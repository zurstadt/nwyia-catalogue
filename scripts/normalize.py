"""Readable-English place names, shelfmark/folio splitting, and author cleanup.

This module is the single place that turns the raw extraction (terse French and
abbreviated library tokens, an unsplit "Num. Ms." cell, Latin author strings in
"Last, first" order) into the clean, English-readable fields the app displays.

Design rules:
  * Every institution is preserved — we only translate the *surface form* to a
    readable English name. Nothing is merged away or re-derived from another
    column. Spelling/casing variants of the SAME library (e.g. "Valiuddin" /
    "Veliyuddin") fold to one display form; distinct institutions never do.
  * Functions are pure: they return new dicts/strings and never mutate input.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path


def jaro_similarity(s1: str, s2: str) -> float:
    """Jaro similarity of two strings, in [0, 1].

    Two characters match when they are equal and lie within a window of
    ``max(len1, len2) // 2 - 1`` positions of each other; a transposition is a
    pair of matched characters that appear in a different relative order.
    """
    len1, len2 = len(s1), len(s2)
    if not len1 and not len2:
        return 1.0
    if not len1 or not len2:
        return 0.0
    window = max(max(len1, len2) // 2 - 1, 0)

    s1_matched = [False] * len1
    s2_matched = [False] * len2
    matches = 0
    for i, ch in enumerate(s1):
        for j in range(max(0, i - window), min(len2, i + window + 1)):
            if not s2_matched[j] and s2[j] == ch:
                s1_matched[i] = s2_matched[j] = True
                matches += 1
                break
    if not matches:
        return 0.0

    # Count characters that matched but in a different order.
    transpositions = 0
    j = 0
    for i in range(len1):
        if not s1_matched[i]:
            continue
        while not s2_matched[j]:
            j += 1
        if s1[i] != s2[j]:
            transpositions += 1
        j += 1
    transpositions //= 2

    return (matches / len1
            + matches / len2
            + (matches - transpositions) / matches) / 3.0


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity, in [0, 1].

    Jaro, boosted for strings sharing a leading prefix (up to 4 characters,
    scaling factor 0.1), and only when the Jaro score already clears 0.7 — the
    standard Winkler boost threshold.

    Implemented here in pure Python on purpose. It is the ONLY similarity call
    the pipeline makes (``cluster.cluster_confidence``), and depending on a
    compiled extension for it made the whole pipeline unrunnable whenever the
    installed wheel's architecture stopped matching the interpreter's. A
    research pipeline should still run years from now on an unknown machine.
    """
    jaro = jaro_similarity(s1, s2)
    if jaro <= 0.7:
        return jaro
    prefix = 0
    for a, b in zip(s1[:4], s2[:4]):
        if a != b:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def write_json_atomic(path, obj, *, backup: bool = True) -> None:
    """Serialize ``obj`` to ``path`` as UTF-8 JSON without risk of truncation.

    Writes to a temp file in the same directory then ``os.replace``s it into
    place (atomic on POSIX), so a crash mid-write can never leave a half-written
    file. When ``backup`` is set and the target already exists, the prior file
    is first copied to ``<path>.bak`` as a last-good snapshot — important because
    ``authority.json`` is the only on-disk record of the user's adjudication.
    """
    path = Path(path)
    if backup and path.exists():
        bak = path.with_name(path.name + ".bak")
        bak.write_bytes(path.read_bytes())
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

# --- City exonyms: French/local token → English. Identity-preserving. ---------
# Tokens not listed (Istanbul, Paris, Berlin, Rabat, Ankara, Burdur, Birmingham,
# Kastamonu, Madrid, Konya, Oxford, Bankipore, Cambridge, Leipzig, Mashhad) pass
# through unchanged.
CITY_DISPLAY: dict[str, str] = {
    "Alexandrie": "Alexandria",
    "Beyrouth": "Beirut",
    "Caire": "Cairo",
    "Damas": "Damascus",
    "Escurial": "El Escorial",
    "Fes": "Fez",
    "Londres": "London",
    "Tubingue": "Tübingen",
    "Téhéran": "Tehran",
    "Vatican": "Vatican City",
    "Vienne": "Vienna",
}

