"""Extract the Nwyia MS collection table from the source PDF into raw_rows.json.

The PDF stores Arabic glyphs in presentation forms in visual (left-to-right
painted) order. We:
  1. Use pdfplumber.find_tables() to detect cell bboxes.
  2. For each cell, collect chars whose centroid lies inside the bbox, sorted
     by (line, painted x).
  3. Re-segment each line into Arabic vs non-Arabic runs; cluster-reverse the
     Arabic runs (so combining marks stay with their bases) and NFKC-normalize
     the whole string to fold presentation forms.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

# Project root is the parent of this scripts/ directory.
ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT.parent / "Nwyia_MSCollection.pdf"   # source PDF lives alongside the project
OUT_PATH = ROOT / "source" / "raw_rows.json"

HEADER_CELLS = {"Ville", "Bibliothèque", "Num. Ms.", "Titre", "Auteur", "COTE"}

# Match Arabic blocks INCLUDING presentation forms (FB50-FDFF, FE70-FEFF).
ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def is_arabic(ch: str) -> bool:
    return bool(ARABIC_RE.match(ch))


def cluster_reverse(text: str) -> str:
    """Reverse text while keeping combining marks attached to their base."""
    clusters: list[str] = []
    cur = ""
    for ch in text:
        if unicodedata.combining(ch) and cur:
            cur += ch
        else:
            if cur:
                clusters.append(cur)
            cur = ch
    if cur:
        clusters.append(cur)
    return "".join(reversed(clusters))


def visual_to_logical(text: str) -> str:
    """Convert visually-painted line text to logical reading order.

    Splits on Arabic vs non-Arabic runs (whitespace flows with neighbors),
    cluster-reverses each Arabic run, then NFKC-normalizes the result.
    """
    if not text:
        return ""
    # Walk chars, accumulate runs.
    runs: list[tuple[str, str]] = []  # (kind, content); kind in {"A","X"}
    cur_kind = None
    cur = ""
    for ch in text:
        if is_arabic(ch) or (unicodedata.combining(ch) and cur_kind == "A"):
            kind = "A"
        elif ch.isspace():
            kind = cur_kind or "X"
        else:
            kind = "X"
        if cur_kind is None:
            cur_kind = kind
            cur = ch
        elif kind == cur_kind:
            cur += ch
        else:
            runs.append((cur_kind, cur))
            cur_kind = kind
            cur = ch
    if cur:
        runs.append((cur_kind, cur))

    out = []
    for kind, content in runs:
        if kind == "A":
            out.append(cluster_reverse(content))
        else:
            out.append(content)
    joined = "".join(out)
    return unicodedata.normalize("NFKC", joined)


def collect_cell_text(page, bbox) -> str:
    """Gather chars inside bbox, group by line, reconstruct each line."""
    x0, y0, x1, y1 = bbox
    in_cell = []
    for c in page.chars:
        cx = (c["x0"] + c["x1"]) / 2
        cy = (c["top"] + c["bottom"]) / 2
        if x0 - 0.5 <= cx <= x1 + 0.5 and y0 - 0.5 <= cy <= y1 + 0.5:
            in_cell.append(c)
    if not in_cell:
        return ""
    # Group into lines by 'top' (rounded for tolerance).
    in_cell.sort(key=lambda c: (round(c["top"], 0), c["x0"]))
    lines: list[list[dict]] = []
    last_top = None
    for c in in_cell:
        top = round(c["top"], 0)
        if last_top is None or abs(top - last_top) > 2:
            lines.append([c])
            last_top = top
        else:
            lines[-1].append(c)
    line_strs = []
    for line in lines:
        text = "".join(c["text"] for c in line)
        line_strs.append(visual_to_logical(text))
    return " ".join(s for s in (s.strip() for s in line_strs) if s)


def is_header_row(cells: list[str]) -> bool:
    nonempty = [c for c in cells if c]
    return bool(nonempty) and any(c in HEADER_CELLS for c in nonempty)


# The Word table renders one logical column as three sub-cells. The parent cell
# bbox sits at indices 0, 3, 6, 9, 12, 15 within each row. The English field
# names below are the project's canonical keys; `shelfmark_raw` is the unsplit
# "Num. Ms." cell (normalize.py splits it into shelfmark + folios).
COL_INDICES = [0, 3, 6, 9, 12, 15]
COL_NAMES = ["city", "library", "shelfmark_raw", "title", "author", "archive"]


def extract() -> list[dict]:
    rows: list[dict] = []
    # Vertical merges in the printed table leave city/library blank on
    # continuation rows. We forward-fill, but RESET the library whenever a new
    # non-blank city appears, so one city's library cannot bleed into the next
    # city's blank rows (the old code leaked e.g. Bankipore's library into
    # Berlin entries).
    last_city = ""
    last_library = ""

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            for table in tables:
                trows = table.rows
                if not trows:
                    continue
                # Filter to tables whose first row contains the column headers
                # (they sit in the inner sub-cell of each 3-cell merge: 1,4,7,10,13,16).
                header_text = " ".join(
                    collect_cell_text(page, cell)
                    for cell in trows[0].cells if cell
                )
                if not all(h in header_text for h in ("Ville", "Titre", "COTE")):
                    continue
                for trow in trows[1:]:
                    cells_bbox = trow.cells
                    if len(cells_bbox) < 16:
                        continue
                    values = [
                        collect_cell_text(page, cells_bbox[i]) if cells_bbox[i] else ""
                        for i in COL_INDICES
                    ]
                    city, library, shelfmark_raw, title, author, archive = values
                    if city:
                        # New city => the library context resets; a blank library
                        # on this row should NOT inherit the previous city's value.
                        if city != last_city:
                            last_library = ""
                        last_city = city
                    else:
                        city = last_city
                    if library:
                        last_library = library
                    else:
                        library = last_library
                    if not any([shelfmark_raw, title, author, archive]):
                        continue
                    rows.append({
                        "page": page_num,
                        "city": city,
                        "library": library,
                        "shelfmark_raw": shelfmark_raw,
                        "title": title,
                        "author": author,
                        "archive": archive,
                    })
    return rows


def main() -> int:
    rows = extract()
    for idx, row in enumerate(rows, start=1):
        row["id"] = f"r{idx:04d}"
    OUT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Wrote {len(rows)} rows to {OUT_PATH}")
    blanks = sum(1 for r in rows if not r["author"])
    print(f"  rows with empty author: {blanks}")
    print(f"  distinct cities: {len({r['city'] for r in rows if r['city']})}")
    print(f"  distinct libraries: {len({r['library'] for r in rows if r['library']})}")
    for r in rows[:6]:
        print(f"  sample: {r['city']!r:18} | {r['library']!r:18} | {r['title']!r:40} | {r['author']!r:25} | {r['archive']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
