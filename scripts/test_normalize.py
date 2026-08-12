"""Self-checks for the pure-Python string metrics in normalize.py.

Run directly, no test framework required:

    python3 scripts/test_normalize.py

These exist because ``jaro_winkler_similarity`` replaced a compiled third-party
implementation (jellyfish), which the pipeline could no longer import once the
installed wheel's architecture stopped matching the interpreter. The published
reference values below are the contract: they are the standard Jaro / Jaro-Winkler
worked examples, and they are what the replacement was validated against.

Note that ``cluster.cluster_confidence`` — the pipeline's only caller — is
currently dormant: every cluster in data/data.json comes from authority.json,
which is assigned a hardcoded confidence of 1.0. The metric only runs for
clusters the authority does not cover. So these vectors, not the stored data,
are what guards this function.
"""
from __future__ import annotations

import sys

import normalize

# (a, b, expected). Standard published values for Jaro-Winkler.
JARO_WINKLER_CASES = [
    ("MARTHA", "MARHTA", 0.9611111111111111),
    ("DIXON", "DICKSONX", 0.8133333333333332),
    ("JELLYFISH", "SMELLYFISH", 0.8962962962962964),
    ("DWAYNE", "DUANE", 0.8400000000000001),
    ("", "", 1.0),
    ("a", "", 0.0),
    ("", "a", 0.0),
    ("abc", "abc", 1.0),
    ("abc", "xyz", 0.0),
]

# Jaro without the Winkler prefix boost.
JARO_CASES = [
    ("MARTHA", "MARHTA", 0.9444444444444445),
    ("DIXON", "DICKSONX", 0.7666666666666666),
    ("", "", 1.0),
    ("abc", "abc", 1.0),
]

TOLERANCE = 1e-12


def check(label, fn, cases) -> list[str]:
    failures = []
    for a, b, expected in cases:
        got = fn(a, b)
        if abs(got - expected) > TOLERANCE:
            failures.append(f"{label}({a!r}, {b!r}) = {got!r}, expected {expected!r}")
    return failures


def check_properties() -> list[str]:
    """Invariants that must hold for any pair, not just the worked examples."""
    failures = []
    pairs = [("al-Sulami", "al-Sulami"), ("al-Harrali", "al-Harrani"),
             ("Ibn Arabi", "Ibn al-Arabi"), ("Qunawi", "Tusi"), ("x", "yz")]
    for a, b in pairs:
        jaro = normalize.jaro_similarity(a, b)
        jw = normalize.jaro_winkler_similarity(a, b)
        if not 0.0 <= jaro <= 1.0:
            failures.append(f"jaro({a!r}, {b!r}) = {jaro!r} out of range")
        if not 0.0 <= jw <= 1.0:
            failures.append(f"jaro_winkler({a!r}, {b!r}) = {jw!r} out of range")
        if jw < jaro - TOLERANCE:
            failures.append(f"winkler boost lowered the score for {a!r}, {b!r}")
        if abs(normalize.jaro_winkler_similarity(b, a) - jw) > TOLERANCE:
            failures.append(f"jaro_winkler is not symmetric for {a!r}, {b!r}")
    return failures


def main() -> int:
    failures = (check("jaro_winkler_similarity", normalize.jaro_winkler_similarity,
                      JARO_WINKLER_CASES)
                + check("jaro_similarity", normalize.jaro_similarity, JARO_CASES)
                + check_properties())
    total = len(JARO_WINKLER_CASES) + len(JARO_CASES)
    if failures:
        print(f"FAILED ({len(failures)} of {total} vectors plus properties):")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"OK — {total} reference vectors and all invariants pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
