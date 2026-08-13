"""Build the transliteration-adjudication worklist and bake the app.

Four strata, in the order they must be decided — each earlier one dissolves work
in the later ones:

  witness     rows whose EXISTING title_translit carries a faulty token. Where that
              token is the sole witness for a losing reading, correcting it settles
              a homograph contest outright instead of requiring a ruling on it.
  homograph   rows apply_word_lexicon.py refuses to compose because one normalized
              key carries two readings (من man/min, علي ʿalā/ʿalī, …).
  ortho       Arabic word forms that look non-standard, with a proposed canonical
              spelling AND the transliteration that spelling implies. Carries the
              hand-written cards plus two derived families: šaddah (shadda_items)
              and initial hamzat qaṭʿ (hamza_items), the latter spanning titles,
              author fields and cluster names at once.
  attribution the handful of rows whose title ends in a li- attribution naming a
              person. Deliberately one card per row with KEEP as the default: the
              census showed most such tails are real bibliographic information
              (whose text is being commented on), not a duplicated author field.

Every stratum is RESIDUAL in two directions. An item the data already reflects — a
witness whose row now reads the corrected token, a word no longer spelled the faulty
way, a type whose every occurrence already carries its šaddah — drops out because the
fault is gone. An item ruled KEEP leaves the data untouched, so no data-derived filter
can see it; those ids live in translit_adjudication_keeps.json and are dropped from
here. Without that second half, every keep would be re-asked on every bake.

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
import normalize  # noqa: E402  — the ONE Arabic word/mark definition
from apply_word_lexicon import apply_construct  # noqa: E402  — ONE home for the iḍāfa rule

DATA = ROOT / "data" / "data.json"
DECISIONS = ROOT / "review" / "translit_words_decisions.json"
TEMPLATE = ROOT / "review" / "translit_adjudicate.template.html"
OUT = ROOT / "review" / "translit_adjudicate.html"
# Items ruled KEEP by a previous batch. A keep leaves the data untouched, so the
# residual filters — which all ask "does the data still show the fault?" — cannot
# see it, and the card would come back every bake. This file is how a keep sticks.
KEEPS = ROOT / "review" / "translit_adjudication_keeps.json"

# One definition, shared with the ingest and the worklist builders. The comment
# this replaces claimed the class had to stay in step with "the app's
# arabicKey()" — the adjudication app has no arabicKey() and does no Arabic
# normalization at all, so that was a contract with nobody.
ARABIC = normalize.AR_WORD
bare = normalize.bare

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
    # One entry per row, because the witness applier patches a row's own tokens.
    *[{
        "id": f"{rid}-istilahat", "row": rid,
        "word": "اصطلاحات", "current": "iṣṭilāḥāṭ", "proposed": "iṣṭilāḥāt",
        "why": "Final ṭāʾ for tāʾ: the plural ending is -āt. Seven rows carry the "
               "same slip. Note the ARABIC is right as it stands — اصطلاح is form "
               "VIII, so its initial ālif is hamzat waṣl and takes no hamza.",
    } for rid in ("r0081", "r0083", "r0084", "r0218", "r0317", "r0318", "r0339")],
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
    {"id": "o18", "word": "اسئيلة", "proposed": "أسئلة", "translit": "asʾilah",
     "only_rows": ["r0258"],
     "reason": "r0258 «الدر المكنون في اسئيلة ما كان وما يكون». Two faults in one "
               "word: a spurious yāʾ (asʾila has no long vowel there), and the "
               "word-initial hamza — أسئلة is form-IV-adjacent and takes qaṭʿ. The "
               "recorded transliteration asʾilah is already correct.",
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


# --- initial hamzat qaṭʿ -----------------------------------------------------
# A word-initial hamza is either qaṭʿ (written أ or إ and always pronounced) or
# waṣl (written as a bare ālif and elided in context). The corpus writes a bare
# ālif in both cases, so the fix is to restore the carrier on the qaṭʿ ones ONLY —
# a bare ālif on a waṣl word is correct and must not be "corrected".
#
# The evidence is the TRANSLITERATION, not the Arabic: this project romanizes
# initial qaṭʿ and waṣl identically (al-asrār, al-intiṣār), but the VOWEL survives,
# and that is enough to decide most of it.
PROCLITIC = ("wa-l-", "li-l-", "bi-l-", "wa-", "al-", "li-", "bi-", "la-")
# Hamzat waṣl belongs to the maṣdars of forms VII, VIII and X, and to a short
# closed lexical list. Form VIII's infixed tāʾ ASSIMILATES after certain
# consonants — iṣṭilāḥ is اصطلاح, not *اصتلاح — so a plain ^ا.ت misses exactly the
# words that occur most here (8 rows of اصطلاحات alone).
WASL_AR = re.compile(r"^ا(ست|صط|ضط|طط|ظط|زد|دد|ذذ|ثث|ن|.ت)")
# A tāʾ in SECOND position is form VIII's infix (اِنتصار); a tāʾ in FIRST position is
# a root consonant of a form IV maṣdar (إتحاف) — the two are distinguishable after
# all. What genuinely collides is a form IV maṣdar whose C2 is tāʾ (إفتاء), and the
# transliteration separates those too: form VIII's iftiʿāl carries TWO i-vowels
# (i-n-t-i-ṣār), form IV's ifʿāl only one (i-ftāʾ).
FORM8_INFIX = re.compile(r"^ا.ت")
TWO_I = re.compile(r"^i[^i]*i")
WASL_LEX = {"ابن", "ابنة", "اسم", "امرؤ", "امرأة", "اثنان", "اثنين", "الله", "اللهم"}


def initial_vowel_tail(translit: str) -> str:
    """The transliteration past any proclitic, lowercased."""
    t = translit
    for p in sorted(PROCLITIC, key=len, reverse=True):
        if t.lower().startswith(p):
            t = t[len(p):]
            break
    return t.lower()


def initial_vowel(translit: str) -> str | None:
    """The first vowel of a transliteration, past any proclitic."""
    return initial_vowel_tail(translit)[:1] or None


def hamza_verdict(word: str, translits: list[str]) -> tuple[str | None, str]:
    """(carrier, why) for a bare-ālif-initial word: 'أ', 'إ', None for waṣl, or
    ('?', why) when the two readings are genuinely indistinguishable."""
    stem = word[2:] if word.startswith("ال") and len(word) > 3 else word
    if not stem.startswith("ا"):
        return None, "not ālif-initial"
    if stem in WASL_LEX:
        return None, "closed-class hamzat waṣl"
    vowels = {initial_vowel(t) for t in translits}
    # An initial LONG ā is not a plain hamza at all — it is hamza + ālif, written
    # with a madda: الآيات al-āyāt, never الأيات. Splitting this off first is what
    # keeps the a/u rule from producing a wrong carrier on a right diagnosis.
    if vowels <= {"ā"}:
        return "آ", "the transliteration opens with ā — hamza over ālif is a madda"
    # A waṣl maṣdar is always romanized with an initial i. Nothing beginning a or u
    # can be one — which is what separates al-intiṣār (form VIII) from al-anwār,
    # anāba and anwāʾ, all three of which an Arabic-side ^ان test wrongly claims.
    if vowels <= {"a", "u"}:
        return "أ", "the transliteration opens with a/u, which no waṣl form does"
    if vowels <= {"i", "ī"}:
        stripped = [t for t in (initial_vowel_tail(x) for x in translits) if t]
        if FORM8_INFIX.match(stem) and any(TWO_I.match(t) for t in stripped):
            return None, ("form VIII iftiʿāl — the infixed tāʾ and the second i "
                          "(i-n-t-i-ṣār) both say so; hamzat waṣl, bare ālif is right")
        if WASL_AR.match(stem) and not FORM8_INFIX.match(stem):
            return None, "form VII/VIII/X maṣdar — hamzat waṣl, bare ālif is correct"
        if FORM8_INFIX.match(stem):
            return "إ", ("a tāʾ in second position looks like form VIII, but the "
                         "transliteration carries only one i, which is form IV")
        return "إ", "the transliteration opens with i, and no waṣl signature matches"
    return "?", f"transliteration opens with {sorted(v for v in vowels if v)}"


def carry_hamza(word: str, carrier: str) -> str:
    """Put the carrier on the word's own ālif, past the definite article."""
    i = 2 if word.startswith("ال") and len(word) > 3 else 0
    return word[:i] + carrier + word[i + 1:]