# --- Library names: raw token → readable English. Identity-preserving. ---------
# Case/spelling variants of one collection fold to a single display form; this is
# normalization of the SAME institution, not a merge of distinct ones.
LIBRARY_DISPLAY: dict[str, str] = {
    "AL-Assad": "al-Asad National Library",
    "Al-Assad": "al-Asad National Library",
    "Al-Azhariyya": "al-Azhar Library",
    "Asitan quds": "Āstān-i Quds Library",
    "Ayasofya": "Ayasofya",
    "BAV": "Vatican Apostolic Library",
    "BM": "British Museum / British Library",
    "BN": "National Library",
    "BO": "Bibliothèque Orientale (USJ)",
    "Bagdadli vehbi": "Bağdatlı Vehbi",
    "Baladiya": "Municipal Library (Baladiyya)",
    "Bayazit": "Beyazıt Library",
    "Bibliotheque générale": "General Library",
    "Bibliothèque générale": "General Library",
    "Bibliothèque du musée de topkapi": "Topkapı Palace Museum Library",
    "Bodleiana": "Bodleian Library",
    "Bursa": "Bursa Library",
    "Escurial": "El Escorial Library",
    "India office": "India Office Library",
    "Kastamonu": "Kastamonu Library",
    "Kattani": "Kattānī Collection",
    "Koprulu": "Köprülü Library",
    "Laleli": "Laleli Library",
    "Ms. Malik": "Malek Library",
    "Oriental public library": "Oriental Public Library (Bankipore)",
    "Qarawiyyin": "al-Qarawiyyīn Library",
    "Selly Oak": "Selly Oak Colleges Library",
    "Suleymaniye": "Süleymaniye Library",
    "Topkapi": "Topkapı Palace Museum Library",
    "Universitatsbiblio thek": "Universitätsbibliothek",
    "University library": "University Library",
    "Université": "University",
    "Université de Harvard": "Harvard University",
    "Université, fac. Hist. - géo.": "University (Faculty of History & Geography)",
    "Valiuddin": "Veliyüddin Efendi",
    "Veliyuddin": "Veliyüddin Efendi",
    "Vehabi": "Vehbi Efendi",
    "Yeni cami": "Yeni Cami Library",
    "Yusuf aga": "Yusuf Ağa Library",
}


def display_city(token: str) -> str:
    return CITY_DISPLAY.get(token, token)


def display_library(token: str) -> str:
    return LIBRARY_DISPLAY.get(token, token)


# Cities already in their English form — intentionally pass through unchanged.
CITY_PASSTHROUGH = {
    "Istanbul", "Paris", "Berlin", "Rabat", "Ankara", "Burdur", "Birmingham",
    "Kastamonu", "Madrid", "Konya", "Oxford", "Bankipore", "Cambridge",
    "Leipzig", "Mashhad",
}


def unmapped_places(raw_rows: list[dict]) -> tuple[set[str], set[str]]:
    """Raw city/library tokens with no display-map entry, for review.

    Call on the *raw* rows (before normalize_rows). Cities known to be already
    English are excluded; any leftover token is one the maps don't yet cover.
    """
    cities = {
        r["city"] for r in raw_rows
        if r["city"] and r["city"] not in CITY_DISPLAY and r["city"] not in CITY_PASSTHROUGH
    }
    libs = {
        r["library"] for r in raw_rows
        if r["library"] and r["library"] not in LIBRARY_DISPLAY
    }
    return cities, libs


