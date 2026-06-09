"""Harvest the user's confirmed adjudications into authority.json.

cluster.py reads authority.json so re-running the pipeline preserves the
hand-curated canonical names, transliterations, and cluster groupings instead of
reverting to mechanical guesses. Run it after exporting data.json from the app:

    python3 harvest_authority.py [path/to/adjudicated/data.json]

Defaults to ~/Downloads/data.json. Writes authority.json next to this script.

What it captures:
  * clusters          — cluster_id → {canonical_ar, canonical_translit, user_confirmed}
  * variant_to_cluster — normalized author string → cluster_id (from row assignments)
  * row_overrides     — per-row non-cluster field edits (e.g. a corrected city)
It also applies NAMED_MERGES — merges the app couldn't perform when the export was
made (it had no merge button), expressed as variant → target cluster.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cluster  # for normalize_ar

# Project root is the parent of this scripts/ directory.
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path.home() / "Downloads" / "data.json"
BASE_PATH = ROOT / "data" / "data.json"   # the generated (pre-adjudication) baseline
OUT_PATH = ROOT / "data" / "authority.json"

# Merges that the app could not do at export time (no merge action existed),
# keyed by raw author variant → target cluster_id. Distinct homonyms are kept
# apart: ʿAbd al-Qādir al-Jīlānī (c070) vs ʿAbd al-Karīm al-Jīlī (c043).
NAMED_MERGES = {
    "محمد بن علي الاندلسي": "c005",   # Ibn al-ʿArabī
    "عبد القادر الكيلاني": "c070",    # ʿAbd al-Qādir al-Jīlānī (= al-Jīlī = al-Kīlānī)
    "عبد الكريم الكيلاني": "c043",    # ʿAbd al-Karīm al-Jīlī (a different person)
}

OVERRIDE_FIELDS = ["city", "library", "shelfmark", "folios", "archive",
                   "title_translit", "title_translation",
                   "author_translit", "author_translation",
                   "catalog_note", "work_url",
                   "pub_status", "pub_citation", "discrepancy_note"]


def clean(s: str) -> str:
    return (s or "").replace("\xa0", " ").strip()


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else DEFAULT_SRC
    if not src.exists():
        print(f"Adjudicated file not found: {src}")
        return 1
    data = json.loads(src.read_text())
    rows = data["rows"]
    norm = cluster.normalize_ar

    # cluster_id → canonical metadata (drop phantom, id-less entries).
    by_id = {c["cluster_id"]: c for c in data["clusters"] if c.get("cluster_id")}

    # normalized author string → cluster_id, from current row assignments.
    v2c: dict[str, str] = {}
    conflicts: dict[str, set[str]] = {}
    for r in rows:
        cid = r.get("author_cluster_id", "")
        a = (r.get("author", "") or "").strip()
        if not cid or not a:
            continue
        n = norm(a)
        if n in v2c and v2c[n] != cid:
            conflicts.setdefault(n, set()).update({v2c[n], cid})
        v2c[n] = cid
    for variant, cid in NAMED_MERGES.items():
        v2c[norm(variant)] = cid

    # Metadata only for clusters that will actually hold rows.
    clusters_out = {}
    for cid in sorted(set(v2c.values())):
        c = by_id.get(cid, {})
        clusters_out[cid] = {
            "canonical_ar": clean(c.get("canonical_ar", "")),
            "canonical_translit": clean(c.get("canonical_translit", "")),
            "authorities": c.get("authorities", []),  # [{source,title,url}, …]
            "user_confirmed": bool(c.get("user_confirmed", False)),
        }

    # Row-level field edits, diffed against the generated baseline.
    overrides = {}
    if BASE_PATH.exists():
        base = {r["id"]: r for r in json.loads(BASE_PATH.read_text())["rows"]}
        for r in rows:
            b = base.get(r["id"], {})
            ov = {f: r.get(f, "") for f in OVERRIDE_FIELDS
                  if (r.get(f, "") or "") != (b.get(f, "") or "")}
            if ov:
                overrides[r["id"]] = ov

    authority = {
        "source": str(src),
        "clusters": clusters_out,
        "variant_to_cluster": v2c,
        "row_overrides": overrides,
    }
    OUT_PATH.write_text(json.dumps(authority, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT_PATH}: {len(clusters_out)} clusters, "
          f"{len(v2c)} variant→cluster, {len(overrides)} row overrides")
    for variant, cid in NAMED_MERGES.items():
        print(f"  merge: {variant!r} → {cid} ({clusters_out.get(cid, {}).get('canonical_translit','?')})")
    if conflicts:
        print("  WARNING — one author string maps to multiple clusters:")
        for n, ids in conflicts.items():
            print(f"    {n!r}: {sorted(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