# Author and cluster names carry no per-word transliteration, so the vowel that
# decides أ from إ has to come from the cluster's own romanization. The census
# found exactly these eight types; each is listed with the reading that settles it,
# so the card cites evidence rather than asserting a form.
NAME_HAMZA = {
    "ابو":        ("أبو", "Abū — every cluster spelling it reads Abū (c001, c024, c026…)"),
    "ابي":        ("أبي", "Abī — Ibn Abī al-Dunyā (c004), Ibn Abī Yaʿlā (c055)"),
    "احمد":       ("أحمد", "Aḥmad — ʿAlī b. Aḥmad al-Ḥarrālī (c008), Aḥmad al-Būnī (c062)"),
    "ارسطو":      ("أرسطو", "Arisṭū (c048) — the name of Aristotle takes qaṭʿ"),
    "الاب":       ("الأب", "al-Ab (c044)"),
    # Nisbas beginning ان-. An Arabic-side ^ان test would call these form VII and
    # leave the bare ālif; they are ordinary qaṭʿ nouns, and only the romanization
    # says so.
    "الانصاري":   ("الأنصاري", "al-Anṣārī (c087, c091) — a, so أ"),
    "الانباري":   ("الأنباري", "al-Anbārī (c069) — a, so أ"),
    "الاندلسي":   ("الأندلسي", "al-Andalusī — a, so أ"),
    "الاهوازي":   ("الأهوازي", "Abū ʿAlī al-Ahwāzī (c078) — a, so أ"),
    "الاسكندري":  ("الإسكندري", "al-Iskandarī (c064, c002) — i, so إ"),
    "الاسفاريني": ("الإسفاريني",
                   "al-Isfārayīnī (c090) — i, so إ. NOTE the yāʾ is a separate "
                   "question: the transliteration reads Isfārayīnī, which would be "
                   "الإسفراييني. This card fixes ONLY the hamza; rule on the yāʾ in "
                   "the note if you want it changed too."),
}