# --- Shelfmark vs folios ------------------------------------------------------
# The Num. Ms. cell mixes an institutional shelfmark (e.g. "Arabe 1397",
# "Isma'il sa'ib 1571", "2821 spr 851") with a folio/page reference
# ("fol.55b-63b", "pp.141-145"). Line wrapping in the PDF leaves artifacts:
# a stray space inside numeric ranges ("fol.1- 75a"), a missing space between a
# word and digits ("Arabe1398"), inconsistent "Fol." casing and commas.

# Start of the folio/page portion: fol./fols./f./p./pp. immediately followed
# (allowing a comma/space) by a digit.
_FOLIO_START = re.compile(r"(?i)\b(?:fols?|ff?|pp?)\.\s*,?\s*(?=\d)")
# Whole value is just an extent descriptor ("13 folios", "6 folios").
_FOLIO_EXTENT = re.compile(r"(?i)^\d+\s+(?:folios?|ff?\.?|pages?)\b")
# A parenthesised extent: "(2 vols.)", "(4 vols)", "(17 pages dactylograhiées)".
# Nwyia wrote these alongside the call number ("Besir aga 36 (3 vols.)"), so they
# arrive glued to the shelfmark even though they describe the extent, not the
# institution's reference.
_PAREN_EXTENT = re.compile(
    r"\(\s*\d+\s*(?:vols?|tomes?|pages?|folios?|ff?)\b[^)]*\)", re.I)
# The same, anchored to the end of the value.
_PAREN_EXTENT_TAIL = re.compile(_PAREN_EXTENT.pattern + r"\s*$", re.I)


def clean_shelfmark_raw(s: str) -> str:
    """Repair line-break artifacts in a raw Num. Ms. value."""
    s = re.sub(r"\s+", " ", s).strip()
    # Add a space after a comma that runs straight into the next token.
    s = re.sub(r",(?=\S)", ", ", s)
    # Collapse spaces around a hyphen sitting between word chars (range wrap).
    s = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "-", s)
    # Insert the missing space between a word (3+ letters) and digits.
    s = re.sub(r"([A-Za-zÀ-ÿ]{3,})(\d)", r"\1 \2", s)
    # Normalize folio/page marker casing ("Fol." → "fol.", "PP." → "pp.").
    s = re.sub(r"(?i)\b(fols?|ff?|pp?)\.", lambda m: m.group(0).lower(), s)
    # Drop a comma directly after the folio marker ("fol.,76v" → "fol.76v").
    s = re.sub(r"(?i)\b(fols?|ff?|pp?)\.\s*,\s*", r"\1.", s)
    return s.strip()


# BnF (Paris) shelfmark classes. These names ARE the Bibliothèque nationale de
# France manuscript collections (Arabe, Syriaque, Persan, …), so a shelfmark in
# one of them identifies the holding library unambiguously — a reliable signal,
# distinct from (and not dependent on) the library column. Used to repair rows
# whose city was left blank and wrongly inherited a previous block's city.
_BNF_CLASS = re.compile(r"(?i)^(?:arabe|syriaque|syr|persan|h[eé]breu|turc|copte)\b")
BNF_CITY = "Paris"
BNF_LIBRARY = "Bibliothèque Nationale de France"


def is_bnf_shelfmark(shelfmark: str) -> bool:
    return bool(_BNF_CLASS.match(shelfmark.strip()))


def split_shelfmark(raw: str) -> tuple[str, str]:
    """Split a raw Num. Ms. value into (shelfmark, folios)."""
    s = clean_shelfmark_raw(raw)
    if not s:
        return "", ""
    # Pure extent descriptor → it is folio information, no shelfmark.
    if _FOLIO_EXTENT.match(s):
        return "", s
    # Value is nothing but parenthesised extents ("(3 vols.)") → all extent.
    if s and not _PAREN_EXTENT.sub("", s).strip():
        return "", s
    # A trailing parenthesised extent belongs in folios, and what precedes it is
    # the shelfmark ("Besir aga 36 (3 vols.)" → "Besir aga 36" + "(3 vols.)").
    tail = _PAREN_EXTENT_TAIL.search(s)
    if tail:
        head = s[: tail.start()].rstrip(" ,;").strip()
        extent = tail.group(0).strip()
        # Anything else in the head is still split on a folio marker as usual.
        inner = _FOLIO_START.search(head)
        if inner:
            folios = f"{head[inner.start():].strip()} {extent}".strip()
            return head[: inner.start()].rstrip(" ,;").strip(), folios
        return head, extent
    m = _FOLIO_START.search(s)
    if not m:
        return s, ""
    shelfmark = s[: m.start()].rstrip(" ,;").strip()
    folios = s[m.start():].strip()
    return shelfmark, folios


