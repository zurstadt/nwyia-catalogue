"""Build the word-level transliteration worklist.

Transliterating 144 remaining titles means writing the same words over and over:
they contain only ~251 distinct Arabic words, and 69 of those are already settled.
This emits one entry per UNSETTLED word, ordered by how many titles it unlocks, so
the highest-leverage decisions come first.

Each entry carries the titles the word occurs in, with the already-known words
rendered — the annotator decides a word while looking at the contexts that word has
to serve, which is the only way to catch one that needs two forms (a construct
qaṣīdat beside an absolute qaṣīda).

Reads data/data.json; writes review/translit_words.json. Never writes data/.

    python3 scripts/build_word_worklist.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cluster  # noqa: E402  — reuse the pipeline's Arabic normalizer

DATA = ROOT / "data" / "data.json"
OUT = ROOT / "review" / "translit_words.json"
# Arabic letters AND the combining marks, but not punctuation or digits. Two traps
# here, both of which split one word into two lexicon keys that never get filled:
# the block ؀-ۿ contains the comma ، (U+060C), so «الاشارات،» keyed separately from
# «الاشارات»; and excluding the marks splits on a shadda, so «التصوّف» became «التصو».
# normalize_ar strips the marks afterwards, so they must be matched, not excluded.
ARABIC = re.compile(r"[\u0621-\u065F\u0670-\u06D3]+")


def words_of(title: str) -> list[str]:
    """Arabic word tokens, normalized the way the app's lexicon keys them."""
    return [cluster.normalize_ar(w) for w in ARABIC.findall(title or "")]


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    clusters = {c["cluster_id"]: c for c in data["clusters"]}
    modern = {k for k, c in clusters.items() if c.get("category") == "modern"}
    rows = [r for r in data["rows"] if r.get("author_cluster_id") not in modern]

    # The lexicon as the pipeline would derive it: a pair is learned ONLY where the
    # Arabic and Latin token counts agree, so an ambiguous pairing is skipped rather
    # than guessed. Same rule as the app — one definition of "known".
    lex: dict[str, str] = {}
    for r in rows:
        ar, lat = words_of(r.get("title") or ""), (r.get("title_translit") or "").split()
        if ar and len(ar) == len(lat):
            for a, l in zip(ar, lat):
                lex.setdefault(a, l)

    todo = [r for r in rows
            if (r.get("title") or "").strip()
            and not (r.get("title_translit") or "").strip()
            and ARABIC.search(r.get("title") or "")]

    occurrences: dict[str, list[dict]] = defaultdict(list)
    freq: Counter = Counter()
    for r in todo:
        ws = words_of(r.get("title") or "")
        for w in set(ws):
            freq[w] += 1
        for w in set(ws):
            occurrences[w].append({
                "row": r["id"],
                "title": r.get("title") or "",
                # The title with what is already settled filled in, so the annotator
                # sees the sentence this word has to fit into.
                "gloss": " ".join(lex.get(x, "…") for x in ws),
                "author": (clusters.get(r.get("author_cluster_id"), {})
                           .get("canonical_translit") or ""),
            })

    unsettled = [w for w in freq if w not in lex]
    items = []
    for w in sorted(unsettled, key=lambda x: (-freq[x], x)):
        occ = occurrences[w]
        items.append({
            "id": w,                       # the word IS the stable id
            "word": w,
            "titles": freq[w],
            # How many titles this word alone is blocking — i.e. titles where every
            # OTHER word is already known. Answering one of these completes a title.
            "unlocks": sum(1 for o in occ
                           if all(x in lex or x == w for x in words_of(o["title"]))),
            "occurrences": occ[:8],
            "more": max(0, len(occ) - 8),
        })

    out = {
        "schema_version": 1,
        "generated_from": "data/data.json",
        "counts": {"titles_todo": len(todo), "words_unsettled": len(items),
                   "words_known": len(lex)},
        "known_sample": dict(sorted(lex.items())[:40]),
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    unlock = sum(1 for i in items if i["unlocks"])
    print(f"{len(todo)} titles still need a transliteration")
    print(f"  distinct unsettled words : {len(items)}")
    print(f"  already settled          : {len(lex)}")
    print(f"  words that alone complete a title: {unlock}")
    print(f"\nTop by leverage:")
    for i in items[:12]:
        print(f"   {i['word']:14} in {i['titles']:3} titles, completes {i['unlocks']}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
