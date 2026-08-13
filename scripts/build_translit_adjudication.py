"""Build the transliteration-adjudication worklist and bake the app.

Three strata, in the order they must be decided — each earlier one dissolves work
in the later ones:

  witness   rows whose EXISTING title_translit carries a faulty token. Where that
            token is the sole witness for a losing reading, correcting it settles
            a homograph contest outright instead of requiring a ruling on it.
  homograph rows apply_word_lexicon.py refuses to compose because one normalized
            key carries two readings (من man/min, علي ʿalā/ʿalī, …).
  ortho     Arabic word forms that look non-standard, with a proposed canonical
            spelling AND the transliteration that spelling implies — the second
            axis is required, because changing the Arabic changes the lexicon key
            the composer will look the word up under. This stratum also carries the
            derived šaddah cards (see shadda_items).

Every stratum is RESIDUAL: an item the data already reflects — a witness whose row
now reads the corrected token, a word no longer spelled the faulty way, a type whose
every occurrence already carries its šaddah — drops out of the next bake. Re-running
this after an ingest yields only what is still open.

Reads data/data.json + review/translit_words_decisions.json. Writes
review/translit_adjudicate.html (self-contained; data inlined, so it opens over
file:// as well as through the project's http.server). Never writes data/.

    python3 scripts/build_translit_adjudication.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cluster  # noqa: E402
from apply_word_lexicon import apply_construct  # noqa: E402  — ONE home for the iḍāfa rule

DATA = ROOT / "data" / "data.json"
DECISIONS = ROOT / "review" / "translit_words_decisions.json"
TEMPLATE = ROOT / "review" / "translit_adjudicate.template.html"
OUT = ROOT / "review" / "translit_adjudicate.html"

# Must stay in step with apply_word_lexicon.ARABIC and the app's arabicKey().
ARABIC = re.compile(r"[ء-ٰٟ-ۓ]+")
MARKS = re.compile(r"[ً-ٰٟ]")

# Rows whose recorded transliteration carries a faulty token. `row` is the row the
# fix lands on; `id` is only the worklist key, so one row can hold several fixes.
# Items whose row already reads `proposed` drop out of the bake automatically.
WITNESSES = [
    {
        "id": "r0146", "row": "r0146",
        "word": "كلام", "current": "kalam", "proposed": "kalām",
        "why": "The recorded value drops the ālif of كلام. Three other rows "
               "(r0106, r0145, r0147) write kalām; this is the only kalam.",
    },
    {
        "id": "r0025", "row": "r0025",
        "word": "مفتاح", "current": "mafātīḥ", "proposed": "miftāḥ",
        "why": "The Arabic is singular مفتاح, but the transliteration is the plural "
               "مفاتيح. The work is Ṣadr al-Dīn al-Qūnawī's Miftāḥ al-ġayb.",
    },
    # Found by scanning the transliterations for a doubled consonant against the
    # Arabic that is supposed to carry the šaddah.
    {
        "id": "r0207-bayan", "row": "r0207",
        "word": "بيان", "current": "bayānn", "proposed": "bayān",
        "why": "A spurious doubled n. Four other rows (r0046, r0190, r0196, r0342) "
               "write bayān — and this single outlier is why the key بيان counts as "
               "contested corpus-wide.",
    },
    {
        "id": "r0086-nusayri", "row": "r0086",
        "word": "النصيرية", "current": "al-nuṣarīyah", "proposed": "al-nuṣayrīyah",
        "why": "The Nuṣayriyya: نصيرية is nuṣayriyya — the recorded form drops the "
               "diphthong and the gemination both.",
    },
    {
        "id": "r0301-nusayri", "row": "r0301",
        "word": "النصيرية", "current": "al-nuṣarīyah", "proposed": "al-nuṣayrīyah",
        "why": "Same fault as r0086.",
    },
    {
        "id": "r0097-hall", "row": "r0097",
        "word": "حلّ", "current": "ǧall", "proposed": "ḥall",
        "why": "ǧīm for ḥāʾ. The Arabic reads حلّ — Ḥall al-rumūz wa-mafātīḥ "
               "al-kunūz.",
    },
    {
        "id": "r0097-mafatih", "row": "r0097",
        "word": "ومفاتيح", "current": "wa-mafātīh", "proposed": "wa-mafātīḥ",
        "why": "Plain h for ḥāʾ in the same row's مفاتيح.",
    },
    {
        "id": "r0268-muqtatafat", "row": "r0268",
        "word": "مقتطفات", "current": "muqtaṭṭafāt", "proposed": "muqtaṭafāt",
        "why": "The Arabic مقتطفات has no gemination — muqtaṭafāt. Do NOT resolve "
               "this by adding a šaddah to the Arabic; the transliteration is the "
               "thing that is wrong.",
    },
    {
        "id": "r0170-mutafarriqa", "row": "r0170",
        "word": "المتفرقة", "current": "al-mutafarraqah", "proposed": "al-mutafarriqah",
        "why": "المتفرّقة is the active participle mutafarriqa «various, sundry», "
               "not the passive mutafarraqa. Check the sense before accepting; the "
               "šaddah on the rāʾ is right either way.",
    },
]

# Orthography candidates. `translit` is the value the word currently carries in the
# lexicon, offered as the starting point for the second axis. `only_rows` scopes an
# item to named rows — for a form that is a fault HERE but perfectly correct
# elsewhere in the corpus (بن is right between two names, wrong word-initially), a
# corpus-wide rewrite would be the bug.
ORTHO = [
    {"id": "o13", "word": "مطالب", "proposed": "مثالب", "translit": "maṯālib",
     "only_rows": ["r0127"],
     "reason": "ṭāʾ for ṯāʾ. The work is al-Ahwāzī's polemic against al-Ašʿarī — "
               "Maṯālib «faults, vices», not Maṭālib «demands». Reported from "
               "WorldCat 1162866982 (search.worldcat.org/title/1162866982); that "
               "record could not be fetched automatically (HTTP 403), so this card "
               "records YOUR reading of it, not a verified retrieval.",
     "confidence": "clear"},
    {"id": "o17", "word": "المضيئة", "proposed": "المضيّة", "translit": "al-muḍīyah",
     "only_rows": ["r0272"],
     "reason": "r0272 is «الخلاصة المرضية من الدرّة المضيئة» — a rhyming title, and "
               "this class of late work regularly drops the hamza for the rhyme: "
               "muḍiyya to answer marḍiyya. The recorded transliteration "
               "al-muḍīyah already reads it that way, so the Arabic is the side "
               "that is out of step. Keeping المضيئة instead would mean fixing the "
               "transliteration to al-muḍīʾah and losing the rhyme.",
     "confidence": "check"},
    {"id": "o15", "word": "الهم", "proposed": "الهمّ", "translit": "al-hamm",
     "only_rows": ["r0155"],
     "reason": "r0155 writes «اّلهم» — the šaddah sits on the ālif, which is "
               "impossible: a mark of gemination cannot fall on a word's first "
               "letter. It belongs on the mīm: الهمّ al-hamm «grief».",
     "confidence": "clear"},
    {"id": "o16", "word": "والمفترين", "proposed": "والمغترّين",
     "translit": "wa-l-muġtarrīn", "only_rows": ["r0124"],
     "reason": "fāʾ for ġayn. The recorded transliteration already reads "
               "wa-l-muġtarrīn, and r0055 writes the word والمغترّين — «the "
               "deluded». Check the manuscript: مفترين muftarīn «slanderers» is "
               "also a word, in which case the TRANSLITERATION is what needs "
               "fixing, not the Arabic.",
     "confidence": "check"},
    {"id": "o14", "word": "بن", "proposed": "ابن", "translit": "ibn",
     "only_rows": ["r0127"],
     "reason": "بن is the correct medial form BETWEEN two names, but this one is "
               "word-initial: the title names Ibn Abī Bišr (al-Ašʿarī's "
               "patronymic), so the standard form is ابن أبي بشر. Only touches "
               "r0127 — every other بن in the corpus is medial and correct. "
               "Check the manuscript reading before accepting.",
     "confidence": "check"},
    {"id": "o01", "word": "ادآب", "proposed": "آداب", "translit": "ādāb",
     "reason": "madda sits on the second letter; the word is آداب.",
     "confidence": "clear"},
    {"id": "o02", "word": "القدسيه", "proposed": "القدسية", "translit": "al-qudsīyah",
     "reason": "final ه for tāʾ marbūṭa ة.", "confidence": "clear"},
    {"id": "o03", "word": "الرضاء", "proposed": "الرضا", "translit": "al-riḍā",
     "reason": "al-riḍā is a maqṣūr noun — no final hamza. The recorded "
               "transliteration al-riḍāʾ follows the non-standard spelling.",
     "confidence": "clear"},
    {"id": "o04", "word": "بدو", "proposed": "بدء", "translit": "badʾ",
     "reason": "badʾ «beginning»; the recorded translit badwʾ is a reading of the "
               "faulty spelling. Compare r0178 «بدء من اناب الى الله».",
     "confidence": "clear"},
    {"id": "o05", "word": "شان", "proposed": "شأن", "translit": "šaʾn",
     "reason": "dropped hamza on the ālif; the translit already reads šaʾn.",
     "confidence": "clear"},
    {"id": "o06", "word": "مرآت", "proposed": "مرآة", "translit": "mirʾāt",
     "reason": "construct spelling of مرآة. The recorded translit mirāʾat also "
               "misplaces the hamza — mirʾāt.",
     "confidence": "check"},
    {"id": "o07", "word": "الاسرار", "proposed": "الأسرار", "translit": "al-asrār",
     "reason": "corpus writes it both ways: الاسرار in 6 rows, الأسرار in r0167. "
               "Hamza-on-ālif is optional in this convention — a house-style call.",
     "confidence": "house-style"},
    {"id": "o08", "word": "ابي", "proposed": "أبي", "translit": "abī",
     "reason": "corpus writes أبي in r0134, r0236, r0245 and ابي in r0127, r0244.",
     "confidence": "house-style"},
    {"id": "o09", "word": "الابدال", "proposed": "الأبدال", "translit": "al-abdāl",
     "reason": "corpus splits 1–1: الابدال r0222, الأبدال r0342.",
     "confidence": "house-style"},
    {"id": "o10", "word": "الاول", "proposed": "الأول", "translit": "al-awwal",
     "reason": "no counterpart spelling in the corpus; flagged only because the "
               "hamza is dropped.", "confidence": "house-style"},
    {"id": "o11", "word": "اسماء", "proposed": "أسماء", "translit": "asmāʾ",
     "reason": "no counterpart spelling in the corpus; hamza dropped.",
     "confidence": "house-style"},
    {"id": "o12", "word": "الابواب", "proposed": "الأبواب", "translit": "al-abwāb",
     "reason": "no counterpart spelling in the corpus; hamza dropped.",
     "confidence": "house-style"},
]

# Which reading the evidence points at, per contested key. A DEFAULT, never a veto —
# the annotator overrides on the card and the export records that they did.
SUGGEST = {"من": "min", "علي": "ʿalā", "كلام": "kalām", "مفتاح": "miftāḥ"}

# Why the key is contested at all. The ʿalā case is not a real ambiguity: normalize_ar
# folds ألف مقصورة to yāʾ (right for matching names), so على and علي share one key.
KEY_NOTE = {
    "علي": "NORMALIZER ARTIFACT — normalize_ar folds ى to ي, so على «ʿalā» and علي "
            "«ʿAlī» collide on one key. Read the RAW title: if it shows على, the "
            "answer is ʿalā and no real ambiguity exists.",
    "من": "Genuine homograph: the preposition min «from, of» and the relative "
           "pronoun man «he who». The sole man witness (r0178 «بدء من اناب الى "
           "الله» = badʾ man anāba) is correct.",
    "كلام": "Contested only because r0146 records kalam — see the Witnesses tab.",
    "مفتاح": "Contested only because r0025 records the plural mafātīḥ for a "
              "singular مفتاح — see the Witnesses tab.",
}


def bare(w: str) -> str:
    return MARKS.sub("", w)


# --- šaddah conformance ------------------------------------------------------
# The corpus writes the šaddah on 16 word types and omits it on 43 more whose
# transliteration geminates. Nothing carries a šaddah the transliteration
# contradicts, so the rule holds in one direction and the omissions are a backlog.
#
# The mark is invisible to matching — normalize_ar strips every combining mark, so
# القدسيّة and القدسيه are ONE lexicon key. Writing it changes no key and unblocks
# no title; what it buys is the reverse check, which is how the faults above were
# found. So these cards are cheap and none of them is load-bearing.
SHADDA = "ّ"
LAT2AR = {"b": "ب", "t": "ت", "ṯ": "ث", "ǧ": "ج", "ḥ": "ح", "ḫ": "خ", "d": "د",
          "ḏ": "ذ", "r": "ر", "z": "ز", "s": "س", "š": "ش", "ṣ": "ص", "ḍ": "ض",
          "ṭ": "ط", "ẓ": "ظ", "ʿ": "ع", "ġ": "غ", "f": "ف", "q": "ق", "k": "ك",
          "l": "ل", "m": "م", "n": "ن", "h": "ه", "w": "و", "y": "ي"}
CONS = "".join(LAT2AR)
# Words whose transliteration is itself the fault — the šaddah pass must not
# "resolve" them by marking a gemination the Arabic does not have.
SHADDA_EXCLUDE = {"مقتطفات", "والمفترين", "النصيرية", "بيان"}


def geminated(translit: str) -> list[str]:
    """The Latin consonants a transliteration doubles, in order of appearance."""
    t = translit.lower()
    out = [("y" if m.group().endswith("y") else "w")
           for m in re.finditer(r"īy|uww|iyy|ayy", t)]
    out += [m.group(1) for m in re.finditer(r"([" + CONS + r"])\1", t)]
    return list(dict.fromkeys(out))


def place_shadda(word: str, letter: str) -> str | None:
    """Insert a šaddah after the letter that carries it, or None if undecidable.

    Two determinate narrowings, both grammatical rather than heuristic:
      * the definite article's lām is never the geminated one, so a leading ال is
        excluded before counting occurrences (this is what resolves الله → اللّه
        and الادلة → الادلّة);
      * in a nisba the doubled yāʾ is the one before the tāʾ marbūṭa, however many
        other yāʾs the stem contains (دينية → دينيّة).
    Anything still ambiguous returns None and becomes a card with no proposal.
    """
    if letter == "ي" and word.endswith("ية"):
        return word[:-1] + SHADDA + word[-1:]
    start = 2 if word.startswith("ال") and len(word) > 3 else 0
    hits = [i for i in range(start, len(word)) if word[i] == letter]
    # …but a leading ال is not always the article. In التي «allatī» that lām IS the
    # geminated consonant, and skipping it leaves nothing to mark. Falling back to
    # the whole word recovers exactly that case without loosening the rule where the
    # article really is an article (there, the root letter is still found).
    if not hits and start:
        hits = [i for i, ch in enumerate(word) if ch == letter]
    if len(hits) != 1:
        return None
    i = hits[0]
    return word[:i + 1] + SHADDA + word[i + 1:]


def shadda_items(rows: list[dict], readings: dict,
                 covered: set[str], translit_fix: dict[str, str]) -> list[dict]:
    """One card per word type whose transliteration geminates but Arabic doesn't.

    Words are keyed mark-BLIND, the way the ingest matches them, so a type the
    corpus writes both ways (التصوّف beside التصوف) is one card that unifies both.
    The corollary is the exclusion below: a type where EVERY occurrence already
    carries the mark is settled and must not come back as a card.
    """
    pairs: dict[str, set[str]] = defaultdict(set)
    where: dict[str, set[str]] = defaultdict(set)
    unmarked: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        ar = ARABIC.findall(r.get("title") or "")
        lat = (r.get("title_translit") or "").split()
        if ar and len(ar) == len(lat):
            for a, l in zip(ar, lat):
                pairs[bare(a)].add(l)
                where[bare(a)].add(r["id"])
                if SHADDA not in a:
                    unmarked[bare(a)].add(r["id"])

    out = []
    for w in sorted(pairs, key=lambda x: (-len(unmarked[x]), x)):
        if SHADDA in w or w in SHADDA_EXCLUDE:
            continue
        if not unmarked[w]:
            continue                # every occurrence already marked — settled
        if w in covered:
            continue                # an explicit card above already rules on it
        translits = sorted(pairs[w])
        gems = list(dict.fromkeys(g for t in translits for g in geminated(t)))
        if not gems:
            continue
        # A yāʾ that carries a hamza is not a geminated yāʾ: al-muḍīyah renders
        # مضيئة muḍīʾa, a participle with no doubling at all. Without this the
        # rule confidently proposes a šaddah that would be simply wrong.
        if gems == ["y"] and "يئ" in w:
            continue
        proposal = (place_shadda(w, LAT2AR[gems[0]])
                    if len(gems) == 1 and len(translits) == 1 else None)
        # Where a witness card is already correcting this word's transliteration,
        # offer the CORRECTED form as this card's second axis — otherwise the two
        # cards disagree and whichever runs last writes the lexicon.
        default = translit_fix.get(w) or (translits[0] if len(translits) == 1 else None)
        out.append({
            "id": "s-" + w, "word": w, "proposed": proposal,
            "translit": default,
            "translits": translits,
            "only_rows": sorted(unmarked[w]),
            "confidence": "shadda" if proposal else "shadda-manual",
            "reason": (
                f"The transliteration geminates ({'/'.join(translits)}), so the "
                f"Arabic should carry a šaddah."
                + ("" if proposal else
                   "  Which letter carries it is not mechanically decidable here"
                   + (f" — {LAT2AR[gems[0]]} occurs more than once outside the "
                      f"article" if len(gems) == 1 else
                      f" — the transliteration doubles {len(gems)} consonants "
                      f"({', '.join(gems)})")
                   + ". Type the form.")
                + "  The mark changes no lexicon key and unblocks no title; it "
                  "makes the transliteration checkable against the Arabic."),
        })
    return out


def words_of(title: str) -> list[str]:
    return [cluster.normalize_ar(w) for w in ARABIC.findall(title or "")]


def build_lexicon(data: dict, decisions: dict) -> tuple[dict, dict, set]:
    """The composer's view of the corpus: settled words, all readings, contested keys."""
    lex = {cluster.normalize_ar(w): d["translit"].strip()
           for w, d in decisions.items()
           if d.get("decided") and (d.get("translit") or "").strip() and not d.get("varies")}

    seen: dict[str, set[str]] = defaultdict(set)
    witness: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in data["rows"]:
        ar = words_of(r.get("title") or "")
        lat = (r.get("title_translit") or "").split()
        if ar and len(ar) == len(lat):
            for a, l in zip(ar, lat):
                seen[a].add(l)
                witness[(a, l)].add(r["id"])

    def state_free(v: str) -> str:
        return v[:-2] + "ah" if v.endswith("at") else v

    contested = {k for k, v in seen.items() if len({state_free(x) for x in v}) > 1}
    for k, v in seen.items():
        if k not in contested:
            lex.setdefault(k, state_free(sorted(v)[0]))
    for k in contested:
        lex.pop(k, None)
    return lex, {k: {r: sorted(witness[(k, r)]) for r in sorted(v)} for k, v in seen.items()}, contested


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8")).get("words", {})
    clusters = {c["cluster_id"]: c for c in data["clusters"]}
    modern = {k for k, c in clusters.items() if c.get("category") == "modern"}
    rows_by_id = {r["id"]: r for r in data["rows"]}

    lex, readings, contested = build_lexicon(data, decisions)

    # --- homograph stratum ---------------------------------------------------
    homographs = []
    for r in data["rows"]:
        if r.get("author_cluster_id") in modern:
            continue
        title = (r.get("title") or "").strip()
        if not title or (r.get("title_translit") or "").strip():
            continue
        ws = words_of(title)
        hits = [w for w in dict.fromkeys(ws) if w in contested]
        if not hits:
            continue

        # The whole point of the card: the raw surface, which is what disambiguates
        # the folded key. Show each contested key's raw spelling in THIS title.
        raw_by_key = {}
        for raw in ARABIC.findall(title):
            k = cluster.normalize_ar(raw)
            if k in contested:
                raw_by_key.setdefault(k, bare(raw))

        # Precompute every composition the card can need — at most 2 keys x 2
        # readings. The app looks the answer up; the formula keeps ONE home here.
        # A combination absent from this table is an error the app must announce,
        # not paper over.
        options = [sorted(readings[k]) for k in hits]
        compositions = {}
        for combo in product(*options):
            choice = dict(zip(hits, combo))
            parts = [choice.get(w, lex.get(w)) for w in ws]
            compositions["|".join(combo)] = (
                " ".join(apply_construct(parts, ws)) if all(parts) else None
            )

        homographs.append({
            "id": r["id"],
            "stratum": "homograph",
            "title": title,
            "author": clusters.get(r.get("author_cluster_id"), {}).get("canonical_translit") or "—",
            "gloss": [{"key": w, "raw": None, "translit": lex.get(w), "contested": w in contested}
                      for w in ws],
            "keys": [{
                "key": k,
                "raw": raw_by_key.get(k, k),
                "note": KEY_NOTE.get(k, ""),
                "suggest": SUGGEST.get(k),
                "options": [{
                    "value": v,
                    "witnesses": readings[k][v],
                    "witness_titles": [
                        {"id": i, "title": (rows_by_id[i].get("title") or ""),
                         "translit": (rows_by_id[i].get("title_translit") or "")}
                        for i in readings[k][v][:3]],
                } for v in sorted(readings[k])],
            } for k in hits],
            "compositions": compositions,
        })

    # --- witness stratum -----------------------------------------------------
    # A decided item never comes back: an item whose row already reads `proposed`
    # is settled, so it simply drops out of the next bake.
    witnesses = []
    for w in WITNESSES:
        rid = w.get("row", w["id"])
        r = rows_by_id[rid]
        toks = (r.get("title_translit") or "").split()
        if w["current"] not in toks:
            continue
        witnesses.append({
            **w, "row": rid, "stratum": "witness",
            "title": r.get("title") or "",
            "title_translit": r.get("title_translit") or "",
            "unblocks": sorted(h["id"] for h in homographs
                               if any(k["key"] == cluster.normalize_ar(w["word"])
                                      for k in h["keys"])),
        })

    # --- orthography stratum -------------------------------------------------
    corpus = [r for r in data["rows"] if r.get("author_cluster_id") not in modern]
    occ: dict[str, list[str]] = defaultdict(list)
    for r in corpus:
        for raw in ARABIC.findall(r.get("title") or ""):
            occ[bare(raw)].append(r["id"])

    ortho = []
    # An explicit card above outranks a derived one, and a witness card that is
    # already correcting a word's transliteration supplies this word's default.
    covered = {o["word"] for o in ORTHO}
    translit_fix = {bare(w["word"]): w["proposed"] for w in WITNESSES}
    for o in ORTHO + shadda_items(corpus, readings, covered, translit_fix):
        ids = sorted(set(occ.get(o["word"], [])))
        if o.get("only_rows"):
            ids = [i for i in ids if i in set(o["only_rows"])]
        if not ids:
            continue                      # already canonicalized — settled, drop it
        # The transliteration the word carries TODAY. The ingest needs it to swap
        # the token inside any affected row that already has a title_translit —
        # rewriting the Arabic without it would leave the two out of step.
        key = cluster.normalize_ar(o["word"])
        was = sorted(readings.get(key, {})) if key in readings else []
        ortho.append({
            **o, "stratum": "ortho",
            "translit_was": lex.get(key) or (was[0] if len(was) == 1 else None),
            "rows": [{
                "id": i,
                "title": rows_by_id[i].get("title") or "",
                "after": (rows_by_id[i].get("title") or "").replace(
                    o["word"], o["proposed"]) if o.get("proposed") else None,
                "translit": rows_by_id[i].get("title_translit") or "",
            } for i in ids],
        })

    payload = {
        "schema_version": 1,
        "task": "translit-adjudication",
        "generated_from": "data/data.json + review/translit_words_decisions.json",
        "counts": {"witness": len(witnesses), "homograph": len(homographs),
                   "ortho": len(ortho)},
        "strata": {"witness": witnesses, "homograph": homographs, "ortho": ortho},
    }

    # `</` inside the inlined JSON would close the <script> block early.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", blob),
                   encoding="utf-8")

    manual = [o for o in ortho if not o.get("proposed")]
    print(f"witnesses  : {len(witnesses)}")
    print(f"homographs : {len(homographs)}")
    print(f"orthography: {len(ortho)}  ({len(manual)} with no proposal — you type "
          f"the form)")
    print(f"\nWrote {OUT}  ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
