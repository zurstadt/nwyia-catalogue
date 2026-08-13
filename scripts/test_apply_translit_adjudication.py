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
