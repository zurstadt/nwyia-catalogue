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

import re

import cluster
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


# --- Arabic word tokens and marks --------------------------------------------
# `bare()` and `AR_WORD` replaced four hand-written copies, two of which were the
# codepoint range [\u064B-\u0670]. That range reads like "the tashkil" and is not:
# it also covers the Arabic-Indic digits and the dotless base letters, so
# "stripping marks" deleted them. The vectors below pin the boundary in both
# directions — what must go, and what must survive.
def check_bare() -> list[str]:
    failures = []
    cases = [
        # (input, expected, why)
        ("\u0627\u0644\u0623\u062F\u0644\u0651\u0629",
         "\u0627\u0644\u0623\u062F\u0644\u0629", "a šaddah is a mark and goes"),
        ("\u0627\u0644\u062A\u0635\u0648\u0651\u0641",
         "\u0627\u0644\u062A\u0635\u0648\u0641", "…mid-word too"),
        ("\u0643\u0640\u062A\u0627\u0628", "\u0643\u062A\u0627\u0628",
         "tatweel goes, so bare() agrees with normalize_ar"),
        ("\u0645\u064F\u062D\u064E\u0645\u0651\u064E\u062F",
         "\u0645\u062D\u0645\u062F", "full vocalization goes"),
        ("\u0660\u0669", "\u0660\u0669",
         "Arabic-Indic digits are NOT marks and must survive"),
        ("\u066E\u066F", "\u066E\u066F",
         "dotless beh and dotless qaf are BASE LETTERS and must survive"),
        ("\u066A\u066B\u066C\u066D", "\u066A\u066B\u066C\u066D",
         "percent, separators and the star must survive"),
        ("\u0627\u0644\u0623\u062F\u0644\u0629",
         "\u0627\u0644\u0623\u062F\u0644\u0629",
         "a hamza CARRIER is a letter, not a mark — only normalize_ar folds it"),
        ("", "", "empty input"),
    ]
    for src, want, why in cases:
        got = normalize.bare(src)
        if got != want:
            failures.append(f"bare({src!r}) = {got!r}, expected {want!r} ({why})")
    # The invariant that made the divergence a bug rather than a wart: whatever
    # bare() strips, normalize_ar must strip too, or the worklist keys a word
    # under one form while the lexicon keys it under another.
    for src, _, _ in cases:
        if cluster.normalize_ar(normalize.bare(src)) != cluster.normalize_ar(src):
            failures.append(f"bare() and normalize_ar disagree on {src!r}")
    return failures


def check_ar_word() -> list[str]:
    """The word class must swallow marks (or a šaddah splits one word into two
    lexicon keys) and must not swallow the comma or the digits (or a punctuated
    word keys separately from its bare form)."""
    failures = []
    cases = [
        ("\u0627\u0644\u062A\u0635\u0648\u0651\u0641",
         ["\u0627\u0644\u062A\u0635\u0648\u0651\u0641"],
         "a marked word is ONE token"),
        ("\u0643\u0640\u062A\u0627\u0628", ["\u0643\u0640\u062A\u0627\u0628"],
         "a tatweel does not split a word"),
        ("\u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062A\u060C",
         ["\u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062A"],
         "the Arabic comma is not part of the word"),
        ("\u0643\u062A\u0627\u0628 \u0662\u0661",
         ["\u0643\u062A\u0627\u0628"],
         "an Arabic-Indic numeral is not a word"),
    ]
    for src, want, why in cases:
        got = normalize.AR_WORD.findall(src)
        if got != want:
            failures.append(f"AR_WORD.findall({src!r}) = {got!r}, expected {want!r} ({why})")
    # The class the app is handed must agree with bare() about every character,
    # or the headless gate grades the pipeline against a rule the pipeline does
    # not use — which is exactly the divergence this consolidation removed.
    js = normalize.mark_class_js()
    try:
        rx = re.compile(js)
    except re.error as exc:
        return failures + [f"mark_class_js() is not a valid class: {exc}"]
    for cp in range(0x0600, 0x0700):
        ch = chr(cp)
        if bool(rx.fullmatch(ch)) != (normalize.bare(ch) == ""):
            failures.append(f"mark_class_js() and bare() disagree on U+{cp:04X}")
    return failures


def main() -> int:
    failures = (check("jaro_winkler_similarity", normalize.jaro_winkler_similarity,
                      JARO_WINKLER_CASES)
                + check("jaro_similarity", normalize.jaro_similarity, JARO_CASES)
                + check_properties() + check_bare() + check_ar_word())
    total = len(JARO_WINKLER_CASES) + len(JARO_CASES)
    if failures:
        print(f"FAILED ({len(failures)} of {total} vectors plus properties):")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"OK — {total} reference vectors, the Arabic word/mark vectors, "
          f"and all invariants pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