# --- Arabic word tokens and marks: the ONE definition -------------------------
# Four copies of this pair lived across the pipeline and two of them were wrong.
# `[ء-ٰٟ-ۓ]` parses as `[ء-ٰ] ∪ [ٟ-ۓ]` = U+0621–U+06D3, and the mark class `[ً-ٰٟ]`
# is the RANGE U+064B–U+0670 — so "stripping marks" also deleted the Arabic-Indic
# digits ٠–٩ (U+0660–U+0669), the percent/decimal separators (U+066A–U+066D) and
# the base letters dotless beh ٮ and dotless qaf ٯ (U+066E–U+066F).
#
# Define a mark STRUCTURALLY rather than by codepoint range, the way
# cluster.normalize_ar already does: a mark is what Unicode calls combining. A
# hand-written range drifts — `unicodedata.combining` cannot.
#
# The word class must MATCH the marks (excluding them splits a word at its
# šaddah, leaving two lexicon keys that never get filled) and must NOT match the
# Arabic comma U+060C or the Arabic-Indic digits U+0660–U+0669 — the first split a
# comma-suffixed title word off its bare form, the second glued a numeral onto the
# word beside it. Tatweel U+0640 stays inside the range on purpose, so a stretched
# word remains ONE token for bare() to fold. Written as escapes, not as literal
# Arabic: the literal form renders right-to-left in every editor, which is exactly
# how `[\u0621-\u0670\u065F-\u06D3]` came to be read as something narrower than it is.
AR_WORD = re.compile(r"[\u0621-\u065F\u0670-\u06D3]+")
TATWEEL = "ـ"


def bare(w: str) -> str:
    """The surface with vowel/šaddah marks and tatweel stripped.

    This is how the worklist keys a word, so it has to agree with
    ``cluster.normalize_ar`` about what a mark is: that function drops every
    combining character AND the tatweel. A ``bare`` that kept the tatweel would
    key كـتاب apart from كتاب while the lexicon keyed them together.
    """
    return "".join(c for c in (w or "")
                   if not unicodedata.combining(c) and c != TATWEEL)


def mark_class_js() -> str:
    """The combining marks of the Arabic block as a JavaScript character class.

    The browser cannot call ``unicodedata``, so the class is derived here and
    baked into the app's payload. A hand-written copy on the JS side is how the
    headless gate came to use a different notion of "mark" than the pipeline it
    verifies.
    """
    marks = [c for c in range(0x0600, 0x0700)
             if unicodedata.combining(chr(c))] + [ord(TATWEEL)]
    marks.sort()
    out, i = [], 0
    while i < len(marks):
        j = i
        while j + 1 < len(marks) and marks[j + 1] == marks[j] + 1:
            j += 1
        out.append(f"\\u{marks[i]:04X}"
                   + (f"-\\u{marks[j]:04X}" if j > i else ""))
        i = j + 1
    return "[" + "".join(out) + "]"


# --- Author cleanup -----------------------------------------------------------
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_AR_LETTER = re.compile(r"[ء-يٱ-ۓ]")


def has_arabic(s: str) -> bool:
    return bool(_ARABIC_RE.search(s))


