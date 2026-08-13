"""Self-checks for the adjudication ingest.

The ingest is where the two criticals of the last review lived, and it had no test
of any kind — a static read cannot catch a conservation guard that fires on a
SUCCESSFUL fix, or a keeps store written under the wrong key. `run()` applies an
export to an in-memory data dict and writes nothing, so every case below is a
fixture, not a copy of the corpus.

Run directly, no test framework required:

    python3 scripts/test_apply_translit_adjudication.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cluster                                          # noqa: E402
from apply_translit_adjudication import run             # noqa: E402

# --- fixture vocabulary ---------------------------------------------------
# Two spellings of one word that differ ONLY by a šaddah (U+0651), so
# normalize_ar folds them together and `bare()` maps the fixed form back onto
# the worklist's key. That coincidence is exactly what defeated the first
# conservation guard, so it is the fixture the C1 regression needs.
WORD_BARE = "الادلة"
WORD_SHADDA = "الادلّة"
TITLE_BEFORE = f"كتاب {WORD_BARE}"
TITLE_AFTER = f"كتاب {WORD_SHADDA}"


def mkdata() -> dict:
    """A fresh two-row corpus. Never shared between cases — run() must not
    mutate its input, and a shared dict would hide it if it did."""
    return {
        "schema_version": 1,
        "rows": [
            {"id": "r1", "title": TITLE_BEFORE, "title_translit": "kitāb al-adilla",
             "author": f"محمد بن {WORD_BARE}", "author_cluster_id": "c1",
             "catalog_note": "", "discrepancy_note": ""},
            {"id": "r2", "title": "كتاب المواقف", "title_translit": "kitāb al-mawāqif",
             "author": "محمد بن علي", "author_cluster_id": "c1",
             "catalog_note": "", "discrepancy_note": ""},
        ],
        "clusters": [
            {"cluster_id": "c1", "canonical_ar": "محمد بن علي",
             "canonical_translit": "Muḥammad b. ʿAlī",
             "variants": ["محمد بن علي", f"محمد بن {WORD_BARE}"]},
        ],
    }


def export(*decisions, annotator="test") -> dict:
    return {"task": "translit-adjudication", "annotator": annotator,
            "annotated_date": "2026-08-13", "decisions": list(decisions)}


def ortho(**kw) -> dict:
    rec = {"id": "o-test", "stratum": "ortho", "disposition": "resolved",
           "word": WORD_BARE, "target": WORD_SHADDA, "translit": "al-adilla",
           "confidence": "shadda", "rows": ["r1"], "scope": {}, "note": ""}
    return {**rec, **kw}


# --- cases ----------------------------------------------------------------
def case_shadda_applies_and_conserves() -> list[str]:
    """C1: a mark-only fix must APPLY, and the conservation audit must not fire.

    `bare()` is mark-blind, so the fixed token still bares to the original word.
    The first guard asked "does the word's key survive?" and therefore rejected
    every successful šaddah fix — the run refused to write precisely because it
    had worked, and the abort stranded the batch's KEEP rulings with it.
    """
    bad = []
    res = run(export(ortho()), data=mkdata(), word_decisions={})
    if res["quarantine"]:
        bad.append("a successful šaddah fix was quarantined: "
                   + "; ".join(q["reason"] for q in res["quarantine"]))
    if len(res["applied"]["ortho"]) != 1:
        bad.append(f"expected 1 ortho application, got {len(res['applied']['ortho'])}")
    title = {r["id"]: r for r in res["updated"]["rows"]}["r1"]["title"]
    if title != TITLE_AFTER:
        bad.append(f"title is {title!r}, expected {TITLE_AFTER!r}")
    return bad


def case_input_not_mutated() -> list[str]:
    """run() returns a new corpus; the caller's dict is untouched."""
    data = mkdata()
    run(export(ortho()), data=data, word_decisions={})
    row = {r["id"]: r for r in data["rows"]}["r1"]
    return ([] if row["title"] == TITLE_BEFORE
            else [f"run() mutated its input: r1.title is now {row['title']!r}"])