# --- author names in the title field -----------------------------------------
# The census found this is far smaller and more delicate than "strip the author
# from the title" suggests. Of the rows whose title contains a person-name, most
# are simply the work's real title (تفسير مقاتل, حكم أبي مدين) — stripping those
# leaves «تفسير» and «حكم». What is left is eight rows carrying a li- attribution
# tail, and even there five identify the BASE TEXT of a commentary rather than the
# row's own author: strip «لابن عربي» from all five and two pairs of distinct
# commentaries collapse to one string each. So: one card per row, keep as default,
# no bulk rule. `marker` is the bare token the tail begins at; the tail itself is
# read off the row at build time so it survives earlier orthographic passes.
ATTRIBUTION = [
    {"row": "r0021", "marker": "لابي", "verdict": "strip candidate",
     "note": "The author field holds «George Makdisi (ed.)» — the modern editor — "
             "so the tail is the only place the real author (Abū al-Wafāʾ ʿAlī b. "
             "ʿAqīl) is recorded. This is the one unambiguous case of an author "
             "name sitting in the title field; moving it to catalog_note loses "
             "nothing IF the cluster records Ibn ʿAqīl. Check that first."},
    *[{"row": r, "marker": "لابن", "verdict": "names the base text",
       "note": "«لابن عربي» identifies whose Mašāhid / Isrāʾ is being commented on — "
               "not who wrote this manuscript, which the author field already "
               "records. Note the collision check on this card comes back EMPTY: "
               "stripping the tails does not actually merge any two of these five "
               "titles (شرح كتاب الاسراء, كتاب شرح الاسراء and شرح الاسراء stay "
               "distinct strings). So the case for keeping rests on the tail being "
               "real bibliographic information, not on avoiding a collision."}
      for r in ("r0067", "r0068", "r0069", "r0070", "r0302")],
    {"row": "r0148", "marker": "للنفري", "verdict": "names the base text",
     "note": "Same shape as the Ibn ʿArabī commentaries: al-Tilimsānī's commentary "
             "on al-Niffarī's Mawāqif. The tail names the base text's author."},
    {"row": "r0285", "marker": "للمفتاح", "verdict": "false positive",
     "note": "NOT a name. li-l-miftāḥ al-fātiḥ li-l-bāb al-muqaffal is «for the key "
             "that opens the locked door» — the detector fired on the لل- proclitic "
             "alone. Nothing to do here; the card exists so the residue is a list "
             "you have seen, not a count you have to trust."},
]


