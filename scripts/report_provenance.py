"""Which transliterations are your own, and which are machine compositions?

The app can pre-fill a field when every word of the source already has a
transliteration you confirmed elsewhere. Accepting that suggestion is a real
decision, but it is not the same act as reading the Arabic and writing the line
out — and once both are sitting in data.json they are byte-identical.

So the app records, beside each decision, WHAT IT PROPOSED at the moment the
decision was made. This script derives the classification by COMPARING that
proposal against the committed value. It never asks the app what the human did.

Three outcomes per field:

  accepted     the value equals the proposal — a machine composition of your
               own earlier word-level decisions, confirmed by you
  overridden   a proposal was shown and you wrote something else
  independent  no proposal existed; the line is yours outright

Why the comparison uses the RECORDED proposal and not a freshly recomputed one:
the lexicon grows as you work, so recomputing would answer a different question
("what would the finished lexicon say now?") and would silently reclassify rows
decided early, when it knew less.

Run:  python3 scripts/report_provenance.py [--field title_translit] [--list]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "data.json"
AUTHORITY = ROOT / "data" / "authority.json"

ACCEPTED, OVERRIDDEN, INDEPENDENT = "accepted", "overridden", "independent"


def classify(value: str, proposal: str | None) -> str:
    """Provenance is a comparison, never an event that was observed."""
    if proposal is None:
        return INDEPENDENT
    return ACCEPTED if value == proposal else OVERRIDDEN


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} is not valid JSON: {e}") from e


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--field", default="title_translit",
                    help="row field to report on (default: title_translit)")
    ap.add_argument("--list", action="store_true",
                    help="list every row, not just the totals")
    args = ap.parse_args()

    data = load(DATA)
    proposals = load(AUTHORITY).get("machine_suggestions", {})

    rows = [r for r in data.get("rows", [])
            if (r.get(args.field) or "").strip()]
    if not rows:
        print(f"No row carries a value for {args.field!r} yet — nothing to report.")
        return 0

    tally, listed = Counter(), []
    for r in rows:
        value = (r[args.field] or "").strip()
        proposal = (proposals.get(r["id"]) or {}).get(args.field)
        verdict = classify(value, proposal)
        tally[verdict] += 1
        listed.append((r["id"], verdict, value, proposal))

    total = len(rows)
    print(f"{args.field}: {total} filled\n")
    for verdict in (INDEPENDENT, ACCEPTED, OVERRIDDEN):
        n = tally[verdict]
        print(f"  {verdict:12} {n:4}  {100 * n / total:5.1f}%")

    if tally[ACCEPTED]:
        print(f"\n  Note: the {tally[ACCEPTED]} accepted are compositions of word-level"
              "\n  decisions you made elsewhere — confirmed, but not independently"
              "\n  written. Say so if the count is reported as hand-transliterated.")

    if args.list:
        print()
        for rid, verdict, value, proposal in listed:
            line = f"  {rid}  {verdict:12} {value}"
            if verdict == OVERRIDDEN:
                line += f"   [proposed: {proposal}]"
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