def case_idempotent() -> list[str]:
    """Re-running an applied export is a no-op — the contract at the module head.

    The mark-blind match means a second run DOES find its own output; what must
    not happen is reporting that as work, which would make a no-op run
    indistinguishable from a real one.
    """
    bad = []
    first = run(export(ortho()), data=mkdata(), word_decisions={})
    second = run(export(ortho()), data=first["updated"], word_decisions={})
    if second["applied"]["ortho"]:
        bad.append("re-running an applied export reported work: "
                   + str(second["applied"]["ortho"]))
    if "o-test:r1" not in second["unchanged"]:
        bad.append(f"re-run did not report r1 as unchanged: {second['unchanged']}")
    if second["quarantine"]:
        bad.append("re-run quarantined: "
                   + "; ".join(q["reason"] for q in second["quarantine"]))
    return bad


def case_deferred_is_not_applied() -> list[str]:
    """Parked is reported, never applied."""
    bad = []
    res = run(export(ortho(disposition="deferred")), data=mkdata(), word_decisions={})
    if res["applied"]["ortho"]:
        bad.append("a deferred decision was applied")
    if res["parked"] != ["o-test"]:
        bad.append(f"deferred not reported as parked: {res['parked']}")
    row = {r["id"]: r for r in res["updated"]["rows"]}["r1"]
    if row["title"] != TITLE_BEFORE:
        bad.append("a deferred decision edited the row anyway")
    return bad


def case_batch_resilient() -> list[str]:
    """One malformed decision is quarantined; the rest of the batch still lands."""
    bad = []
    res = run(export(ortho(id="o-good"),
                     ortho(id="o-bad", target="al-adilla")),  # Latin in the Arabic slot
              data=mkdata(), word_decisions={})
    ids = [a["id"] for a in res["applied"]["ortho"]]
    if ids != ["o-good"]:
        bad.append(f"the sound decision did not apply alone: {ids}")
    qids = [q["id"] for q in res["quarantine"]]
    if qids != ["o-bad"]:
        bad.append(f"expected o-bad quarantined, got {qids}")
    return bad


def case_keeps_are_keyed_by_decision_id() -> list[str]:
    """C2: the builder drops a card by its ITEM id, so every stratum's keep must
    be stored under `d["id"]` — a keep filed under a row id silently re-asks."""
    bad = []
    res = run(export(
        ortho(id="o-keep", target=WORD_BARE),
        {"id": "w-keep", "stratum": "witness", "disposition": "resolved",
         "row": "r2", "action": "keep", "was": "al-mawāqif", "note": ""},
        {"id": "r2-attr", "stratum": "attribution", "disposition": "resolved",
         "row": "r2", "action": "keep", "was": "كتاب المواقف", "note": ""},
    ), data=mkdata(), word_decisions={})
    for want in ("o-keep", "w-keep", "r2-attr"):
        if want not in res["keeps"]:
            bad.append(f"keep {want!r} missing; keeps holds {sorted(res['keeps'])}")
    if res["quarantine"]:
        bad.append("a keep was quarantined: "
                   + "; ".join(q["reason"] for q in res["quarantine"]))
    return bad


def case_from_value_guard() -> list[str]:
    """A stale correction must not fire on content that has since changed."""
    data = mkdata()
    data = {**data, "rows": [{**r, "title": "كتاب اخر"} if r["id"] == "r1" else r
                             for r in data["rows"]]}
    res = run(export(ortho()), data=data, word_decisions={})
    reasons = [q["reason"] for q in res["quarantine"]]
    return ([] if any("no longer contains" in x for x in reasons)
            else [f"a stale correction was not caught; quarantine says {reasons}"])


