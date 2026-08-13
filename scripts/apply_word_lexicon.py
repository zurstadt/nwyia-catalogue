"""Compose title transliterations from the word list, as SUGGESTIONS.

Takes the export from review/translit_words.html and writes title_translit for every
title whose every word is now settled. A composed title is recorded as a machine
suggestion (the same `machine_suggestions` channel the app uses), so
report_provenance.py can still tell a composed title from one written by hand — the
whole point of that record.

Rules, all of them refusals rather than guesses:
  * a title is composed only when EVERY one of its words is settled;
  * a word marked "varies by context" disqualifies every title containing it;
  * word order follows the Arabic, so the composition is the words in sequence —
    no attempt is made to fix construct state, which is exactly what "varies"
    is for.

    python3 scripts/apply_word_lexicon.py ~/Downloads/translit_words_decisions.json
    python3 scripts/apply_word_lexicon.py <file> --write
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cluster  # noqa: E402
import normalize  # noqa: E402

DATA = ROOT / "data" / "data.json"
# Arabic letters and combining marks; not punctuation, not digits. Must stay in
# step with arabicKey() in app/index.html — a divergence here silently stops words
# matching between the app and the pipeline.
ARABIC = re.compile(r"[ء-ٰٟ-ۓ]+")


def words_of(title: str) -> list[str]:
    return [cluster.normalize_ar(w) for w in ARABIC.findall(title or "")]


# --- construct state (iḍāfa) -------------------------------------------------
# A word ending in tāʾ marbūṭa is romanized -ah standing alone, but -at when it is
# the FIRST term of a noun phrase: risālah, but risālat manāzil al-abdāl. The word
# list holds base forms, so the rule is applied here rather than asked 170 times.
#
# Two conditions decide it, and both are grammatical rather than heuristic:
#   * a muḍāf is formally INDEFINITE — a word carrying al- is not one, so
#     al-risālah al-qušayrīyah keeps -ah (that is an adjective, not a construct);
#   * something must follow it, and that something must be a noun.
#
# Whether the follower is a noun is read off the ANNOTATOR'S OWN transliteration
# rather than guessed from the Arabic: a value beginning wa-/bi-/li- is a particle
# with its host, and the closed-class words below are never a second term.
BLOCK_PREFIX = ("wa-", "bi-", "li-", "la-")
BLOCK_EXACT = {"fī", "min", "ʿan", "ʿalā", "ilā", "maʿa", "bayna", "allatī",
               "allaḏī", "hiya", "huwa", "mā", "lā", "kāna", "yakūn", "ʾan", "in"}
DEFINITE = ("ال",)


def in_construct(arabic: str, nxt_arabic: str | None, nxt_translit: str | None) -> bool:
    if arabic.startswith(DEFINITE):
        return False
    if not nxt_arabic or not nxt_translit:
        return False
    low = nxt_translit.lower()
    if low in BLOCK_EXACT or low.startswith(BLOCK_PREFIX):
        return False
    if not re.search(r"[ء-ي]", nxt_arabic):     # a number or stray token
        return False
    return True


def apply_construct(parts: list[str], words: list[str]) -> list[str]:
    """Rewrite -ah to -at wherever a word heads a following noun."""
    out = []
    for i, (t, w) in enumerate(zip(parts, words)):
        nxt_w = words[i + 1] if i + 1 < len(words) else None
        nxt_t = parts[i + 1] if i + 1 < len(parts) else None
        if t.endswith("ah") and in_construct(w, nxt_w, nxt_t):
            t = t[:-2] + "at"
        out.append(t)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        print(__doc__)
        return 1
    src = Path(args[0]).expanduser()
    if not src.exists():
        print(f"Not found: {src}")
        return 1

    decisions = json.loads(src.read_text(encoding="utf-8")).get("words", {})
    lex, varies = {}, set()
    for w, d in decisions.items():
        key = cluster.normalize_ar(w)
        if d.get("varies"):
            varies.add(key)
        elif d.get("decided") and (d.get("translit") or "").strip():
            lex[key] = d["translit"].strip()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    clusters = {c["cluster_id"]: c for c in data["clusters"]}
    modern = {k for k, c in clusters.items() if c.get("category") == "modern"}

    # Every word already attested by a completed row counts as settled too — the
    # word list only ever contained the ones that were missing.
    #
    # But collect ALL readings per key and refuse a key that has more than one.
    # normalize_ar folds alif maqṣūra to yāʾ (right for matching names, its actual
    # job), which merges على (ʿalā) with علي (ʿAlī) onto one key. Taking the first
    # writer silently rendered every «على» as the personal name. A key with two
    # readings is not settled; it is contested, and must block rather than guess.
    # Rows whose transliteration REORDERS the Arabic. Count-matching assumes word
    # order is preserved; when it is not, every pair in the row is shifted and the
    # result looks perfectly well-formed. r0009 renders a scrambled extraction in
    # readable order, which silently taught بنفح→tarǧamat, البابا→yūnus, عشر→al-rūḥ
    # and three more. There is no general way to detect this, so a reordered row is
    # named here and excluded from learning.
    REORDERED = {"r0009"}

    seen: dict[str, set[str]] = {}
    for r in data["rows"]:
        if r["id"] in REORDERED:
            continue
        ar, lat = words_of(r.get("title") or ""), (r.get("title_translit") or "").split()
        if ar and len(ar) == len(lat):
            for a, l in zip(ar, lat):
                seen.setdefault(a, set()).add(l)
    contested = {k for k, v in seen.items() if len(v) > 1}
    for k, v in seen.items():
        if k not in contested:
            lex.setdefault(k, next(iter(v)))
    for k in contested:
        lex.pop(k, None)

    composed, blocked_varies, blocked_unknown, blocked_contested = [], [], [], []

    def compose(row: dict) -> dict:
        if row.get("author_cluster_id") in modern:
            return row
        title = (row.get("title") or "").strip()
        if not title or (row.get("title_translit") or "").strip():
            return row
        ws = words_of(title)
        if not ws:
            return row
        if any(w in varies for w in ws):
            blocked_varies.append(row["id"])
            return row
        missing = [w for w in ws if w not in lex]
        if missing:
            hit = [w for w in missing if w in contested]
            (blocked_contested if hit else blocked_unknown).append((row["id"], hit or missing))
            return row
        value = " ".join(apply_construct([lex[w] for w in ws], ws))
        composed.append((row["id"], title, value))
        return {**row, "title_translit": value}

    updated = {**data, "rows": [compose(r) for r in data["rows"]]}

    # Record what the machine proposed, beside the value it produced, so the
    # composed rows stay separable from hand-written ones at export time.
    ms = dict(updated.get("machine_suggestions") or {})
    for rid, _t, value in composed:
        entry = dict(ms.get(rid) or {})
        entry["title_translit"] = value
        ms[rid] = entry
    if ms:
        updated["machine_suggestions"] = ms

    print(f"settled words available : {len(lex)}")
    print(f"words marked 'varies'   : {len(varies)}")
    print(f"titles composed         : {len(composed)}")
    print(f"blocked by a 'varies' word: {len(blocked_varies)}")
    print(f"blocked by unknown words  : {len(blocked_unknown)}")
    print(f"blocked by a CONTESTED word: {len(blocked_contested)}  "
          f"(one key, two readings — refused rather than guessed)")
    for rid, ws in blocked_contested[:8]:
        print(f"   {rid}  contested: {', '.join(ws)}  readings: "
              + " / ".join(sorted(seen[ws[0]])) if ws else "")
    for rid, title, value in composed[:15]:
        print(f"   {rid}  {title}  ->  {value}")
    if blocked_unknown[:5]:
        print("\n  still missing, e.g.:")
        for rid, miss in blocked_unknown[:5]:
            print(f"   {rid}  needs {', '.join(miss[:4])}")

    if not write:
        print("\nPreview only. Re-run with --write to apply.")
        return 0
    normalize.write_json_atomic(DATA, updated)
    print(f"\nWrote {DATA}")
    print("Then: harvest_authority.py -> cluster.py, and confirm the composed rows "
          "in the app (they arrive tinted, as suggestions).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
