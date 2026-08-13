"""Fold the transliteration-adjudication export back into data/data.json.

Reads the app's export, applies it in the order the strata depend on each other,
and recomposes the titles the word lexicon can now reach:

  1. orthography  rewrite the Arabic word in every affected title, and record the
                  transliteration that spelling implies as a lexicon override;
  2. witnesses    correct the title_translit of the rows whose recorded value was
                  the sole witness for a losing reading;
  3. homographs   compose title_translit for the thirteen contested rows, using
                  the adjudicated reading for the contested key and the pipeline's
                  own composer (apply_word_lexicon) for everything else.

Contract, per the annotation-app-design ingest rules:
  * batch-resilient — one malformed decision is QUARANTINED with a reason and the
    rest of the batch applies; the run exits non-zero so nothing is silently lost;
  * merge, never clobber — decisions for items absent from this export are left
    alone, and re-running the same export is a no-op;
  * parked is not resolved — a deferred item is reported, never applied;
  * backup before write.

    python3 scripts/apply_translit_adjudication.py ~/Downloads/translit_adjudication_decisions.json
    python3 scripts/apply_translit_adjudication.py <file> --write
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cluster  # noqa: E402
import normalize  # noqa: E402
from apply_word_lexicon import apply_construct  # noqa: E402

DATA = ROOT / "data" / "data.json"
WORDS = ROOT / "review" / "translit_words_decisions.json"
LOG = ROOT / "review" / "translit_adjudication_applied.json"
# A ruling of "keep" is a RESOLUTION, not an absence of one — but it leaves no
# trace in the data, so the next bake would re-derive the same card and ask again.
# This is the durable record of every such ruling; the builder reads it and drops
# those ids. Cumulative across runs, keyed by the worklist's stable item id.
KEEPS = ROOT / "review" / "translit_adjudication_keeps.json"

ARABIC = re.compile(r"[ء-ٰٟ-ۓ]+")
MARKS = re.compile(r"[ً-ٰٟ]")
# A canonical answer must look canonical: Latin letters, digits, or a Latin-script
# transliteration in the Arabic slot means the annotator typed in the wrong box.
LATIN = re.compile(r"[A-Za-z0-9]")


def words_of(title: str) -> list[str]:
    return [cluster.normalize_ar(w) for w in ARABIC.findall(title or "")]


def bare(w: str) -> str:
    """The surface with vowel/šaddah marks stripped — how the worklist keys words."""
    return MARKS.sub("", w)


def replace_tokens(title: str, word: str, target: str) -> tuple[str, int, list[int]]:
    """Replace whole Arabic tokens whose mark-stripped surface is `word`.

    Returns the rewritten title, the number of replacements, and the WORD
    POSITIONS that changed — the positions are what lets the caller patch the
    matching tokens of an existing title_translit.
    """
    out, last, hits, positions = [], 0, 0, []
    for i, m in enumerate(ARABIC.finditer(title or "")):
        if bare(m.group()) == word:
            out.append(title[last:m.start()])
            out.append(target)
            last = m.end()
            hits += 1
            positions.append(i)
    out.append((title or "")[last:])
    return "".join(out), hits, positions


def state_free(v: str) -> str:
    return v[:-2] + "ah" if v.endswith("at") else v


def build_lexicon(data: dict, decisions: dict, overrides: dict) -> tuple[dict, set]:
    """The composer's lexicon, with adjudicated words forced in as authoritative."""
    lex = {cluster.normalize_ar(w): d["translit"].strip()
           for w, d in decisions.items()
           if d.get("decided") and (d.get("translit") or "").strip() and not d.get("varies")}

    seen: dict[str, set[str]] = {}
    for r in data["rows"]:
        ar = words_of(r.get("title") or "")
        lat = (r.get("title_translit") or "").split()
        if ar and len(ar) == len(lat):
            for a, l in zip(ar, lat):
                seen.setdefault(a, set()).add(l)
    contested = {k for k, v in seen.items() if len({state_free(x) for x in v}) > 1}
    for k, v in seen.items():
        if k not in contested:
            lex.setdefault(k, state_free(sorted(v)[0]))
    for k in contested:
        lex.pop(k, None)

    # An adjudicated word wins over anything inferred from the corpus — that is the
    # whole point of having asked.
    lex.update(overrides)
    return lex, contested - set(overrides)


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

    export = json.loads(src.read_text(encoding="utf-8"))
    if export.get("task") != "translit-adjudication":
        print(f"Refusing: export task is {export.get('task')!r}, not "
              f"'translit-adjudication'.")
        return 1

    data = json.loads(DATA.read_text(encoding="utf-8"))
    word_decisions = json.loads(WORDS.read_text(encoding="utf-8")).get("words", {})
    rows = {r["id"]: r for r in data["rows"]}

    quarantine: list[dict] = []
    parked: list[str] = []
    applied = {"ortho": [], "witness": [], "homograph": [], "attribution": []}
    unchanged: list[str] = []

    def reject(rec, why):
        quarantine.append({"id": rec.get("id"), "stratum": rec.get("stratum"),
                           "reason": why, "record": rec})

    decisions = export.get("decisions") or []
    by_stratum = {s: [d for d in decisions if d.get("stratum") == s]
                  for s in ("ortho", "witness", "homograph", "attribution")}
    for d in decisions:
        if d.get("disposition") == "deferred":
            parked.append(d["id"])

    # Collected across all strata, merged (never replaced) into the keeps file.
    keeps: dict[str, dict] = {}

    def live(stratum):
        return [d for d in by_stratum[stratum] if d.get("disposition") == "resolved"]

    # --- 1. orthography ------------------------------------------------------
    # Rewrites the Arabic; must run before anything reads a title, or the composer
    # looks the word up under a key the fix has just retired.
    overrides: dict[str, str] = {}
    titles: dict[str, str] = {}
    translits: dict[str, str] = {}
    authors: dict[str, str] = {}
    cluster_edits: dict[str, dict] = {}
    clusters = {c["cluster_id"]: c for c in data["clusters"]}
    for d in live("ortho"):
        word, target = d.get("word"), (d.get("target") or "").strip()
        if not target:
            reject(d, "no canonical form recorded"); continue
        if LATIN.search(target):
            reject(d, f"canonical Arabic form contains Latin characters: {target!r}")
            continue
        translit = (d.get("translit") or "").strip()
        scope = d.get("scope") or {}
        # A transliteration is required only where the word sits in a TITLE: that is
        # the surface whose lexicon key the composer looks up. An author field or a
        # cluster name carries no per-word romanization, so demanding one there
        # would reject every name card for a fact that does not exist.
        touches_titles = bool(d.get("rows")) or bool(scope.get("titles"))
        if target != word and touches_titles and not translit:
            reject(d, "spelling changed but no transliteration given — the new "
                      "spelling would be an unsettled lexicon key")
            continue
        if target == word:
            unchanged.append(d["id"])
            keeps[d["id"]] = {"stratum": "ortho", "word": word,
                              "kept": target, "note": d.get("note") or ""}
            if translit:
                overrides[cluster.normalize_ar(target)] = translit
            continue
        if translit:
            overrides[cluster.normalize_ar(target)] = translit
        touched, retranslit = [], []
        for rid in d.get("rows") or []:
            r = rows.get(rid)
            if r is None:
                reject(d, f"row {rid} is not in data.json"); continue

            # Replace whole Arabic TOKENS, matched mark-blind — never a substring
            # rewrite of the title. The worklist keys words by their mark-stripped
            # surface, so a title that already carries a šaddah (الاوّل beside the
            # worklist's الاول) is a match the string form silently misses, and a
            # short word would otherwise also rewrite the inside of a longer one.
            before = titles.get(rid, r.get("title") or "")
            after, hits, positions = replace_tokens(before, word, target)
            if not hits:
                if any(bare(m.group()) == bare(target)
                       for m in ARABIC.finditer(before)):
                    continue                      # already applied — idempotent
                # Guard the edit on the from-value: a re-extraction that changed
                # the title must not let a stale correction fire on new content.
                reject(d, f"row {rid} no longer contains {word!r}"); continue
            # A hit is not a change. The match is mark-BLIND, so re-running an
            # applied decision matches the token it already wrote and rewrites it
            # to itself. The data is right either way, but reporting that as
            # "applied" makes a no-op run indistinguishable from a real one — and
            # the whole value of the idempotence check is telling those apart.
            if after == before:
                unchanged.append(f"{d['id']}:{rid}")
                continue
            titles[rid] = after
            touched.append(rid)

            # A row that ALREADY has a transliteration is not recomposed later, so
            # rewriting its Arabic here would leave the two out of step — silently,
            # and only on the rows that were already finished. Read the prior form
            # off THIS row by position rather than trusting a worklist field: the
            # row is the authority on what its own words say.
            old = (translits.get(rid) or r.get("title_translit") or "").strip()
            if not old:
                continue
            toks = old.split()
            if len(toks) != len(ARABIC.findall(before)):
                reject(d, f"row {rid}: title and title_translit have different word "
                          f"counts ({len(ARABIC.findall(before))} vs {len(toks)}), so "
                          f"the word carrying {word!r} cannot be located — fix that "
                          f"row by hand"); continue
            for i in positions:
                # -ah and -at are one word in two states, and which applies is a
                # property of the POSITION, not of the answer. Carry the state the
                # row already had, so a base-form answer stays correct in a
                # construct slot.
                toks[i] = (translit[:-2] + "at"
                           if toks[i].endswith("at") and translit.endswith("ah")
                           else translit)
            translits[rid] = " ".join(toks)
            retranslit.append(rid)
        # --- the other two surfaces the same ruling governs ------------------
        # An author field and a cluster's canonical_ar / variants hold the same
        # word and take the same fix. Reuse replace_tokens rather than writing a
        # second rewriter, so the mark-blind, whole-token, from-value-guarded
        # behaviour is identical on all three surfaces.
        au_touched, cl_touched = [], []
        for rid in scope.get("authors") or []:
            r = rows.get(rid)
            if r is None:
                reject(d, f"row {rid} is not in data.json"); continue
            before = authors.get(rid, r.get("author") or "")
            after, hits, _ = replace_tokens(before, word, target)
            if hits and after != before:
                authors[rid] = after
                au_touched.append(rid)
        for cid in scope.get("clusters") or []:
            c = clusters.get(cid)
            if c is None:
                reject(d, f"cluster {cid} is not in data.json"); continue
            cur = cluster_edits.get(cid) or {
                "canonical_ar": c.get("canonical_ar") or "",
                "variants": list(c.get("variants") or []),
            }
            can, hits, _ = replace_tokens(cur["canonical_ar"], word, target)
            vs, vhits = [], 0
            for v in cur["variants"]:
                nv, h, _ = replace_tokens(v, word, target)
                vs.append(nv); vhits += h
            if (hits and can != cur["canonical_ar"]) or (vhits and vs != cur["variants"]):
                cluster_edits[cid] = {"canonical_ar": can, "variants": vs}
                cl_touched.append(cid)

        if touched or au_touched or cl_touched:
            applied["ortho"].append({"id": d["id"], "word": word, "target": target,
                                     "translit": translit, "rows": touched,
                                     "retransliterated": retranslit,
                                     "authors": au_touched, "clusters": cl_touched})

    for rid, t in titles.items():
        rows[rid] = {**rows[rid], "title": t}
    for rid, t in translits.items():
        rows[rid] = {**rows[rid], "title_translit": t}
    for rid, a in authors.items():
        rows[rid] = {**rows[rid], "author": a}
    for cid, patch in cluster_edits.items():
        clusters[cid] = {**clusters[cid], **patch}

    # --- 2. witnesses --------------------------------------------------------
    for d in live("witness"):
        # A row can carry several fixes, so the worklist key is not the row id.
        rid = d.get("row") or d["id"]
        target = (d.get("target") or "").strip()
        r = rows.get(rid)
        if r is None:
            reject(d, "row is not in data.json"); continue
        if d.get("action") == "keep":
            unchanged.append(rid)
            keeps[d["id"]] = {"stratum": "witness", "row": rid,
                              "kept": d.get("was"), "note": d.get("note") or ""}
            continue
        if not target:
            reject(d, "no transliteration recorded"); continue
        old = (r.get("title_translit") or "").strip()
        was = d.get("was")
        toks = old.split()
        if old == target or (target in toks and (not was or was not in toks)):
            unchanged.append(rid); continue       # already applied — idempotent
        if was and was not in toks:
            reject(d, f"expected to find {was!r} in {old!r} — the row changed "
                      f"under the adjudication"); continue
        rows[rid] = {**r, "title_translit": " ".join(
            target if w == was else w for w in old.split())}
        applied["witness"].append({"id": d["id"], "row": rid, "was": old,
                                   "now": rows[rid]["title_translit"]})

    # --- 2b. attribution tails -----------------------------------------------
    # Runs after the orthographic passes, so `was` is compared against the title as
    # those passes left it — a tail decided before a šaddah landed inside it would
    # otherwise fail its own from-value guard.
    for d in live("attribution"):
        rid = d.get("row") or d["id"]
        r = rows.get(rid)
        if r is None:
            reject(d, "row is not in data.json"); continue
        if d.get("action") == "keep":
            unchanged.append(d["id"])
            keeps[d["id"]] = {"stratum": "attribution", "row": rid,
                              "kept": d.get("was"), "note": d.get("note") or ""}
            continue
        target = (d.get("target") or "").strip()
        if not target:
            reject(d, "no resulting title recorded"); continue
        current = (r.get("title") or "").strip()
        if current == target:
            unchanged.append(d["id"]); continue      # already applied — idempotent
        tail = (d.get("tail") or "").strip()
        if tail and tail not in current:
            reject(d, f"the tail {tail!r} is no longer in the title {current!r} — "
                      f"the row changed under the adjudication"); continue
        patch = {"title": target}
        # The transliteration is trimmed only when the app said the row's two sides
        # were aligned. Otherwise the tail's own words cannot be located in it, and
        # a guess would silently truncate the wrong end.
        if d.get("target_translit"):
            patch["title_translit"] = d["target_translit"]
        elif tail and not d.get("aligned"):
            patch["discrepancy_note"] = " ".join(filter(None, [
                (r.get("discrepancy_note") or "").strip(),
                f"title_translit not trimmed with the removed tail «{tail}» — "
                f"word counts did not align."]))
        # The tail is not deleted, it is MOVED. A catalogue note is where the
        # bibliographic fact survives; dropping it outright would lose the only
        # record of whose text is being commented on.
        if tail:
            patch["catalog_note"] = " ".join(filter(None, [
                (r.get("catalog_note") or "").strip(),
                f"Title as catalogued ends «{tail}»"
                + (f" ({d['tail_translit']})" if d.get("tail_translit") else "") + "."]))
        rows[rid] = {**r, **patch}
        applied["attribution"].append({"id": d["id"], "row": rid, "was": current,
                                       "now": target, "tail": tail})

    # --- 3. homographs -------------------------------------------------------
    data = {**data, "rows": [rows[r["id"]] for r in data["rows"]]}
    lex, still_contested = build_lexicon(data, word_decisions, overrides)

    for d in live("homograph"):
        rid = d["id"]
        r = rows.get(rid)
        if r is None:
            reject(d, "row is not in data.json"); continue
        if (r.get("title_translit") or "").strip():
            unchanged.append(rid); continue
        readings = {k: v for k, v in (d.get("readings") or {}).items() if v}
        if len(readings) != len(d.get("readings") or {}):
            reject(d, "a contested reading was left unanswered"); continue
        ws = words_of(r.get("title") or "")
        parts = [readings.get(w, lex.get(w)) for w in ws]
        missing = [w for w, p in zip(ws, parts) if not p]
        if missing:
            reject(d, "still-unsettled words after adjudication: "
                      + ", ".join(dict.fromkeys(missing))); continue
        value = " ".join(apply_construct(parts, ws))
        rows[rid] = {**r, "title_translit": value}
        applied["homograph"].append({"id": rid, "title": r.get("title"),
                                     "readings": readings, "value": value})

    updated = {**data, "rows": [rows[r["id"]] for r in data["rows"]],
               "clusters": [clusters[c["cluster_id"]] for c in data["clusters"]]}

    # Composed titles stay separable from hand-written ones — the same channel
    # apply_word_lexicon.py uses, so report_provenance.py keeps working.
    ms = dict(updated.get("machine_suggestions") or {})
    for a in applied["homograph"]:
        ms[a["id"]] = {**(ms.get(a["id"]) or {}), "title_translit": a["value"]}
    if ms:
        updated["machine_suggestions"] = ms

    # --- report --------------------------------------------------------------
    print(f"export: {src}  ({export.get('annotator') or 'no annotator recorded'}, "
          f"{export.get('annotated_date')})")
    print(f"  orthography applied : {len(applied['ortho'])}")
    for a in applied["ortho"]:
        surfaces = []
        if a["rows"]: surfaces.append(f"titles {', '.join(a['rows'])}")
        if a.get("authors"): surfaces.append(f"authors {', '.join(a['authors'])}")
        if a.get("clusters"): surfaces.append(f"clusters {', '.join(a['clusters'])}")
        print(f"     {a['word']} -> {a['target']}  [{a['translit']}]  "
              f"in {'; '.join(surfaces)}"
              + (f"  (title_translit rewritten in {', '.join(a['retransliterated'])})"
                 if a["retransliterated"] else ""))
    print(f"  witnesses corrected : {len(applied['witness'])}")
    for a in applied["witness"]:
        print(f"     {a['row']}  {a['was']}  ->  {a['now']}")
    print(f"  attribution tails   : {len(applied['attribution'])}")
    for a in applied["attribution"]:
        print(f"     {a['row']}  «{a['tail']}» -> catalog_note;  title now: {a['now']}")
    print(f"  titles composed     : {len(applied['homograph'])}")
    for a in applied["homograph"]:
        print(f"     {a['id']}  {a['title']}  ->  {a['value']}")
    print(f"  already applied     : {len(unchanged)}")
    print(f"  ruled KEEP (recorded, so the card does not return): {len(keeps)}")
    print(f"  deferred (parked, NOT applied): {len(parked)}"
          + (f"  {', '.join(parked)}" if parked else ""))
    print(f"  quarantined         : {len(quarantine)}")
    for q in quarantine:
        print(f"     {q['id']} [{q['stratum']}]  {q['reason']}")
    if still_contested:
        # Corpus-wide, not per row: the rows above were composed with an adjudicated
        # reading, but the KEY still carries two readings for any future title.
        print(f"  keys still contested corpus-wide: {', '.join(sorted(still_contested))}")

    if not write:
        print("\nPreview only. Re-run with --write to apply.")
        return 1 if quarantine else 0

    # `.bak.` with the dot, so .gitignore's existing `*.bak.*` rule catches it —
    # a snapshot of the live data file must never become a tracked artifact.
    backup = DATA.with_suffix(f".json.bak.{date.today().isoformat()}-pre-adjudication")
    if not backup.exists():                       # never clobber an earlier same-day copy
        shutil.copy2(DATA, backup)
        print(f"\nBacked up to {backup.name}")
    prior = {}
    if KEEPS.exists():
        prior = json.loads(KEEPS.read_text(encoding="utf-8")).get("keeps") or {}
    KEEPS.write_text(json.dumps(
        {"schema_version": 1, "updated": date.today().isoformat(),
         "keeps": {**prior, **keeps}}, ensure_ascii=False, indent=2), encoding="utf-8")
    normalize.write_json_atomic(DATA, updated)
    LOG.write_text(json.dumps(
        {"schema_version": 1, "applied_date": date.today().isoformat(),
         "source_export": str(src), "annotator": export.get("annotator"),
         "applied": applied, "unchanged": unchanged, "deferred": parked,
         "quarantine": quarantine}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {DATA}")
    print(f"Wrote {LOG}")
    print(f"Wrote {KEEPS}")
    print("\nThen: harvest_authority.py -> cluster.py, and confirm the composed rows "
          "in the app (they arrive tinted, as suggestions).")
    return 1 if quarantine else 0


if __name__ == "__main__":
    raise SystemExit(main())