def case_name_only_card() -> list[str]:
    """A card whose word sits only in author fields and cluster names.

    It needs no transliteration — a name carries no per-word romanization — and
    the cluster variants it rewrites must come back de-duplicated: folding two
    spellings of one name onto the same target used to leave the identical string
    twice, because the rewrite was positional and never dropped duplicates.
    """
    bad = []
    word, target = "\u0627\u0628\u064A", "\u0623\u0628\u064A"        # ابي -> أبي
    raw = f"\u0645\u062D\u0645\u062F \u0628\u0646 {word}"            # محمد بن ابي
    fixed = f"\u0645\u062D\u0645\u062F \u0628\u0646 {target}"
    data = {
        "schema_version": 1,
        "rows": [{"id": "r1", "title": "\u0643\u062A\u0627\u0628",
                  "title_translit": "kit\u0101b", "author": raw,
                  "author_cluster_id": "c1", "catalog_note": "",
                  "discrepancy_note": ""}],
        "clusters": [{"cluster_id": "c1", "canonical_ar": raw,
                      "canonical_translit": "x", "variants": [raw, fixed]}],
    }
    res = run(export(ortho(id="o-name", word=word, target=target, translit=None,
                           confidence="hamza", rows=[],
                           scope={"titles": [], "authors": ["r1"], "clusters": ["c1"]})),
              data=data, word_decisions={})
    if res["quarantine"]:
        bad.append("a name-only card was quarantined: "
                   + "; ".join(q["reason"] for q in res["quarantine"]))
    got_rows = {r["id"]: r for r in res["updated"]["rows"]}
    if got_rows["r1"]["author"] != fixed:
        bad.append(f"author is {got_rows['r1']['author']!r}, expected {fixed!r}")
    c = {c["cluster_id"]: c for c in res["updated"]["clusters"]}["c1"]
    if c["canonical_ar"] != fixed:
        bad.append(f"canonical_ar is {c['canonical_ar']!r}, expected {fixed!r}")
    if c["variants"] != [fixed]:
        bad.append(f"variants is {c['variants']!r}, expected {[fixed]!r} — the two "
                   f"spellings fold onto one target and must de-duplicate")
    applied = res["applied"]["ortho"]
    if not applied or applied[0]["authors"] != ["r1"] or applied[0]["clusters"] != ["c1"]:
        bad.append(f"the surfaces touched were not reported: {applied}")
    return bad


def case_conservation_covers_authors() -> list[str]:
    """The conservation audit re-verified TITLES only, so a reverted author edit
    went unseen where a reverted title edit could not — and an author field is now
    the only surface some cards touch. Assert it inspects the end state there."""
    word, target = "\u0627\u0628\u064A", "\u0623\u0628\u064A"
    raw = f"\u0645\u062D\u0645\u062F \u0628\u0646 {word}"
    data = {
        "schema_version": 1,
        "rows": [{"id": "r1", "title": "\u0643\u062A\u0627\u0628",
                  "title_translit": "kit\u0101b", "author": raw,
                  "author_cluster_id": "c1", "catalog_note": "",
                  "discrepancy_note": ""}],
        "clusters": [{"cluster_id": "c1", "canonical_ar": raw,
                      "canonical_translit": "x", "variants": [raw]}],
    }
    res = run(export(ortho(id="o-name", word=word, target=target, translit=None,
                           confidence="hamza", rows=[],
                           scope={"titles": [], "authors": ["r1"], "clusters": []})),
              data=data, word_decisions={})
    row = {r["id"]: r for r in res["updated"]["rows"]}["r1"]
    if row["author"] != f"\u0645\u062D\u0645\u062F \u0628\u0646 {target}":
        return [f"author not rewritten: {row['author']!r}"]
    # A clean run must not accuse itself.
    return ([] if not res["quarantine"]
            else ["the audit fired on a successful author fix: "
                  + "; ".join(q["reason"] for q in res["quarantine"])])


