"""Self-checks for the parts of cluster.py that a re-cluster can silently undo.

`variants` is rebuilt on every run from the row `author` strings, so an
orthographic ruling applied to a cluster name used to survive exactly one step of
the documented pipeline and then revert. It is now pinned through
harvest_authority.py and merged back here — a merge with two failure modes worth
pinning: a pinned spelling that fails to win, and a pinned spelling that
RESURRECTS after the corpus stopped producing anything like it.

Run directly, no test framework required:

    python3 scripts/test_cluster.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cluster  # noqa: E402

# Two spellings of one name differing only by a hamza carrier, which normalize_ar
# folds — so they share a key and the pinned one must win on it.
RAW = "ابو الحسن محمد بن ابي يعلى"
FIXED = "أبو الحسن محمد بن أبي يعلى"
OTHER = "محمد بن علي"
RETIRED = "احمد بن يزدانيار"


def check_merge_variants() -> list[str]:
    failures = []
    cases = [
        # (computed, pinned, expected, why)
        ([RAW], [FIXED], [FIXED],
         "the adjudicated spelling wins on a key the corpus still produces"),
        ([RAW, OTHER], [FIXED], sorted([FIXED, OTHER]),
         "…and leaves every other variant alone"),
        ([RAW], [], [RAW], "no pin means the computed value stands"),
        ([], [FIXED], [],
         "a pin whose key no longer occurs is DROPPED, not resurrected"),
        ([OTHER], [RETIRED], [OTHER],
         "a stale pin cannot re-inject a name the corpus stopped writing"),
        ([RAW, FIXED], [FIXED], [FIXED],
         "two spellings of one key collapse to the pinned one — the dedupe the "
         "ingest's positional rewrite never did"),
        ([OTHER, OTHER], [], [OTHER], "duplicates collapse"),
    ]
    for computed, pinned, want, why in cases:
        got = cluster.merge_variants(computed, pinned)
        if got != want:
            failures.append(f"merge_variants({computed!r}, {pinned!r}) = {got!r}, "
                            f"expected {want!r} ({why})")
    # Idempotence: re-running the pipeline must not keep changing the answer.
    once = cluster.merge_variants([RAW, OTHER], [FIXED])
    twice = cluster.merge_variants(once, [FIXED])
    if once != twice:
        failures.append(f"merge_variants is not idempotent: {once!r} -> {twice!r}")
    return failures


def check_normalize_ar_folds_the_carrier() -> list[str]:
    """The merge is keyed on normalize_ar, so the whole rule rests on the two
    spellings actually folding together. If they ever stop, the pin silently
    becomes an ADDITION rather than a replacement."""
    if cluster.normalize_ar(RAW) != cluster.normalize_ar(FIXED):
        return [f"normalize_ar no longer folds {RAW!r} and {FIXED!r} together — "
                f"the variant merge would add a spelling instead of replacing one"]
    return []


CASES = [
    ("a pinned variant wins its key, and a stale one is dropped",
     check_merge_variants),
    ("normalize_ar still folds the hamza carrier the merge keys on",
     check_normalize_ar_folds_the_carrier),
]


def main() -> int:
    failures = []
    for label, fn in CASES:
        try:
            bad = fn()
        except Exception as exc:
            bad = [f"raised {type(exc).__name__}: {exc}"]
        if bad:
            failures.append(label)
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
