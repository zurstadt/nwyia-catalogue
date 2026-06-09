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

import re
import unicodedata

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
    m = _FOLIO_START.search(s)
    if not m:
        return s, ""
    shelfmark = s[: m.start()].rstrip(" ,;").strip()
    folios = s[m.start():].strip()
    return shelfmark, folios


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


def normalize_rows(rows: list[dict]) -> list[dict]:
    """Return new rows with English places, split shelfmark/folios, clean authors."""
    out: list[dict] = []
    for r in rows:
        shelfmark, folios = split_shelfmark(r.get("shelfmark_raw", ""))
        title = space_letters_digits(strip_orphan_marks(r.get("title", "").strip()))
        author = strip_orphan_marks(r.get("author", "").strip())
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