# --- H3: a reading is not a ruling -------------------------------------------
# A corpus that genuinely disagrees with itself about one word: the same Arabic
# key, two transliterations. Only an affirmative answer may close that.
CONTESTED = "\u0627\u0644\u0641\u0631\u0642"                       # الفرق
CONTESTED_MARKED = "\u0627\u0644\u0641\u0631\u0652\u0642"        # with a sukūn


def contested_data() -> dict:
    return {
        "schema_version": 1,
        "rows": [
            {"id": "r1", "title": f"\u0643\u062A\u0627\u0628 {CONTESTED}",
             "title_translit": "kit\u0101b al-farq", "author": "", "catalog_note": "",
             "author_cluster_id": "c1", "discrepancy_note": ""},
            {"id": "r2", "title": f"\u0628\u0627\u0628 {CONTESTED}",
             "title_translit": "b\u0101b al-firaq", "author": "", "catalog_note": "",
             "author_cluster_id": "c1", "discrepancy_note": ""},
        ],
        "clusters": [{"cluster_id": "c1", "canonical_ar": "x",
                      "canonical_translit": "x", "variants": []}],
    }


def contested_key() -> str:
    return cluster.normalize_ar(CONTESTED)


def h3(**kw) -> dict:
    return ortho(id="o-h3", word=CONTESTED, target=CONTESTED_MARKED,
                 translit="al-farq", confidence="shadda", rows=["r1"], **kw)


def case_default_reading_does_not_settle_a_key() -> list[str]:
    """A transliteration box left as it arrived is the corpus's own reading,
    accepted. The app tells the annotator a mark "changes no key and unblocks no
    title"; it must not then close a contest they never ruled on."""
    bad = []
    res = run(export(h3(translit_source="default")),
              data=contested_data(), word_decisions={})
    if contested_key() not in res["still_contested"]:
        bad.append(f"an accepted default settled {contested_key()!r}; "
                   f"still contested: {sorted(res['still_contested'])}")
    if not any("accepted as offered" in line for line in res["report"]):
        bad.append("the report does not say the key was left open")
    return bad


def case_affirmative_reading_settles_both_keys() -> list[str]:
    """Typing or picking a reading IS a ruling — and it settles the key the rows
    carry as well as the one the new spelling introduces. De-contesting only the
    new key left the old one contested forever, exactly where a spelling changed."""
    bad = []
    res = run(export(h3(translit_source="typed")),
              data=contested_data(), word_decisions={})
    if contested_key() in res["still_contested"]:
        bad.append(f"an affirmative ruling left {contested_key()!r} contested")
    if cluster.normalize_ar(CONTESTED_MARKED) in res["still_contested"]:
        bad.append("the new spelling's key was left contested")
    if res["overrides"].get(cluster.normalize_ar(CONTESTED_MARKED)) != "al-farq":
        bad.append(f"the reading was not installed corpus-wide: {res['overrides']}")
    return bad


def case_row_scoped_reading_stays_local() -> list[str]:
    """`only_rows` exists because a form can be a fault HERE and correct
    elsewhere, so a corpus-wide rewrite would be the bug. Its reading must reach
    the named rows and nothing else — not the lexicon, not the contest."""
    bad = []
    res = run(export(h3(translit_source="typed", row_scoped=True)),
              data=contested_data(), word_decisions={})
    if res["overrides"]:
        bad.append(f"a row-scoped ruling went corpus-wide: {res['overrides']}")
    if contested_key() not in res["still_contested"]:
        bad.append("a row-scoped ruling settled a corpus-wide key")
    if not any("NOT installed corpus-wide" in line for line in res["report"]):
        bad.append("the report does not say the reading was held local")
    # …but it must still have done its local work.
    r1 = {r["id"]: r for r in res["updated"]["rows"]}["r1"]
    if CONTESTED_MARKED not in r1["title"]:
        bad.append(f"the scoped fix did not reach its own row: {r1['title']!r}")
    return bad


