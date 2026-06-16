# Fonds P. Nwyia — Project Progress & Features

A running log of what has been built and surfaced for the *Index Lieux* of Paul
Nwyia's manuscript collection, the methods and resources that worked, and what
remains. Companion to `findings.md` (scholarly provenance/identification notes)
and `README.md` (layout & usage).

_Last updated: 2026-06-16._

## Snapshot

- **347 manuscripts**, **117 author clusters** (116 with rows).
- **Publication status:** 139 published · 7 manuscript-only · 201 unknown (was
  2 published at the start). **120 rows** carry a `work_url` (edition/catalogue link).
- **Author metadata:** 60 clusters carry `full_name`, `dates`, and authority links.
- **32 rows** remain unclustered (mostly genuine fragments / generic incipits).

## What has been built

### 1. Pipeline & persistence model (durable, idempotent)
The pipeline is `extract.py → normalize.py → cluster.py → data/data.json`, with
`harvest_authority.py` capturing hand-work into `data/authority.json` so a
re-cluster never reverts it. Key properties established this cycle:
- **Stable-baseline overrides.** `harvest` diffs the live `data.json` against the
  *normalized raw extraction* (not against the generated file), so overrides are
  idempotent and never self-erase. `row_overrides` now ~180+ entries.
- **Atomic, UTF-8 writes** with `.bak` snapshots (`normalize.write_json_atomic`).
- **Durable cluster metadata.** `full_name`, `dates`, `authorities`,
  `canonical_*`, `user_confirmed` all round-trip through harvest → cluster.
- **Safeguards:** id-drift abort in harvest; heuristic `n###` ids skip pinned ids;
  `"NA"`/placeholder authors blanked so anonymous works don't seed clusters.
- **Working rule:** `data/data.json` is the single source of truth; edits are made
  there and re-harvested. `cluster.py` is the safety net, not the daily driver.

### 2. Adjudicator app (`app/index.html`) — hardened
Recompute cluster counts + drop phantom clusters on export; Save-to-GitHub
concurrency guard that preserves in-flight edits; single-level undo (`z`);
`beforeunload` warning; debounced search/index; misleading kbd hint removed.

### 3. Public catalogue site (`site/`) — new
Self-contained static site (no build), reads the live `data/data.json`, styled
after digitalsufism.github.io on a warm manuscript palette (Spectral/Amiri, RTL).
- `index.html` — bilingual hero, live stats, Tübingen-Depot highlight.
- `catalogue.html` — search + filter (city/library/author/status) + sort, RTL
  titles, transliteration, pub-status badges, citation/edition links; honours an
  `?author=` deep link.
- `authors.html` — browsable author index: name, fullest name, dates, manuscript
  count, and authority-link chips; deep-links into the catalogue.
- `about.html` — Nwyia, methodology, the provenance findings.
- Serve from the project root: `python3 -m http.server 8000` →
  `/site/index.html`. For GitHub Pages, publish from the repo root so `/site/`
  and `/data/` are both served. (Not yet deployed; no git remote configured.)

### 4. Publication status (139/347)
Each manuscript traced, where possible, to a published edition (`pub_status`,
`pub_citation`, `work_url`). Major clusters done: al-Sulamī, al-Ḥallāj,
al-Muḥāsibī, al-Khargūshī, Abū Ṭālib al-Makkī, al-Tustarī, al-Kharrāz, al-Junayd,
al-Kalābādhī, Ibn Yazdānyār, Ibn ʿAṭāʾ Allāh (Ḥikam), Šaqīq al-Balḫī, al-Niffarī,
Ibn ʿAbbād, Ibn al-ʿArabī, al-Tirmidhī, Ibn Abī al-Dunyā, al-Qushayrī (Laṭāʾif),
al-Ghazālī (Tahāfut), al-Qūnawī, al-Makzūn al-Sinjārī, al-Ḥarrālī, Ibn Sawdakīn,
al-Tilimsānī.

