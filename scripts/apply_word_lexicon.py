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
    for r in data["rows"]:
        ar, lat = words_of(r.get("title") or ""), (r.get("title_translit") or "").split()
        if ar and len(ar) == len(lat):
            for a, l in zip(ar, lat):
                lex.setdefault(a, l)

    composed, blocked_varies, blocked_unknown = [], [], []

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
            blocked_unknown.append((row["id"], missing))
            return row
        value = " ".join(lex[w] for w in ws)
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
