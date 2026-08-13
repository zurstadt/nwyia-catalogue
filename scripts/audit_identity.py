"""Read-only audit of author clusters and titles for identity problems.

Clustering only ever ACCUMULATES similarity — nothing subtracts — so two people
who share enough onomastic surface merge however violently they disagree on a
discriminating element. This script applies the refutations that a similarity
score cannot express, and reports what it finds. It NEVER writes to data/.

Checks, in the order they are reported:

  1. OVER-MERGE   two author forms inside one cluster that name different people
                  (a differing ism; a kunyah that names the other form's ism —
                  i.e. the father, not the man; an inverted nasab chain)
  2. CONSERVATION one author string filed under two clusters
  3. UNDER-MERGE  two clusters whose canonical names fold to the same key
  4. ATTRIBUTION  one title attributed to two different clusters
  5. TITLE FORMS  titles that differ only orthographically — they must receive
                  the same transliteration, so they matter to the sweep in progress

Onomastic rules follow the `network-disambiguation` skill: nasab is a SEQUENCE
(order is evidence), a confidently-parsed ism mismatch REFUSES rather than
penalises, and a bare shared kunyah is an honorific rather than an identification.
Token distinctiveness is IDF over this corpus, not a global gazetteer.

    python3 scripts/audit_identity.py [--json review/identity_audit.json]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cluster  # noqa: E402  — reuse the pipeline's own Arabic normalizers

DATA = ROOT / "data" / "data.json"

NASAB_CONNECTORS = {"بن", "ابن"}
KUNYA_PARTICLES = {"ابو", "ابي", "ام"}
COMPOUND_HEADS = {"عبد"}          # عبد + theophoric is ONE name unit
ARTICLE = "ال"


# --------------------------------------------------------------------- parsing
def strip_article(tok: str) -> str:
    """الحسن and حسن are the same ism.

    The article is attached in Arabic script, so a parser that does not strip it
    compares الحسن against حسن and finds them different — which silently disables
    the ism veto for every al- name, the classic fail-open.
    """
    return tok[len(ARTICLE):] if tok.startswith(ARTICLE) and len(tok) > 3 else tok


def element_at(tokens: list[str], i: int) -> tuple[str, int]:
    """One name UNIT starting at i, and the index after it.

    A unit is atomic: عبد الله is one name, not two, and أبو عبد الله is one
    kunyah. Splitting either produces a non-name and corrupts every comparison
    downstream. Compound heads are detected at any position, not only at the
    start of the string.
    """
    if i >= len(tokens):
        return "", i
    tok = tokens[i]
    if tok in KUNYA_PARTICLES:
        rest, j = element_at(tokens, i + 1)
        return (f"{tok} {rest}".strip(), j)
    if tok in COMPOUND_HEADS and i + 1 < len(tokens):
        return (f"{tok} {tokens[i + 1]}", i + 2)
    return (tok, i + 1)


def parse_name(raw: str) -> dict:
    """Split an Arabic author string into onomastic components."""
    norm = cluster.normalize_ar(raw or "")
    tokens = [t for t in norm.split() if t]
    out = {"raw": raw, "norm": norm, "kunya": None, "ism": None,
           "chain": [], "nisbahs": [], "tokens": tokens}
    if not tokens:
        return out

    # A name OPENING with Ibn is a shuhrah — "Ibn al-ʿArabī" points at an ancestor
    # of unknown depth, not at a father. It may corroborate any ancestor slot but
    # must never drive a positional veto: treating it as position 1 is exactly
    # what falsely splits a shuhrah from its own fuller name.
    out["shuhrah"] = tokens[0] in NASAB_CONNECTORS

    i = 0
    if tokens[0] in KUNYA_PARTICLES:
        out["kunya"], i = element_at(tokens, 0)

    # The ism is claimed ONLY when a nasab connector follows it. A shuhrah- or
    # nisbah-only name yields no ism, and the veto then abstains rather than
    # inventing a disagreement out of a parser guess.
    if i < len(tokens):
        head, j = element_at(tokens, i)
        if j < len(tokens) and tokens[j] in NASAB_CONNECTORS:
            out["ism"] = head
        out["head"] = head

    # The nasab CHAIN in order — position is the evidence, so it is a list.
    chain, k = [], i
    while k < len(tokens):
        if tokens[k] in NASAB_CONNECTORS:
            el, k = element_at(tokens, k + 1)
            if el:
                chain.append(el)
        else:
            k += 1
    out["chain"] = chain
    out["nisbahs"] = [t for t in tokens if t.startswith(ARTICLE) and t.endswith("ي")]
    return out


def key(el: str | None) -> str | None:
    """Comparison key for a name element."""
    if not el:
        return None
    return " ".join(strip_article(t) for t in el.split())


# ------------------------------------------------------------------- refutations
def refute(a: dict, b: dict, rare: set[str]) -> list[str]:
    """Reasons these two author forms name DIFFERENT people. Empty = no objection."""
    reasons = []

    # An ism mismatch, both confidently parsed, is decisive.
    if a["ism"] and b["ism"] and key(a["ism"]) != key(b["ism"]):
        reasons.append(
            f"different ism: {a['ism']} vs {b['ism']} — provably two men, "
            "not two spellings")

    # A kunyah names the SON. "Abū al-Ḥasan" is the father of al-Ḥasan, so a form
    # whose kunyah element equals the other form's own name is a generation apart.
    for x, y in ((a, b), (b, a)):
        if not x["kunya"]:
            continue
        kun = key(x["kunya"].split(" ", 1)[1]) if " " in x["kunya"] else None
        other = key(y.get("ism") or y.get("head"))
        if kun and other and kun == other:
            reasons.append(
                f"kunyah names the other form: {x['kunya']} is the FATHER of "
                f"{y.get('ism') or y.get('head')} — a generation apart")

    # An inverted chain (X b. Y vs Y b. X) shares every token and names two men.
    if a["ism"] and b["ism"] and a["chain"] and b["chain"]:
        if key(a["ism"]) == key(b["chain"][0]) and key(b["ism"]) == key(a["chain"][0]):
            reasons.append(
                f"inverted nasab: {a['ism']} b. {a['chain'][0]} vs "
                f"{b['ism']} b. {b['chain'][0]}")

    # Chains that disagree at a shared position are different lineages — but only
    # when both sides are real chains. A shuhrah is excluded (above), and a
    # one-letter difference is a spelling of one name, not another lineage.
    if not a["shuhrah"] and not b["shuhrah"]:
        for idx, (x, y) in enumerate(zip(a["chain"], b["chain"])):
            if key(x) != key(y) and not near(key(x), key(y)):
                reasons.append(f"nasab differs at position {idx + 1}: {x} vs {y}")
                break

    return reasons


def near(x: str, y: str) -> bool:
    """One edit apart — an orthographic variant of one name, not a second name.

    Yazdānyār / Yāzdānyār is one man spelled two ways; without this the audit
    reports every scribal variant as a distinct lineage and buries the real ones.
    """
    if not x or not y or abs(len(x) - len(y)) > 1:
        return False
    if len(x) < len(y):
        x, y = y, x
    if x == y:
        return True
    for i in range(len(x)):                      # deletion / substitution probe
        if x[:i] + x[i + 1:] == y or (len(x) == len(y) and x[:i] + y[i] + x[i + 1:] == y):
            return True
    return False


def folded_tokens(p: dict) -> set[str]:
    return {strip_article(t) for t in cluster.fold_orthography(p["norm"]).split()}


def weak_link(a: dict, b: dict, rare: set[str]) -> str | None:
    """No shared DISTINCTIVE token — the merge rests on common vocabulary alone.

    A short form nested inside a longer one is NOT weak: a mention that is just
    "al-Baṣrī" asserts nothing beyond the fuller sibling it belongs to, and
    treating containment as a disagreement splits one man in two.
    """
    ta, tb = folded_tokens(a), folded_tokens(b)
    if ta <= tb or tb <= ta:
        return None
    shared = ta & tb
    if shared & rare:
        return None
    return ("no distinctive token in common"
            + (f" (shared only: {', '.join(sorted(shared))})" if shared else ""))


def nisba_only_link(form: dict, canon: dict) -> str | None:
    """This form is attached to its cluster by a NISBAH and nothing else.

    A nisbah is confirmatory, never decisive — al-Kāshānī, al-Baġdādī and their
    like are shared by many unrelated people, and a cluster built on one is the
    classic homonym conflation. Fires only when the form carries real identifying
    material of its own (an ism or a chain) that the cluster's canonical lacks.
    """
    if not (form["ism"] or form["chain"]):
        return None
    shared = folded_tokens(form) & folded_tokens(canon)
    if not shared:
        return "shares NOTHING with the cluster's canonical name"
    if all(t.endswith("ي") for t in shared):
        return (f"linked to the cluster by nisbah alone ({', '.join(sorted(shared))}) "
                "while carrying its own ism/nasab")
    return None


# ------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", help="also write the worklist to this path")
    args = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    clusters = {c["cluster_id"]: c for c in data["clusters"]}
    modern = {k for k, c in clusters.items() if c.get("category") == "modern"}
    rows = [r for r in data["rows"] if r.get("author_cluster_id") not in modern]

    # IDF over THIS corpus: a token's weight is how rare it is here, not in a
    # gazetteer. df<=3 is "distinctive".
    df = Counter()
    for r in rows:
        for t in {strip_article(x) for x in cluster.normalize_ar(r.get("author") or "").split()}:
            df[t] += 1
    rare = {t for t, n in df.items() if n <= 3}

    forms = defaultdict(set)
    for r in rows:
        cid, a = r.get("author_cluster_id"), (r.get("author") or "").strip()
        if cid and a:
            forms[cid].add(a)

    # An adjudicated merge is a settled case. Re-raising it every run is how a
    # worklist loses the reader's trust.
    import harvest_authority
    settled = {cluster.normalize_ar(v) for v in harvest_authority.NAMED_MERGES}

    report, worklist = [], {"over_merge": [], "conservation": [], "under_merge": [],
                            "attribution": [], "cote_conflict": [], "case_drift": [],
                            "title_forms": []}

    # 1 — over-merge
    for cid, variants in sorted(forms.items()):
        variants = {v for v in variants if cluster.normalize_ar(v) not in settled}
        if not variants:
            continue
        parsed = {v: parse_name(v) for v in variants}
        canon = parse_name(clusters[cid].get("canonical_ar") or "")
        # Each form against the identity the cluster CLAIMS, not only against its
        # siblings: a cluster of two forms can be wrong about both.
        for v in sorted(variants):
            why = nisba_only_link(parsed[v], canon)
            if why:
                worklist["over_merge"].append({
                    "cluster_id": cid, "cluster": clusters[cid].get("canonical_translit", ""),
                    "dates": clusters[cid].get("dates", ""),
                    "form_a": clusters[cid].get("canonical_ar", "") + "  [cluster canonical]",
                    "form_b": v, "severity": "refute", "reasons": [why]})
        if len(variants) < 2:
            continue
        vs = sorted(variants)
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                a, b = parsed[vs[i]], parsed[vs[j]]
                reasons = refute(a, b, rare)
                weak = None if reasons else weak_link(a, b, rare)
                if not reasons and not weak:
                    continue
                item = {"cluster_id": cid,
                        "cluster": clusters[cid].get("canonical_translit", ""),
                        "dates": clusters[cid].get("dates", ""),
                        "form_a": vs[i], "form_b": vs[j],
                        "severity": "refute" if reasons else "weak",
                        "reasons": reasons or [weak]}
                worklist["over_merge"].append(item)

    # 2 — conservation: one author string must live in exactly one cluster
    where = defaultdict(set)
    for r in rows:
        a = (r.get("author") or "").strip()
        if a and r.get("author_cluster_id"):
            where[cluster.normalize_ar(a)].add(r["author_cluster_id"])
    for name, cids in sorted(where.items()):
        if len(cids) > 1:
            worklist["conservation"].append({"author": name, "clusters": sorted(cids)})

    # 3 — under-merge: two clusters whose canonical names fold together
    folded = defaultdict(list)
    for cid, c in clusters.items():
        if cid in modern:
            continue
        k = cluster.fold_orthography(cluster.normalize_ar(c.get("canonical_ar") or ""))
        if k:
            folded[k].append(cid)
    for k, cids in sorted(folded.items()):
        if len(cids) > 1:
            worklist["under_merge"].append(
                {"folded": k,
                 "clusters": [{"cluster_id": c, "translit": clusters[c].get("canonical_translit", ""),
                               "dates": clusters[c].get("dates", "")} for c in sorted(cids)]})

    # 4 — one title, two clusters
    by_title = defaultdict(list)
    for r in rows:
        t = cluster.normalize_ar(r.get("title") or "")
        if len(t) >= 6 and r.get("author_cluster_id"):
            by_title[t].append(r)
    for t, rs in sorted(by_title.items()):
        cids = {r["author_cluster_id"] for r in rs}
        if len(cids) > 1:
            worklist["attribution"].append({
                "title": t,
                "attributions": [{"cluster_id": c,
                                  "translit": clusters[c].get("canonical_translit", ""),
                                  "rows": sorted(r["id"] for r in rs if r["author_cluster_id"] == c)}
                                 for c in sorted(cids)]})

    # 4b — the Fonds cote as independent evidence. The cote numbers were assigned
    # by the colleagues who catalogued Nwyia's office, so items sharing a cote were
    # bundled together by someone who had the material in front of them. That
    # grouping is INDEPENDENT of the name string the clusterer saw. A row whose
    # cote-mates all sit in a different cluster is a real signal — weak on its own,
    # decisive when it agrees with an onomastic doubt.
    by_cote = defaultdict(list)
    for r in rows:
        cote = (r.get("archive") or "").strip()
        if cote and r.get("author_cluster_id"):
            by_cote[cote].append(r)
    # Cote co-membership ALONE over-fires badly: a bundle is a box of unrelated
    # works, so cote-mates in different clusters is the norm, not an anomaly (an
    # unconditioned version of this check produced 73 hits, nearly all benign).
    # It becomes evidence only when a SECOND dimension agrees — here, the same
    # work bundled together and attributed two different ways.
    for cote, rs in sorted(by_cote.items()):
        by_t = defaultdict(list)
        for r in rs:
            t = cluster.normalize_ar(r.get("title") or "")
            if len(t) >= 6:
                by_t[t].append(r)
        for t, same in by_t.items():
            cids = {r["author_cluster_id"] for r in same}
            if len(cids) < 2:
                continue
            worklist["cote_conflict"].append({
                "cote": cote, "title": t,
                "attributions": [{"cluster_id": c,
                                  "translit": clusters[c].get("canonical_translit", ""),
                                  "rows": sorted(r["id"] for r in same if r["author_cluster_id"] == c),
                                  "authors": sorted({r.get("author", "") for r in same
                                                     if r["author_cluster_id"] == c})}
                                 for c in sorted(cids)]})

    # 4c — transliteration house style. Titles are romanized in LOWERCASE in this
    # corpus (ruled 2026-08-13); a stray initial capital is drift, not a variant,
    # and two spellings of one work is exactly what the index must not carry.
    # A Latin-script source is exempt: its capitals are proper nouns, not style.
    arabic_re = re.compile(r"[؀-ۿ]")
    for r in rows:
        t = (r.get("title_translit") or "").strip()
        if not t or not arabic_re.search(r.get("title") or ""):
            continue
        if t != t.lower():
            worklist["case_drift"].append(
                {"row": r["id"], "value": t, "expected": t.lower()})

    # 5 — title spellings that must not diverge in transliteration
    by_fold = defaultdict(set)
    for r in rows:
        t = (r.get("title") or "").strip()
        if len(t) >= 6:
            by_fold[cluster.fold_orthography(cluster.normalize_ar(t))].add(t)
    for k, spellings in sorted(by_fold.items()):
        if len(spellings) > 1:
            worklist["title_forms"].append({"normalized": k, "spellings": sorted(spellings)})

    # ------------------------------------------------------------------ output
    def section(title, items):
        report.append(f"\n## {title}  ({len(items)})\n")

    section("Over-merge candidates", worklist["over_merge"])
    for it in sorted(worklist["over_merge"], key=lambda x: x["severity"] != "refute"):
        mark = "REFUTE" if it["severity"] == "refute" else "weak  "
        report.append(f"[{mark}] {it['cluster_id']} {it['cluster']} {it['dates']}")
        report.append(f"         A: {it['form_a']}")
        report.append(f"         B: {it['form_b']}")
        for why in it["reasons"]:
            report.append(f"         → {why}")
    section("Conservation failures (one name, two clusters)", worklist["conservation"])
    for it in worklist["conservation"]:
        report.append(f"  {it['author']} → {', '.join(it['clusters'])}")
    section("Under-merge candidates (canonical names fold together)", worklist["under_merge"])
    for it in worklist["under_merge"]:
        report.append(f"  {it['folded']}")
        for c in it["clusters"]:
            report.append(f"      {c['cluster_id']}  {c['translit']}  {c['dates']}")
    section("One title, two attributions", worklist["attribution"])
    for it in worklist["attribution"]:
        report.append(f"  {it['title']}")
        for a in it["attributions"]:
            report.append(f"      {a['cluster_id']} {a['translit']}: {', '.join(a['rows'])}")
    section("Cote conflicts (a row whose Fonds bundle-mates sit elsewhere)",
            worklist["cote_conflict"])
    for it in worklist["cote_conflict"]:
        report.append(f"  cote {it['cote']} — {it['title']}")
        for a in it["attributions"]:
            report.append(f"      {', '.join(a['rows'])} → {a['cluster_id']} {a['translit']}"
                          f"   ({'; '.join(a['authors'])})")
    section("Transliteration case drift (titles are lowercase here)", worklist["case_drift"])
    for it in worklist["case_drift"]:
        report.append(f"  {it['row']}  {it['value']}  ->  {it['expected']}")
    section("Title spellings that must share one transliteration", worklist["title_forms"])
    for it in worklist["title_forms"]:
        report.append("  " + "   |   ".join(it["spellings"]))

    print("\n".join(report))
    counts = {k: len(v) for k, v in worklist.items()}
    print(f"\nTotals: {counts}")

    if args.json:
        out = ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(worklist, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