def attribution_items(rows_by_id: dict, clusters: dict, kept: set) -> list[dict]:
    """One card per row carrying a li- attribution tail."""
    out = []
    for a in ATTRIBUTION:
        r = rows_by_id.get(a["row"])
        if r is None or a["row"] + "-attr" in kept:
            continue
        title = r.get("title") or ""
        toks = ARABIC.findall(title)
        # Fold to match, not just strip marks: r0021 writes لأبي with the hamza it
        # already carries, and a bare() comparison against the worklist's لابي
        # misses it entirely — the card vanished from the bake without a word.
        key = cluster.normalize_ar(a["marker"])
        idx = next((i for i, w in enumerate(toks)
                    if cluster.normalize_ar(w) == key), None)
        if idx is None:
            continue                      # already stripped — settled, drop it
        lat = (r.get("title_translit") or "").split()
        aligned = bool(toks) and len(toks) == len(lat)
        # Cut at the marker's own start so the tail is exactly what would go.
        cut = [m.start() for m in ARABIC.finditer(title)][idx]
        out.append({
            "id": a["row"] + "-attr", "stratum": "attribution", "row": a["row"],
            "marker": a["marker"], "verdict": a["verdict"], "note_why": a["note"],
            "title": title,
            "title_translit": r.get("title_translit") or "",
            "tail": title[cut:].strip(),
            "tail_translit": " ".join(lat[idx:]) if aligned else None,
            "proposed_title": title[:cut].strip(),
            "proposed_translit": " ".join(lat[:idx]) if aligned else None,
            "aligned": aligned,
            "author_ar": r.get("author") or "",
            "author": (clusters.get(r.get("author_cluster_id"), {})
                       .get("canonical_translit") or "—"),
            "catalog_note": r.get("catalog_note") or "",
            # Rows this one would become INDISTINGUISHABLE from if every tail in the
            # batch were stripped — the concrete cost of the bulk answer, computed
            # rather than asserted. Compare the stripped titles to each other, not
            # against the corpus's untouched ones (a prefix test reports a row that
            # merely starts the same way, which is a different and weaker claim).
            "collides_with": [],
        })
    by_stripped: dict[str, list[str]] = defaultdict(list)
    for o in out:
        by_stripped[cluster.normalize_ar(o["proposed_title"])].append(o["row"])
    for o in out:
        o["collides_with"] = sorted(
            x for x in by_stripped[cluster.normalize_ar(o["proposed_title"])]
            if x != o["row"])
    return out