def strip_orphan_marks(s: str) -> str:
    """Drop combining marks not sitting on an Arabic base letter.

    The PDF extraction occasionally floats a shadda next to a space or a
    parenthesis ("السلمي ّ", "المقدسي ّ(محقق)"); those are artifacts. A mark
    that genuinely follows an Arabic letter is kept.
    """
    out: list[str] = []
    for ch in s:
        if unicodedata.combining(ch):
            if out and _AR_LETTER.match(out[-1]):
                out.append(ch)
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _cap_word(w: str) -> str:
    """Capitalize the first letter, preserve the rest (so 'BnF' survives)."""
    for i, ch in enumerate(w):
        if ch.isalpha():
            return w[:i] + ch.upper() + w[i + 1:]
    return w


def space_letters_digits(s: str) -> str:
    """Insert a space where an Arabic letter is glued to an ASCII number.

    The PDF extraction strands a count next to the word ("خصلة الامام50",
    "فريضة54"); this separates them ("خصلة الامام 50"). Arabic-Indic digit lists
    joined by "،" (e.g. "4،3،2") and Latin segments ("(54 pages)") are untouched.
    Note: only spacing is fixed, not word order — a leading count may still read
    after the noun, which the adjudicator can reorder if needed.
    """
    s = re.sub(r"([ء-يٱ-ۓ])([0-9])", r"\1 \2", s)
    s = re.sub(r"([0-9])([ء-يٱ-ۓ])", r"\1 \2", s)
    return s


def normalize_latin_author(s: str) -> str:
    """Tidy a Latin-script author string.

    'Last, first' → 'First Last' with sensible casing ('Ritter, hellmut' →
    'Hellmut Ritter'). Names without a comma keep their order (only casing is
    fixed), since the correct order can't be inferred reliably — e.g. Syriac
    'Qatraya gabriel' is left for the adjudicator to confirm.
    """
    s = re.sub(r"\s+", " ", s).strip()
    if "," in s:
        last, first = (p.strip() for p in s.split(",", 1))
        s = f"{first} {last}".strip()
    return " ".join(_cap_word(w) for w in s.split(" ") if w)


# Author strings that mean "not attributed / anonymous" rather than a real name.
# Nwyia's catalogue marks unattributed works "NA" (occasionally "N/A"); left as-is
# these seed a spurious one-row author cluster, so we treat them as a blank author.
AUTHOR_PLACEHOLDERS = {"na", "n/a", "n.a.", "n.a", "n a"}


def blank_author_placeholder(s: str) -> str:
    """Map an unattributed-author placeholder (NA, N/A, …) to an empty string."""
    return "" if (s or "").strip().lower() in AUTHOR_PLACEHOLDERS else (s or "")


def normalize_rows(rows: list[dict]) -> list[dict]:
    """Return new rows with English places, split shelfmark/folios, clean authors."""
    out: list[dict] = []
    for r in rows:
        shelfmark, folios = split_shelfmark(r.get("shelfmark_raw", ""))
        title = space_letters_digits(strip_orphan_marks(r.get("title", "").strip()))
        author = blank_author_placeholder(strip_orphan_marks(r.get("author", "").strip()))
        if author and not has_arabic(author):
            author = normalize_latin_author(author)
        city = display_city(r.get("city", ""))
        library = display_library(r.get("library", ""))
        # A BnF-class shelfmark (Arabe, Syriaque, Persan, …) *can* pin the holding
        # library to the BnF in Paris — but ONLY when the library column is blank
        # or already names the BnF ("BN"). The Vatican (Vat. ar./Vat. syr.) and the
        # Escorial use the very same shelfmark prefixes, so the prefix alone is not
        # decisive and must never override an explicit, different institution.
        raw_lib = (r.get("library", "") or "").strip()
        if is_bnf_shelfmark(shelfmark) and raw_lib in ("", "BN"):
            city, library = BNF_CITY, BNF_LIBRARY
        out.append({
            **{k: v for k, v in r.items() if k != "shelfmark_raw"},
            "city": city,
            "library": library,
            "shelfmark": shelfmark,
            "folios": folios,
            "title": title,
            "author": author,
        })
    return out
