"""Cluster the author names and emit data.json for the search app.

Strategy:
  * Normalize each Arabic name (strip diacritics/tatweel, fold alif/yāʾ/tāʾ
    marbūṭa variants).
  * Build clusters with union-find using two rules:
      (a) identical normalized form, or
      (b) Jaro-Winkler similarity > 0.92 on normalized form (catches small
          spelling variants), or
      (c) one is a token-subset of the other AND they share a distinctive
          token (catches "السلمي" ↔ "أبو عبد الرحمن السلمي").
  * For each cluster, pick the longest variant as canonical Arabic and attach
    a transliteration from CURATED_TRANSLITS, falling back to a mechanical
    DIN 31635 transliteration as a placeholder for the user to edit.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import normalize

# Project root is the parent of this scripts/ directory.
ROOT = Path(__file__).resolve().parent.parent
ROWS_PATH = ROOT / "source" / "raw_rows.json"
OUT_PATH = ROOT / "data" / "data.json"
# Harvested adjudications (optional). When present, its curated canonical names,
# transliterations, and groupings take precedence over the heuristic clusterer so
# re-running the pipeline preserves the user's work. Produced by harvest_authority.py.
AUTH_PATH = ROOT / "data" / "authority.json"

# Adjudicator-side row fields that don't come from the PDF extraction. These are
# the defaults a freshly-generated row carries *before* any override is applied
# (pub_status starts at "unknown"; the rest empty). Defined here as the single
# source of truth so harvest_authority.py can reconstruct the exact pre-override
# baseline it diffs against — keeping the override round-trip idempotent.
ROW_FIELD_DEFAULTS = {
    "pub_status": "unknown",
    "pub_citation": "",
    # Where the citation came from, so a relayed one is not mistaken for a checked
    # one. "catalogue" = copied from a holding library's own notice and NOT verified;
    # "bibliography" = from a published bibliography or reference work;
    # "edition" = taken from the edition itself. Empty means simply unrecorded —
    # it is not a claim that the citation is unsourced.
    "pub_source": "",
    "discrepancy_note": "",
    "title_translit": "",
    "title_translation": "",
    "author_translit": "",
    "author_translation": "",
    "catalog_note": "",
    "work_url": "",
}

# Curated DIN 31635 (with Farrell modifications) for the most common figures.
# All other clusters get a mechanical fallback; the user will correct in-app.
CURATED_TRANSLITS = {
    "الترمذي": "al-Tirmiḏī",
    "السلمي": "al-Sulamī",
    "ابو عبد الرحمن السلمي": "Abū ʿAbd al-Raḥmān al-Sulamī",
    "القونوي": "al-Qūnawī",
    "صدر الدين القونوي": "Ṣadr al-Dīn al-Qūnawī",
    "ابن عطاء الله": "Ibn ʿAṭāʾ Allāh",
    "ابن ابي الدنيا": "Ibn Abī al-Dunyā",
    "ابن عربي": "Ibn ʿArabī",
    "الحلاج": "al-Ḥallāǧ",
    "القشيري": "al-Qušayrī",
    "النفري": "al-Niffarī",
    "بولس نويا": "Paul Nwyia",
    "ابن سودكين": "Ibn Sawdakīn",
    "ابن سودكني": "Ibn Sawdakīn",
    "الغزالي": "al-Ġazālī",
    "ابن عباد": "Ibn ʿAbbād",
    "الحارث المحاسبي": "al-Ḥāriṯ al-Muḥāsibī",
    "البصري": "al-Baṣrī",
    "حسن البصري": "al-Ḥasan al-Baṣrī",
    "الخركوشي": "al-Ḫarkūšī",
    "شقيق البلخي": "Šaqīq al-Balḫī",
    "ميشال الار": "Michel Allard",
    "جورج المقدسي": "George Makdisi",
    "ابو نصر الفارابي": "Abū Naṣr al-Fārābī",
    "النيسابوري": "al-Naysābūrī",
    "جعفر الصادق": "Ǧaʿfar al-Ṣādiq",
    "ابو طالب المكي": "Abū Ṭālib al-Makkī",
    "ابو مدين شعيب": "Abū Madyan Šuʿayb",
    "ابن عجيبه": "Ibn ʿAǧība",
    "ابن سينا": "Ibn Sīnā",
    "روزبهان الشيرازي": "Rūzbihān al-Šīrāzī",
    "روزبهان البقلي": "Rūzbihān al-Baqlī",
    "صدر الدين الشيرازي": "Ṣadr al-Dīn al-Šīrāzī",
    "داود بن محمود القيصري": "Dāwūd b. Maḥmūd al-Qayṣarī",
    "ابن الفارض": "Ibn al-Fāriḍ",
    "التستري": "al-Tustarī",
    "ابو سعيد الخراز": "Abū Saʿīd al-Ḫarrāz",
    "ابن سبعين": "Ibn Sabʿīn",
    "التلمساني": "al-Tilimsānī",
    "الماتريدي": "al-Māturīdī",
    "المتريدي": "al-Māturīdī",
    "الجويني": "al-Ǧuwaynī",
    "فخر الدين الرازي": "Faḫr al-Dīn al-Rāzī",
    "فخر الدين ابو الحسن علي بن احمد حرالي": "Faḫr al-Dīn Abū al-Ḥasan ʿAlī b. Aḥmad al-Ḥarrālī",
    "ابو حيان الغرناطي": "Abū Ḥayyān al-Ġarnāṭī",
    "الكتاني": "al-Kattānī",
    "محمد الكتاني": "Muḥammad al-Kattānī",
    "ابن قسي": "Ibn Qasī",
    "الجامي": "al-Ǧāmī",
    "عبد الكريم الجيلي": "ʿAbd al-Karīm al-Ǧīlī",
    "محمد بن شعبة الحراني": "Muḥammad b. Šuʿba al-Ḥarrānī",
    "النوري": "al-Nūrī",
    "ابو الحسن النوري": "Abū al-Ḥasan al-Nūrī",
    "ابن خميس": "Ibn Ḫamīs",
    "السمرقندي": "al-Samarqandī",
    "داود الباخلي الاسكندري": "Dāwūd al-Bāḫilī al-Iskandarī",
    "ابن العريف": "Ibn al-ʿArīf",
    "ابو القاسم الجنيد": "Abū al-Qāsim al-Ǧunayd",
    "الكلاباذي": "al-Kalābāḏī",
    "السهروردي": "al-Suhrawardī",
    "ابن الجوزي": "Ibn al-Ǧawzī",
    "ابن غانم المقدسي": "Ibn Ġānim al-Maqdisī",
    "عبد القادر الجيلاني": "ʿAbd al-Qādir al-Ǧīlānī",
    "عبد القادر الكيلاني": "ʿAbd al-Qādir al-Kīlānī",
    "ابن عرب": "Ibn ʿArabī",
    "الفاسي": "al-Fāsī",
    "الشاذلي": "al-Šāḏilī",
    "ارسطو": "Arisṭū (Aristotle)",
    "افلاطون": "Aflāṭūn (Plato)",
    "ابن تيمية": "Ibn Taymiyya",
    "ابو العلاء المعري": "Abū al-ʿAlāʾ al-Maʿarrī",
    "ابن مكزون": "Ibn Makzūn",
    "احمد البوني": "Aḥmad al-Būnī",
    "محمود الكازواني": "Maḥmūd al-Kāzarūnī",
    "القباب": "al-Qabbāb",
    "السنماني": "al-Simnānī",
    "السمناني": "al-Simnānī",
    "ابن باكويه الشيرازي": "Ibn Bākūya al-Šīrāzī",
    "ابو مطيع مكحول النسفي": "Abū Muṭīʿ Makḥūl al-Nasafī",
    "النسفي": "al-Nasafī",
    "الخواص": "al-Ḫawwāṣ",
    "السنوسي": "al-Sanūsī",
    "السنفي": "al-Sanūsī",
    "ابن منور": "Ibn Munawwar",
}

# Simple char-by-char fallback in strict DIN 31635 (ǧ ḏ ṯ ġ ḫ š). Not
# linguistically complete (no case, no sun-letter assimilation); placeholder
# only, for clusters with no curated entry — the user corrects these in-app.
CHAR_TRANSLIT = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "ṯ", "ج": "ǧ", "ح": "ḥ", "خ": "ḫ",
    "د": "d", "ذ": "ḏ", "ر": "r", "ز": "z", "س": "s", "ش": "š", "ص": "ṣ",
    "ض": "ḍ", "ط": "ṭ", "ظ": "ẓ", "ع": "ʿ", "غ": "ġ", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
    "ء": "ʾ", "ؤ": "ʾ", "ئ": "ʾ", " ": " ", "-": "-",
}


# Editorial role tags that may trail an author name, e.g. "جورج المقدسي (محقق)".
ROLE_TRANSLIT = {"محقق": "ed.", "مترجم": "tr.", "جامع": "comp."}


def curated_lookup(norm: str) -> str | None:
    """Curated transliteration for a normalized name, role-tag aware.

    "جورج المقدسي (محقق)" → "George Makdisi (ed.)": strip a trailing parenthetical
    role, look up the bare name, and re-attach the role in translation.
    """
    if norm in CURATED_TRANSLITS:
        return CURATED_TRANSLITS[norm]
    m = re.search(r"\s*\(([^)]*)\)\s*$", norm)
    if m:
        base = norm[: m.start()].strip()
        if base in CURATED_TRANSLITS:
            role = ROLE_TRANSLIT.get(m.group(1).strip())
            return CURATED_TRANSLITS[base] + (f" ({role})" if role else "")
    return None


def mechanical_translit(arabic: str) -> str:
    out = []
    for ch in arabic:
        if ch in CHAR_TRANSLIT:
            out.append(CHAR_TRANSLIT[ch])
        elif ch.isspace():
            out.append(" ")
    s = "".join(out)
    # Collapse "al " → "al-" and capitalize first letter.
    s = re.sub(r"\bal ", "al-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_ar(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ـ", "")
    s = re.sub(r"[آأإٱ]", "ا", s)
    s = s.replace("ى", "ي")
    s = s.replace("ة", "ه")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Orthographic synonym folding (heuristic clustering ONLY — never applied to the
# authority keys, so it can't disturb adjudicated groupings). Whole-token rewrites
# unify spellings of the same nisbah/ism that differ only by interchangeable
# letters — e.g. jīm/kāf in al-Ǧīlānī / al-Kīlānī, or the -ī / -ānī alternation.
# Done token-by-token (not letter-by-letter) so it can't merge unrelated words
# like Ǧamāl vs Kamāl. Extend as new equivalences surface during adjudication.
SYNONYM_TOKENS = {
    "الكيلاني": "الجيلاني",
    "الجيلي": "الجيلاني",
    "الكيلي": "الجيلاني",
    "الجيلانى": "الجيلاني",
}


def fold_orthography(norm: str) -> str:
    """Apply curated whole-token synonym rewrites to a normalized name."""
    return " ".join(SYNONYM_TOKENS.get(t, t) for t in norm.split())


# Kunya particles (post-normalization forms). A differing kunya marks two
# distinct people sharing the same nisbah (e.g. the two Ibn Yazdānyār:
# Abū Ḥafṣ vs Abū Jaʿfar), so it blocks an automatic merge.
KUNYA_PARTICLES = {"ابو", "ام"}


def kunya(name: str) -> str | None:
    """Return the kunya name token (after Abū/Umm), or None."""
    toks = name.split()
    for i, t in enumerate(toks[:-1]):
        if t in KUNYA_PARTICLES:
            return toks[i + 1]
    return None


# Tokens too generic to license a "shared distinctive token" merge.
STOPWORDS = {
    # Filiation / particles.
    "ابن", "ابو", "ام", "ابي", "بن", "بنت", "ال", "الله", "عبد",
    # Frequent ism components & honorifics.
    "الدين", "محمد", "احمد", "علي", "الحسن", "الحسين", "القاسم",
    # Theophoric second elements after ʿAbd — common across many distinct people.
    "الرحمن", "الكريم", "القادر", "العزيز", "الكبير", "الواحد", "الصمد", "الغفار",
}


def distinctive_tokens(name: str) -> set[str]:
    return {t for t in name.split() if t not in STOPWORDS and len(t) > 2}


def find(parent: dict[int, int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def union(parent: dict[int, int], i: int, j: int) -> None:
    ri, rj = find(parent, i), find(parent, j)
    if ri != rj:
        parent[ri] = rj


def build_clusters(norm_to_originals: dict[str, list[str]]) -> list[list[str]]:
    norms = list(norm_to_originals.keys())
    parent = {i: i for i in range(len(norms))}

    # Conservative rule: token-subset + shared distinctive token. The Jaro-Winkler
    # rule over-merges short nisbahs that share frequent letters
    # (al-Baṣrī ↔ al-Nūrī ↔ al-Niffarī all rhyme on ـري); user can merge missed
    # variants in the app, but silently merged distinct people are hard to catch.
    for i in range(len(norms)):
        a = norms[i]
        a_toks = set(a.split())
        a_distinct = distinctive_tokens(a)
        a_kunya = kunya(a)
        for j in range(i + 1, len(norms)):
            b = norms[j]
            b_toks = set(b.split())
            if (a_toks <= b_toks or b_toks <= a_toks) and (a_distinct & distinctive_tokens(b)):
                # Suppress merge if the shorter form looks like a co-attribution
                # ("X - Y") — keep as its own cluster for the user to triage.
                if "-" in a or "-" in b:
                    continue
                # Homonym guard: two explicit, differing kunyas ⇒ distinct people.
                b_kunya = kunya(b)
                if a_kunya and b_kunya and a_kunya != b_kunya:
                    continue
                union(parent, i, j)

    clusters: dict[int, list[str]] = {}
    for i, n in enumerate(norms):
        clusters.setdefault(find(parent, i), []).append(n)
    return list(clusters.values())


def pick_canonical(all_originals: list[str]) -> str:
    """Most frequent variant; on tie the cleanest (fewest chars / orphan marks)."""
    counts = {s: all_originals.count(s) for s in set(all_originals)}
    canonical = max(counts, key=lambda s: (counts[s], -len(s), -sum(1 for c in s if c.isspace())))
    canonical = re.sub(r" [ً-ْٰ]+", "", canonical)
    return re.sub(r"\s+", " ", canonical).strip()


def pick_translit(group: list[str], canonical: str) -> str:
    """Curated translit for any member, else Latin-as-is, else mechanical DIN."""
    for n in group:
        t = curated_lookup(n)
        if t is not None:
            return t
    t = curated_lookup(normalize_ar(canonical))
    if t is not None:
        return t
    if not normalize.has_arabic(canonical):
        return canonical  # modern scholar already in Latin script
    return mechanical_translit(normalize_ar(canonical))


def cluster_confidence(group: list[str]) -> float:
    if len(group) <= 1:
        return 1.0
    sims = [normalize.jaro_winkler_similarity(group[i], group[j])
            for i in range(len(group)) for j in range(i + 1, len(group))]
    return round(min(sims), 3) if sims else 1.0


def main() -> int:
    rows = json.loads(ROWS_PATH.read_text(encoding="utf-8"))

    # Step 0: readable-English places, split shelfmark/folios, tidy Latin authors.
    cities, libs = normalize.unmapped_places(rows)
    rows = normalize.normalize_rows(rows)
    if cities:
        print(f"  NOTE unmapped cities (passed through): {sorted(cities)}")
    if libs:
        print(f"  NOTE unmapped libraries (passed through): {sorted(libs)}")

    # Step 0b: load harvested adjudications (curated names + groupings + overrides).
    authority = json.loads(AUTH_PATH.read_text(encoding="utf-8")) if AUTH_PATH.exists() else {}
    v2c = authority.get("variant_to_cluster", {})
    auth_clusters = authority.get("clusters", {})
    overrides = authority.get("row_overrides", {})
    if authority:
        print(f"  using authority.json: {len(auth_clusters)} clusters, "
              f"{len(v2c)} pinned variants, {len(overrides)} row overrides")
    if overrides:
        rows = [{**r, **overrides.get(r["id"], {})} for r in rows]
        # Neutralize unattributed-author placeholders ("NA") that arrive via an
        # override (normalize_rows already blanks them in the raw pass, but an
        # override is applied on top of that). Keeps anonymous works from seeding
        # a spurious one-row cluster.
        rows = [{**r, "author": normalize.blank_author_placeholder(r.get("author", ""))}
                for r in rows]
        # Safeguard: an edited author that isn't pinned in variant_to_cluster
        # falls through to the heuristic clusterer below and is given a fresh
        # n### id — detaching it from the cluster the user intended. Warn so the
        # operator knows to re-run harvest_authority.py (which re-pins it).
        detached = [(r["id"], (r.get("author", "") or "").strip())
                    for r in rows
                    if "author" in overrides.get(r["id"], {})
                    and (r.get("author", "") or "").strip()
                    and normalize_ar((r.get("author", "") or "").strip()) not in v2c]
        if detached:
            print("  WARNING — edited author(s) not pinned in variant_to_cluster "
                  "(will get a fresh n### cluster; re-run harvest_authority.py):")
            for rid, a in detached:
                print(f"    {rid}: {a!r}")

    # Step 1: bucket originals by normalized form.
    norm_to_originals: dict[str, list[str]] = {}
    for r in rows:
        a = r["author"].strip()
        if not a:
            continue
        norm_to_originals.setdefault(normalize_ar(a), []).append(a)

    # Step 2: partition norms into authority-pinned vs leftover, then cluster.
    norm_to_cid: dict[str, str] = {}
    pinned_groups: dict[str, list[str]] = {}   # cluster_id -> [norms]
    leftover: dict[str, list[str]] = {}
    for n, origs in norm_to_originals.items():
        cid = v2c.get(n)
        if cid:
            norm_to_cid[n] = cid
            pinned_groups.setdefault(cid, []).append(n)
        else:
            leftover[n] = origs

    cluster_meta = []
    # 2a) Authority clusters keep their curated canonical / translit / confirmed flag.
    for cid, group in pinned_groups.items():
        all_originals = [s for n in group for s in norm_to_originals[n]]
        meta = auth_clusters.get(cid, {})
        canonical = meta.get("canonical_ar") or pick_canonical(all_originals)
        translit = meta.get("canonical_translit") or pick_translit(group, canonical)
        entry = {
            "cluster_id": cid,
            "canonical_ar": canonical,
            "canonical_translit": translit,
            "variants": sorted(set(all_originals)),
            "count": len(all_originals),
            "confidence": 1.0,
            "user_confirmed": bool(meta.get("user_confirmed", False)),
        }
        # Carry curated author metadata: fullest name, dates, and authority-control
        # links (Wikidata/VIAF/GND/TDVİA/EI/Wikipedia …).
        if meta.get("full_name"):
            entry["full_name"] = meta["full_name"]
        if meta.get("dates"):
            entry["dates"] = meta["dates"]
        if meta.get("authorities"):
            entry["authorities"] = meta["authorities"]
        # Corpus classification. "modern" marks clusters that are NOT part of the
        # premodern manuscript corpus — Nwyia's own studies, his colleagues'
        # scholarship (Allard, Makdisi, Ritter), and modern authors — so the site
        # can exclude them from manuscript counts and surface them separately.
        if meta.get("category"):
            entry["category"] = meta["category"]
        cluster_meta.append(entry)

    # 2b) Heuristic clusters for everything the authority doesn't cover (new ids).
    #     Bucket leftovers by orthographically-folded key first, so variant
    #     spellings (al-Ǧīlānī / al-Kīlānī / al-Ǧīlī) collapse before clustering.
    folded_to_norms: dict[str, list[str]] = {}
    for n in leftover:
        folded_to_norms.setdefault(fold_orthography(n), []).append(n)
    folded_bucket = {fk: [o for n in ns for o in leftover[n]]
                     for fk, ns in folded_to_norms.items()}
    leftover_clusters = build_clusters(folded_bucket) if folded_bucket else []
    # Number heuristic clusters n000, n001, … but SKIP any id already held by a
    # pinned cluster. Authority-pinned clusters can themselves be n### (a former
    # heuristic cluster the user adjudicated), so naive positional numbering would
    # mint a duplicate cluster_id and collide. Skipping keeps every id unique.
    used_ids = set(pinned_groups)
    next_n = 0
    for group in sorted(leftover_clusters, key=lambda g: -sum(len(folded_bucket[fk]) for fk in g)):
        while f"n{next_n:03d}" in used_ids:
            next_n += 1
        cid = f"n{next_n:03d}"
        used_ids.add(cid)
        next_n += 1
        member_norms = [n for fk in group for n in folded_to_norms[fk]]
        all_originals = [o for fk in group for o in folded_bucket[fk]]
        canonical = pick_canonical(all_originals)
        cluster_meta.append({
            "cluster_id": cid,
            "canonical_ar": canonical,
            "canonical_translit": pick_translit(member_norms, canonical),
            "variants": sorted(set(all_originals)),
            "count": len(all_originals),
            "confidence": cluster_confidence(member_norms),
            "user_confirmed": False,
        })
        for n in member_norms:
            norm_to_cid[n] = cid

    cluster_meta.sort(key=lambda c: -c["count"])

    # Step 3: tag each row with its cluster_id; default the adjudicator-side
    # fields (transliteration, translation, cataloguer comment, identification
    # URL, publication status) that an override may already have filled.
    for r in rows:
        a = r["author"].strip()
        r["author_cluster_id"] = norm_to_cid.get(normalize_ar(a), "") if a else ""
        for k, dv in ROW_FIELD_DEFAULTS.items():
            r.setdefault(k, dv)

    data = {
        "version": 1,
        "source_pdf": "Nwyia_MSCollection.pdf",
        "rows": rows,
        "clusters": cluster_meta,
        "schema": {
            "row_columns": ["id", "page", "city", "library", "shelfmark", "folios",
                            "title", "title_translit", "title_translation",
                            "author", "author_translit", "author_translation",
                            "catalog_note", "archive", "author_cluster_id",
                            "pub_status", "pub_citation", "pub_source", "work_url",
                            "discrepancy_note"],
            "pub_status_values": ["unknown", "published", "partial", "manuscript"],
        },
    }
    normalize.write_json_atomic(OUT_PATH, data)
    print(f"Wrote {OUT_PATH}: {len(rows)} rows, {len(cluster_meta)} clusters")
    print("Largest 12 clusters:")
    for c in sorted(cluster_meta, key=lambda c: -c["count"])[:12]:
        print(f'  {c["cluster_id"]} ({c["count"]:3d}, conf={c["confidence"]}) {c["canonical_ar"]:35} → {c["canonical_translit"]}')
        if len(c["variants"]) > 1:
            print(f'      variants: {c["variants"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