def hamza_items(rows: list[dict], clusters: list[dict], covered: set[str]) -> list[dict]:
    """One card per bare-ālif-initial word type that should carry أ or إ.

    Spans three surfaces at once — row titles, row.author, and each cluster's
    canonical_ar / variants — because the ruling is the same wherever the word
    sits. Safe by construction for the authority: normalize_ar folds أ إ آ ٱ back
    to ا, so restoring a carrier changes no cluster key, exactly as the šaddah
    changed no lexicon key.
    """
    pairs: dict[str, set[str]] = defaultdict(set)          # word -> transliterations
    titles: dict[str, set[str]] = defaultdict(set)
    authors: dict[str, set[str]] = defaultdict(set)
    names: dict[str, set[str]] = defaultdict(set)

    for r in rows:
        ar = ARABIC.findall(r.get("title") or "")
        lat = (r.get("title_translit") or "").split()
        aligned = bool(ar) and len(ar) == len(lat)
        for i, w in enumerate(ar):
            titles[bare(w)].add(r["id"])
            if aligned:
                pairs[bare(w)].add(lat[i])
        for w in ARABIC.findall(r.get("author") or ""):
            authors[bare(w)].add(r["id"])
    for c in clusters:
        for s in [c.get("canonical_ar")] + list(c.get("variants") or []):
            for w in ARABIC.findall(s or ""):
                names[bare(w)].add(c["cluster_id"])

    out = []
    for w in sorted(set(titles) | set(authors) | set(names),
                    key=lambda x: (-len(titles[x]) - len(authors[x]), x)):
        if w in covered or set(w) & set("أإآٱ"):
            continue                     # already carries a hamza — settled
        # The gate the no-transliteration branch used to skip: only a word whose
        # OWN initial letter is a bare ālif is a candidate at all. Without this,
        # every author-field word reached the verdict and came back "undecidable",
        # burying 40 real cards under 200 that were never candidates.
        stem = w[2:] if w.startswith("ال") and len(w) > 3 else w
        if not stem.startswith("ا"):
            continue
        ts = sorted(pairs.get(w, ()))
        if ts:
            carrier, why = hamza_verdict(w, ts)
        elif w in NAME_HAMZA:
            carrier, why = None, NAME_HAMZA[w][1]
        else:
            carrier, why = "?", ("no transliteration is aligned to this word, so "
                                 "the vowel that decides qaṭʿ from waṣl is not "
                                 "recoverable here")
        if ts and carrier is None:
            continue                     # hamzat waṣl — the bare ālif is correct
        proposal = (NAME_HAMZA[w][0] if not ts and w in NAME_HAMZA
                    else carry_hamza(w, carrier) if carrier not in (None, "?") else None)
        surfaces = []
        if titles[w]: surfaces.append(f"{len(titles[w])} title(s)")
        if authors[w]: surfaces.append(f"{len(authors[w])} author field(s)")
        if names[w]: surfaces.append(f"{len(names[w])} cluster name(s)")
        out.append({
            "id": "h-" + w, "word": w, "proposed": proposal,
            "translit": ts[0] if len(ts) == 1 else None,
            "translits": ts,
            "confidence": "hamza" if proposal else "hamza-manual",
            "scope": {"titles": sorted(titles[w]), "authors": sorted(authors[w]),
                      "clusters": sorted(names[w])},
            "only_rows": sorted(titles[w]) or None,
            "reason": (
                f"Word-initial bare ālif in {', '.join(surfaces)}."
                + (f"  Derived أ/إ: {why}." if proposal else f"  No proposal — {why}."
                   "  Type the form.")
                + "  Restoring the carrier changes no cluster or lexicon key: "
                  "normalize_ar folds أ إ آ ٱ back to ا."),
        })
    return out


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
    kept = set((json.loads(KEEPS.read_text(encoding="utf-8")).get("keeps") or {})
               if KEEPS.exists() else {})
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
        if w["current"] not in toks or w["id"] in kept:
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
    derived = (shadda_items(corpus, readings, covered, translit_fix)
               + hamza_items(corpus, data["clusters"], covered | {"مطالب"}))
    for o in ORTHO + derived:
        ids = sorted(set(occ.get(o["word"], [])))
        if o.get("only_rows"):
            ids = [i for i in ids if i in set(o["only_rows"])]
        if o["id"] in kept:
            continue                      # ruled keep in an earlier batch
        # `occ` is keyed mark-BLIND, the way the ingest matches. That is right for
        # FINDING the word and wrong for deciding whether it is still open: a fix
        # that only adds marks (a šaddah) leaves the key unchanged, so the row keeps
        # matching and the card returns forever. Ask the sharper question — does any
        # occurrence still differ from the proposal?
        if o.get("proposed"):
            ids = [i for i in ids
                   if any(bare(m.group()) == o["word"] and m.group() != o["proposed"]
                          for m in ARABIC.finditer(rows_by_id[i].get("title") or ""))]
        scope = o.get("scope") or {}
        if not ids and not (scope.get("authors") or scope.get("clusters")):
            continue                      # already canonicalized — settled, drop it
        # The transliteration the word carries TODAY. The ingest needs it to swap
        # the token inside any affected row that already has a title_translit —
        # rewriting the Arabic without it would leave the two out of step.
        key = cluster.normalize_ar(o["word"])
        was = sorted(readings.get(key, {})) if key in readings else []
        # Most of these fixes are invisible to matching: normalize_ar strips marks
        # and folds hamza carriers, so a šaddah or an أ leaves the key untouched. A
        # card that ALSO changes a letter does move the key, and that is a different
        # kind of edit — the annotator should be told which one they are making.
        key_changes = bool(o.get("proposed")) and (
            cluster.normalize_ar(o["word"]) != cluster.normalize_ar(o["proposed"]))
        ortho.append({
            **o, "stratum": "ortho", "key_changes": key_changes,
            "translit_was": lex.get(key) or (was[0] if len(was) == 1 else None),
            "rows": [{
                "id": i,
                "title": rows_by_id[i].get("title") or "",
                "after": (rows_by_id[i].get("title") or "").replace(
                    o["word"], o["proposed"]) if o.get("proposed") else None,
                "translit": rows_by_id[i].get("title_translit") or "",
            } for i in ids],
        })

    attributions = attribution_items(rows_by_id, clusters, kept)

    payload = {
        "schema_version": 1,
        "task": "translit-adjudication",
        "generated_from": "data/data.json + review/translit_words_decisions.json",
        # The browser cannot call unicodedata, so the pipeline's own notion of an
        # Arabic mark travels WITH the payload. The headless gate reads it from
        # here rather than carrying a hand-written copy — that copy was a fourth
        # definition, and it disagreed with the two it was checking.
        "mark_class": normalize.mark_class_js(),
        "counts": {"witness": len(witnesses), "homograph": len(homographs),
                   "ortho": len(ortho), "attribution": len(attributions)},
        "strata": {"witness": witnesses, "homograph": homographs, "ortho": ortho,
                   "attribution": attributions},
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
    print(f"attribution: {len(attributions)}")
    print(f"\nWrote {OUT}  ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
