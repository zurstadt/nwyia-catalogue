#!/usr/bin/env python3
"""OpenRefine-style clustering of similar author names → candidate-merge worklist.

Surfaces groups of author clusters whose names are similar enough that they may be
the SAME person split across two clusters (or a bare/heuristic cluster that matches
an already-identified one). The user adjudicates each group in the companion app
`review/name_clusters.html` and exports confirmed merges.

Modelled on OpenRefine's clustering: several independent keying / distance methods,
each proposing links; links are unioned into connected components (the "clusters of
similar names"). Methods implemented:

  1. fingerprint        — token-sort key on the transliteration (OpenRefine default)
  2. fingerprint-ar     — token-sort key on the Arabic, with the project's
                          orthographic folding (ج↔ك, -ī/-ānī …)
  3. ngram (n=2)        — character-bigram fingerprint on the transliteration
  4. levenshtein        — near-neighbour on the whole normalized string (tight)
  5. shared-rare-token  — clusters sharing a distinctive nisbah/ism (df ≤ 3),
                          which catches spelling variants of the same nasab

Reads  data/data.json   (immutable — never written)
Writes review/name_clusters.json   (the worklist the HTML app fetches)

Run:  python3 scripts/name_cluster.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import cluster  # reuse normalize_ar + fold_orthography (SYNONYM_TOKENS)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "data.json"
OUT = ROOT / "review" / "name_clusters.json"

# Transliteration tokens that carry no identifying weight (particles / connectors).
STOP_TRANSLIT = {
    "al", "b", "bn", "ibn", "abu", "abi", "abd", "umm", "bint", "ben", "el",
    "ed", "of", "the", "and", "le", "la",
}
# Arabic particles (post-normalization) to drop from the Arabic key.
STOP_AR = {"بن", "ابن", "ابو", "ابي", "ام", "بنت", "عبد", "ال"}

# Common given-names (ism), kunya and laqab elements. A SINGLE such token is not
# distinctive enough to propose a group — half the corpus is a Muḥammad or a Ṣadr
# al-Dīn. They are skipped as single-token / prefix keys, but a TWO-token key that
# happens to include one (the bigram "ʿAfīf al-Dīn") is still distinctive and is
# kept. So "ʿAfīf al-Dīn" surfaces as a pair while "Ḥasan" alone does not.
COMMON_ISM = {
    "muhammad", "ahmad", "ali", "hasan", "husayn", "husain", "mahmud", "ibrahim",
    "ismail", "ismael", "yusuf", "umar", "uthman", "qasim", "sulayman", "salih",
    "yahya", "jafar", "hamza", "dawud", "davud", "zayd", "zaid", "abbas", "bakr",
    "said", "saeed", "khalid", "musa", "isa", "harun", "idris", "nuh", "yaqub",
    "ishaq", "ayyub", "sufyan", "talha", "anas", "amr", "amir", "faraj", "farag",
    "nasr", "mansur", "qadir", "karim", "majid", "magid", "wahhab", "ghaffar",
    "ghani", "hamid", "rahman", "rahim", "salam", "razzaq", "latif", "aziz",
    "jabbar", "malik", "hadi",
}
# kunya / relational / honorific (laqab) elements. Kept apart from the isms because
# a laqab COMPOUND ("ʿAfīf al-Dīn") is a distinctive shared key worth a group, even
# though each element is itself common — whereas a pair of bare isms ("ʿAlī Aḥmad")
# is just a name coincidence.
COMMON_LAQAB = {
    "allah", "abdallah", "wali", "dunya", "din", "nur", "taj", "shams", "jalal",
    "najm", "sharaf", "izz", "afif", "qutb", "muhyi", "jamal", "kamal", "zayn",
    "badr", "sayf", "fakhr", "shihab", "burhan", "imam", "shaykh", "sadr", "baha",
    "ala", "alaa", "sad", "saad", "najib", "hakim", "dawla",
}
COMMON = COMMON_ISM | COMMON_LAQAB
# Same idea for the Arabic key (bare forms; ar_tokens already strips ال and عبد).
AR_COMMON = {
    "محمد", "احمد", "علي", "حسن", "حسين", "عباس", "بكر", "سعيد", "قاسم", "جعفر",
    "محمود", "ابراهيم", "اسماعيل", "عمر", "عثمان", "يوسف", "داود", "سليمان",
    "صالح", "يحيي", "حمزه", "زيد", "خالد", "موسي", "عيسي", "قادر", "كريم", "مجيد",
    "الله", "نور", "دين", "علاء", "عفيف", "هادي", "جمال", "كمال", "شرف",
    "نصر", "فرج", "منصور", "حميد", "رحمن", "عزيز",
}


# ── normalization ────────────────────────────────────────────────────────────
# DIN-31635 letters that stand for an Arabic consonant English renders as a
# DIGRAPH. These must be expanded BEFORE diacritic stripping — otherwise ḫ (خ)
# and ḥ (ح) both collapse to a bare "h" and al-Ḫarrāz wrongly merges with
# al-Ḥarrānī. (Plain ḥ/ṣ/ḍ/ṭ/ẓ have no digraph and do reduce to h/s/d/t/z.)
DIGRAPHS = {
    "ḫ": "kh", "ḵ": "kh", "ḡ": "gh", "ġ": "gh", "ṯ": "th", "ḏ": "dh",
    "š": "sh", "ǧ": "j", "ž": "zh", "č": "ch",
}


def strip_diacritics(s: str) -> str:
    """DIN-31635 → bare Latin, preserving consonant digraphs (kh, gh, th, dh, sh)."""
    s = (s or "").lower()
    for k, v in DIGRAPHS.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def translit_tokens(s: str) -> list[str]:
    s = strip_diacritics(s or "").lower()
    s = s.replace("ʾ", "").replace("ʿ", "").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    toks = []
    for raw in re.split(r"[\s-]+", s):
        t = raw.strip()
        if not t:
            continue
        # fold a leading article so "al-tirmidhi" ≡ "tirmidhi"
        if t.startswith("al") and len(t) > 3 and t not in STOP_TRANSLIT:
            t = t[2:]
        toks.append(t)
    return toks


def content_translit(s: str) -> list[str]:
    return [t for t in translit_tokens(s) if t not in STOP_TRANSLIT and len(t) > 1]


def ar_tokens(s: str) -> list[str]:
    norm = cluster.fold_orthography(cluster.normalize_ar(s or ""))
    out = []
    for t in norm.split():
        if t.startswith("ال") and len(t) > 3:
            t = t[2:]
        if t and t not in STOP_AR:
            out.append(t)
    return out


# ── edit distance ────────────────────────────────────────────────────────────
def lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def main() -> None:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    clusters = d["clusters"]
    rows = d["rows"]

    # Sample work titles per cluster — context for the adjudicator.
    titles = defaultdict(list)
    for r in rows:
        cid = r.get("author_cluster_id")
        if cid and r.get("title") and len(titles[cid]) < 4:
            titles[cid].append(r["title"])

    by_id = {c["cluster_id"]: c for c in clusters}
    # The strings each cluster is keyed on (canonical + fullest romanized name).
    rep_translit = {c["cluster_id"]: (c.get("canonical_translit") or c.get("full_name") or "")
                    for c in clusters}
    rep_ar = {c["cluster_id"]: c.get("canonical_ar", "") for c in clusters}

    # ── blocking keys → candidate groups (OpenRefine key-collision, NO union) ──
    # Each shared key proposes ONE group = the clusters carrying it. We deliberately
    # do NOT union groups together: union-find blobbed unrelated people whenever one
    # cluster bridged two signals (the two "ʿAfīf al-Dīn" clusters got dragged in
    # with al-Jīlī via a shared "Karīm"). Keeping every signal a separate candidate
    # group means an obvious pair surfaces cleanly on its own. A key shared by more
    # than MAX_DF clusters is too common to be distinctive and is dropped — so we
    # rely on rarity, not hand-maintained given-name stoplists.
    MAX_DF = 4

    key_clusters: dict[str, set[str]] = defaultdict(set)
    key_label: dict[str, str] = {}

    def add_key(k: str, label: str, cid: str) -> None:
        key_clusters[k].add(cid)
        key_label.setdefault(k, label)

    for cid in by_id:
        # toks_full keeps short laqab tokens (≥3: "dīn", "izz") so bigrams like
        # "ʿafīf dīn" form; single/prefix keys use the ≥4 non-common subset.
        toks_full = [t for t in content_translit(rep_translit[cid]) if len(t) >= 3]
        for t in toks_full:
            if len(t) >= 4 and t not in COMMON:
                add_key("t:" + t, t, cid)              # whole content token (nisbah)
                add_key("p:" + t[:4], t[:4] + "…", cid)  # nisbah stem (ḥarrā…)
        for a, b in zip(toks_full, toks_full[1:]):
            # a bigram of two bare given-names ("ʿAlī Aḥmad") is a coincidence, not
            # a shared identity — skip it; keep laqab compounds ("ʿAfīf al-Dīn").
            if a in COMMON_ISM and b in COMMON_ISM:
                continue
            add_key("b:" + a + " " + b, a + " " + b, cid)   # adjacent bigram (ʿafīf dīn)
        for t in ar_tokens(rep_ar[cid]):
            if len(t) >= 3 and t not in AR_COMMON:
                add_key("a:" + t, t, cid)              # Arabic content token

    # Levenshtein near-neighbour on the whole normalized string — catches spelling
    # variants that share no clean token (al-Ḥarrālī ≈ al-Ḥarrānī).
    norm_str = {cid: " ".join(content_translit(rep_translit[cid])) for cid in by_id}
    sids = [cid for cid in by_id if norm_str[cid]]
    for a, b in combinations(sids, 2):
        sa, sb = norm_str[a], norm_str[b]
        dist = lev(sa, sb)
        if dist and dist <= 2 and dist / max(len(sa), len(sb)) <= 0.25:
            k = "lev:" + "|".join(sorted((a, b)))
            add_key(k, "≈ spelling", a)
            add_key(k, "≈ spelling", b)

    # Collapse to unique member-sets: identical member-sets are one group, labelled
    # by every key that produced them.
    members_to_keys: dict[frozenset, list[str]] = defaultdict(list)
    for k, cids in key_clusters.items():
        if 2 <= len(cids) <= MAX_DF:
            members_to_keys[frozenset(cids)].append(k)

    def member(cid):
        c = by_id[cid]
        return {
            "cluster_id": cid,
            "canonical_ar": c.get("canonical_ar", ""),
            "canonical_translit": c.get("canonical_translit", ""),
            "full_name": c.get("full_name", ""),
            "dates": c.get("dates", ""),
            "count": c.get("count", 0),
            "user_confirmed": bool(c.get("user_confirmed", False)),
            "category": c.get("category", ""),
            "variants": c.get("variants", []),
            "sample_titles": titles.get(cid, []),
            "authorities": [a.get("source", "") for a in c.get("authorities", [])],
        }

    worklist = []
    for member_set, keys in members_to_keys.items():
        ids = sorted(member_set)
        labels = sorted({key_label[k] for k in keys}, key=lambda s: (-len(s), s))
        confirmed = [m for m in ids if by_id[m].get("user_confirmed")]
        keep = sorted(ids, key=lambda m: (
            not by_id[m].get("user_confirmed"),
            not by_id[m].get("full_name"),
            -by_id[m].get("count", 0),
        ))[0]
        worklist.append({
            "group_id": "g" + "_".join(ids),
            "label": labels[0],
            "members": sorted((member(m) for m in ids),
                              key=lambda m: (-m["count"], m["cluster_id"])),
            "methods": labels,
            "n_confirmed": len(confirmed),
            "suggested_keep": keep,
        })

    # Easy, high-value cases first: pairs involving an unidentified (bare) cluster,
    # then small groups, then those whose shared key is a fuller (multi-token) name.
    def priority(g):
        has_bare = any(not m["full_name"] for m in g["members"])
        return (
            not has_bare,                 # identification leads first
            len(g["members"]),            # tight pairs before larger groups
            -len(g["label"]),             # richer shared name first
        )
    worklist.sort(key=priority)

    out = {
        "schema_version": "1.0",
        "source": "data/data.json",
        "n_clusters_total": len(clusters),
        "n_groups": len(worklist),
        "n_clusters_in_groups": sum(len(g["members"]) for g in worklist),
        "methods_legend": {
            "shared name / nisbah": "clusters sharing a distinctive token (e.g. al-Nūrī), "
                                    "rare across the corpus (≤ 4 clusters)",
            "shared prefix": "share a nisbah stem (ḥarrā… joins al-Ḥarrālī & al-Ḥarrānī)",
            "shared bigram": "share two adjacent name tokens (ʿAfīf al-Dīn)",
            "≈ spelling": "near-identical names by edit distance",
        },
        "groups": worklist,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(worklist)} candidate groups "
          f"({out['n_clusters_in_groups']} cluster-slots) → {OUT}")
    for g in worklist:
        names = " | ".join(m["canonical_translit"] or m["cluster_id"] for m in g["members"])
        print(f"  [{g['label'][:22]:22}] {names}")


if __name__ == "__main__":
    main()