# --- H2: the affordance the ingest could not consume -------------------------
TAIL = "\u0644\u0627\u0628\u064A \u0639\u0644\u064A"                 # لابي علي
ATTR_TITLE = f"\u0643\u062A\u0627\u0628 \u0627\u0644\u0645\u0648\u0627\u0642\u0641 {TAIL}"
TYPED = "\u0643\u062A\u0627\u0628 \u0622\u062E\u0631"               # كتاب آخر


def attr_data(*, with_translit: bool = True) -> dict:
    return {
        "schema_version": 1,
        "rows": [{"id": "r7", "title": ATTR_TITLE,
                  "title_translit": "kit\u0101b al-maw\u0101qif li-Ab\u012B \u02BFAl\u012B"
                                    if with_translit else "",
                  "author": "", "author_cluster_id": "c1", "catalog_note": "",
                  "discrepancy_note": ""}],
        "clusters": [{"cluster_id": "c1", "canonical_ar": "x",
                      "canonical_translit": "x", "variants": []}],
    }


def attr(**kw) -> dict:
    rec = {"id": "r7-attr", "stratum": "attribution", "disposition": "resolved",
           "row": "r7", "action": "set_title", "target": TYPED,
           "target_translit": "kit\u0101b \u0101\u1E2Bar", "was": ATTR_TITLE,
           "tail": TAIL, "tail_translit": "li-Ab\u012B \u02BFAl\u012B",
           "aligned": True, "note": ""}
    return {**rec, **kw}


def case_set_title_applies() -> list[str]:
    """A title the annotator wrote by hand is a supported answer, not a fault."""
    bad = []
    res = run(export(attr()), data=attr_data(), word_decisions={})
    if res["quarantine"]:
        bad.append("a hand-written title was quarantined: "
                   + "; ".join(q["reason"] for q in res["quarantine"]))
    r = {x["id"]: x for x in res["updated"]["rows"]}["r7"]
    if r["title"] != TYPED:
        bad.append(f"title is {r['title']!r}, expected {TYPED!r}")
    if r["title_translit"] != "kit\u0101b \u0101\u1E2Bar":
        bad.append(f"title_translit is {r['title_translit']!r}, not the one given")
    if TAIL not in (r.get("catalog_note") or ""):
        bad.append(f"the removed tail was not moved to catalog_note: "
                   f"{r.get('catalog_note')!r}")
    if not res["applied"]["attribution"]:
        bad.append("the application was not reported")
    return bad


def case_set_title_without_translit_is_refused() -> list[str]:
    """The row already has a transliteration and a typed title cannot be trimmed
    automatically, so applying one without the other desynchronizes the row."""
    res = run(export(attr(target_translit=None)), data=attr_data(), word_decisions={})
    reasons = [q["reason"] for q in res["quarantine"]]
    if not any("disagreeing" in x for x in reasons):
        return [f"expected a desync refusal, got {reasons}"]
    r = {x["id"]: x for x in res["updated"]["rows"]}["r7"]
    return ([] if r["title"] == ATTR_TITLE
            else ["the row was edited anyway despite the refusal"])


def case_set_title_needs_no_translit_when_the_row_has_none() -> list[str]:
    """…and where there is nothing to desynchronize, nothing is demanded."""
    res = run(export(attr(target_translit=None)),
              data=attr_data(with_translit=False), word_decisions={})
    if res["quarantine"]:
        return ["refused a title on a row that carries no transliteration: "
                + "; ".join(q["reason"] for q in res["quarantine"])]
    r = {x["id"]: x for x in res["updated"]["rows"]}["r7"]
    return [] if r["title"] == TYPED else [f"title is {r['title']!r}"]


def case_set_title_guards_its_from_value() -> list[str]:
    """A title written against one reading of the row must not overwrite another."""
    data = attr_data()
    data = {**data, "rows": [{**r, "title": "\u0643\u062A\u0627\u0628 \u0645\u062E\u062A\u0644\u0641"}
                             for r in data["rows"]]}
    res = run(export(attr()), data=data, word_decisions={})
    reasons = [q["reason"] for q in res["quarantine"]]
    return ([] if any("changed under the adjudication" in x for x in reasons)
            else [f"a stale hand-written title was applied; quarantine says {reasons}"])