### 5. Author metadata (~55 substantive figures + recoveries)
Per cluster: `full_name` (fullest nasab), `dates` (AH/CE), and `authorities`
(Wikidata, VIAF, GND, Wikipedia, TDVİA, EI, OpenAlex, Google Scholar).

### 6. Title-fingerprint author recovery
Once works were identified, the *title* fingerprints the author for rows the
name-clustering missed. Recovered 9 figures (5 new clusters + al-Shaʿrānī unmasked
from an "al-Anṣārī" singleton + 3 returned to existing clusters). Unclustered 42 → 32.

## Methods & resources that worked (the toolkit)

- **digitalsufism.github.io** — published-editions DB for early Sufism; data at
  `/data/bibliography.json` (31 authors, 146 works). See memory `digitalsufism-bibliography`.
- **MIAS Catalogue of Ibn ʿArabī's Works** (Osman Yahia RG numbers) — `pdfplumber`
  to extract; cite by RG + authenticity code. See memory `mias-ibn-arabi-catalogue`.
- **TDVİA** (islamansiklopedisi.org.tr) — WebFetch-friendly "Eserleri" lists with editions.
- **EI² / EI³** (Brill referenceworks) — bibliographies; pages 403 on fetch, so
  the user has pasted key entries; EI3 links stored as Crossref-verified DOIs.
- **Wikidata** — the authority-link backbone. Two tricks that mattered:
  (a) **disambiguate by death-year** against the known date (caught a "died 1829"
  pseudo-Farabi and a "died 2003" pseudo-Jāmī); (b) when the Latin
  `wbsearchentities` misses, **search the Arabic label** (`language=ar`) — found
  al-Shaʿrānī, the two Nasafīs, al-Dawānī. Fetch `Special:EntityData/Q….json` for
  verified VIAF/GND/Wikipedia.
- **Nwyia's own editions** (IdRef 030170745 → Sudoc): *Trois œuvres inédites*
  (Šaqīq, al-Niffarī), the *Ḥikam* (1972), Ibn ʿAbbād's letters.
- One-off finds: al-Khayyāṭī's *Turāth Abī al-Ḥasan al-Ḥarrālī … fī al-tafsīr*
  (Tetouan); ʿAbd al-Hādī al-Kharsa's *Sharḥ al-Qaṣīda al-Muḥammadiyya* (archive.org).

## Data model

`row`: city, library, shelfmark, folios, title (+ `_translit`, `_translation`),
author (+ `_translit`, `_translation`), archive (Fonds cote), `author_cluster_id`,
`catalog_note`, `pub_status` (unknown|published|manuscript|partial), `pub_citation`,
`work_url`, `discrepancy_note`, `page`, `id`.
`cluster`: cluster_id, canonical_ar, canonical_translit, **full_name**, **dates**,
variants, count, confidence, user_confirmed, **authorities** [{source,title,url}].

## Roadmap / what's left

- **~201 unknown pub_status.** Much is blocked behind login-gated catalogues
  (Süleymaniye / Türkiye Yazma Eserler, other İstanbul & Anatolian collections,
  USJ Beirut, Rabat, Ankara DTCF) the user must pull logged-in. The openly
  resolvable remainder is the minor works of authors already touched.
- **32 unclustered rows** — genuine fragments / generic incipits; need external
  evidence. The *Ṭabaqāt* fragment (r0022) is parked (too little to go on).
- **Open identity flag:** c091 «ʿAbd Allāh al-Anṣārī» was labelled al-Harawī in the
  bulk metadata pass, but its row r0193 «fī anwāʾ al-ʿulūm» doesn't confirm it — verify.
- **5 figures lack a Wikidata QID** (al-Qushayrī, al-Niffarī, al-Khargūshī,
  al-Fārābī, al-Rūdhbārī) — they have name/dates + EI/TDVİA + discovery links;
  add QIDs (and thus VIAF/GND) when found.
- **Long-tail author metadata** — minor count-1 figures beyond the ~55 substantive.
- **Site:** surface `full_name`/`dates` inside catalogue entries (not just the
  Authors page); deploy to GitHub Pages once a remote is set.