def case_unknown_action_is_refused_not_guessed() -> list[str]:
    """The root defect was the missing `else`: anything that was not "keep" fell
    into the tail-removal path, so an unimplemented action was not rejected but
    silently mis-executed, and the reason blamed a cause that had not occurred."""
    bad = []
    res = run(export(attr(action="frobnicate")), data=attr_data(), word_decisions={})
    reasons = [q["reason"] for q in res["quarantine"]]
    if not any("unknown action" in x and "frobnicate" in x for x in reasons):
        bad.append(f"the unknown action was not named in the refusal: {reasons}")
    if any("changed under the adjudication" in x for x in reasons):
        bad.append("the refusal still blames the row for changing")
    r = {x["id"]: x for x in res["updated"]["rows"]}["r7"]
    if r["title"] != ATTR_TITLE:
        bad.append("an unknown action edited the row")
    return bad


def case_strip_tail_still_works() -> list[str]:
    """The path the fail-loud else must not have broken."""
    bad = []
    proposed = ATTR_TITLE[:ATTR_TITLE.index(TAIL)].strip()
    res = run(export(attr(action="strip_tail", target=proposed,
                          target_translit="kit\u0101b al-maw\u0101qif")),
              data=attr_data(), word_decisions={})
    if res["quarantine"]:
        bad.append("a strip was quarantined: "
                   + "; ".join(q["reason"] for q in res["quarantine"]))
    r = {x["id"]: x for x in res["updated"]["rows"]}["r7"]
    if r["title"] != proposed:
        bad.append(f"title is {r['title']!r}, expected {proposed!r}")
    return bad


CASES = [
    ("šaddah fix applies and survives the conservation audit (C1)",
     case_shadda_applies_and_conserves),
    ("run() does not mutate the corpus it is given", case_input_not_mutated),
    ("re-running an applied export is a no-op", case_idempotent),
    ("a deferred decision is parked, never applied", case_deferred_is_not_applied),
    ("one malformed decision does not sink the batch", case_batch_resilient),
    ("every stratum's keep is keyed by the decision id (C2)",
     case_keeps_are_keyed_by_decision_id),
    ("an edit is guarded on its from-value", case_from_value_guard),
    ("a name-only card rewrites authors and de-duplicates cluster variants",
     case_name_only_card),
    ("the conservation audit inspects author fields too",
     case_conservation_covers_authors),
    ("an accepted default reading does not settle a contested key",
     case_default_reading_does_not_settle_a_key),
    ("a typed or chosen reading settles both the old and the new key",
     case_affirmative_reading_settles_both_keys),
    ("a row-scoped reading stays local but still fixes its own rows",
     case_row_scoped_reading_stays_local),
    ("a hand-written title applies, tail and all", case_set_title_applies),
    ("a hand-written title with no transliteration is refused, honestly",
     case_set_title_without_translit_is_refused),
    ("…and is not demanded where the row has none",
     case_set_title_needs_no_translit_when_the_row_has_none),
    ("a hand-written title is guarded on its from-value",
     case_set_title_guards_its_from_value),
    ("an unrecognized action is refused, not guessed at",
     case_unknown_action_is_refused_not_guessed),
    ("strip_tail still works", case_strip_tail_still_works),
]


def main() -> int:
    failures = []
    for label, fn in CASES:
        try:
            bad = fn()
        except Exception as exc:                       # a case that throws IS a failure
            bad = [f"raised {type(exc).__name__}: {exc}"]
        if bad:
            failures.append((label, bad))
            print(f"  FAIL {label}")
            for b in bad:
                print(f"         {b}")
        else:
            print(f"  ok   {label}")
    if failures:
        print(f"\nFAILED — {len(failures)} of {len(CASES)} cases")
        return 1
    print(f"\nOK — {len(CASES)} cases pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
