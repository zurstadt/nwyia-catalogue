# Fonds P. Nwyia — Index Lieux (searchable)

A single-page, static web app for searching and adjudicating the *Index Lieux* of
Paul Nwyia's manuscript collection at the Bibliothèque Orientale (Saint-Joseph
University, Beirut). Built from `Nwyia_MSCollection.pdf`.

## Layout

```
app/
  index.html            The web app. Serve the project root, then open /app/index.html.
data/
  data.json             The data the app reads (rows, clusters, schema). Source of truth.
  authority.json        Curated cluster canonicals/translits; reused by the pipeline.
source/
  raw.txt               Original extracted text.
  raw_rows.json         Intermediate extraction output (PDF → rows).
scripts/
  extract.py            (re)build source/raw_rows.json from the PDF.
  normalize.py          Pure helpers (place names, shelfmark/folio split, author cleanup).
  cluster.py            (re)build data/data.json from raw_rows.json + authority.json.
  harvest_authority.py  Build data/authority.json from an exported data.json.
  name_cluster.py       OpenRefine-style fuzzy grouping of similar author names → review worklist.
backups/                Timestamped data.json snapshots + stray exports.
site/                   Public static catalogue site (Home / Catalogue / Authors / Scholarship / About).
review/
  name_clusters.html    Adjudicate similar-name groups (confirm merges/identifications).
  name_clusters.json    Worklist produced by scripts/name_cluster.py.
docs/
  findings.md           Provenance & identification notes for the forthcoming publication.
  PROGRESS.md           Project progress & features log: methods, resources, roadmap.
  UX-DECISIONS.md       Deliberate interaction decisions in the app — read before changing it.
```

All scripts resolve paths from the project root (the parent of `scripts/`), so they
can be run from anywhere, e.g. `python3 scripts/cluster.py`.

## Sweeping one column (Edit columns)

Pick a **Column**, set the filter to **Blank**, and type. The screen shows only the Arabic being
read from and the field being typed into; `ctx ▾` opens the full entry, the key reference and the
shorthand table. `Enter` next · `Shift+Enter` previous · `Alt+↑` copies the previous row's value ·
`Ctrl+S` save.

On the transliteration columns (`Title (translit.)`, `Author (translit.)`) an ASCII shorthand is
expanded as you type — it is **not** applied to the translation columns, so English prose is never
rewritten:

| type | get | type | get | type | get | type | get |
|---|---|---|---|---|---|---|---|
| `a:` | ā | `h.` | ḥ | `d_` | ḏ | `'` | ʾ |
| `i:` | ī | `s.` | ṣ | `t_` | ṯ | `` ` `` | ʿ |
| `u:` | ū | `d.` | ḍ | `g_` | ġ | | |
| | | `t.` | ṭ | `h_` | ḫ | | |
| | | `z.` | ẓ | `s_` | š | | |
| | | | | `j_` | ǧ | | |

A title whose every word you have already transliterated is **pre-filled** and tinted; `Enter`
accepts it, typing replaces it, and stepping past leaves the row blank. Words are learned only from
rows where the Arabic and Latin word counts match, so an ambiguous pairing is skipped rather than
guessed.

Accepting a pre-fill is a real decision, but it is not the same as reading the Arabic and writing the
line out — so the app records **what it proposed**, beside the decision, at the moment you made it.
`harvest_authority.py` keeps that in `authority.json` (it accumulates across harvests), and the split
is derived by comparison, never asserted by the app:

```sh
python3 scripts/report_provenance.py            # totals
python3 scripts/report_provenance.py --list     # per row, with the overridden proposals
```

`accepted` = the value equals what was proposed · `overridden` = a proposal was shown and you wrote
something else · `independent` = no proposal existed. Accepted rows are confirmed compositions of your
own word-level decisions; they should not be reported as hand-transliterated.

## Local use

```sh
# from the project root
python3 -m http.server 8000
# then open http://127.0.0.1:8000/app/index.html
```

Opening `index.html` directly via `file://` also works for search and editing,
but the "Save to GitHub" button requires the page to be served (the GitHub API
rejects requests from `file://` origins). Edits made offline are kept in
`localStorage` and can be saved later from a served context, or downloaded with
**Export JSON**.

## Published site

The public catalogue is live at **<https://zurstadt.github.io/nwyia-catalogue/>**
(GitHub Pages, served from `main` at `/ (root)`, so both `/site/` and `/data/`
are reachable — the pages fetch `../data/data.json` at runtime). The root
`index.html` redirects to `site/index.html`; `.nojekyll` disables Jekyll.

A push to `main` republishes; the build takes ~30 s. The adjudicator app is
published at the same origin under `/app/`.

## Editing and saving back to the repo

The app stores in-progress edits in `localStorage` (badge on **Save to GitHub**
shows how many are pending). To commit them:

1. **Settings → Personal access token**. Generate a *fine-grained* token at
   <https://github.com/settings/tokens?type=beta>:
   - **Repository access**: only the index repository.
   - **Repository permissions**: **Contents: Read and write** (and nothing else).
   - **Expiration**: as short as is convenient — the token only needs to live
     in your browser's `sessionStorage` for the editing session.
2. Paste the token, owner, repo, and branch into **Settings** in the app.
3. Click **Save to GitHub**. The app PUTs the merged `data.json` via the
   Contents API; the page reloads from the updated file.

The token is kept in `sessionStorage` only — closing the tab clears it.

## Re-running the data pipeline

If the source PDF is updated, or you want to regenerate `data.json` from
scratch:

```sh
pip install pdfplumber jellyfish
python3 scripts/extract.py      # writes source/raw_rows.json
python3 scripts/cluster.py      # writes data/data.json
```

`cluster.py` carries a curated DIN 31635 transliteration table for the most
common figures in the corpus; other clusters get a mechanical placeholder
which is meant to be corrected interactively in the app.

## Finding similar-name clusters to merge (OpenRefine-style)

`scripts/name_cluster.py` groups author clusters whose names are similar enough
that they may be the same person (or a bare/unidentified cluster matching an
identified one). It mirrors OpenRefine's clustering with several independent
methods — token-sort *fingerprint* (transliteration and Arabic, the latter with
the project's orthographic folding), *n-gram* fingerprint, *Levenshtein*
near-neighbour, a *shared distinctive nisbah* test (excluding common given-name
and laqab elements), and a *bare-cluster lead* pass that links unidentified
clusters to look-alikes by nisbah-stem prefix. Consonant digraphs are preserved
(ḫ→kh stays distinct from ḥ→h), so خ and ح don't wrongly merge.

```sh
python3 scripts/name_cluster.py        # writes review/name_clusters.json
python3 -m http.server 8443            # from the project root
# then open http://localhost:8443/review/name_clusters.html
```

Adjudicate one group per screen (j/k to move, 1–4 to decide, click a card to set
the *keep* target, tick who merges into it). **Export JSON** saves the decisions;
**Merge transcript** emits ready-to-paste `NAMED_MERGES` mappings for
`scripts/harvest_authority.py`.

## Notes on the data

- Author clustering is **conservative**: it only merges rows whose normalized
  Arabic strings are identical, or where one is a token-subset of the other
  *and* shares a distinctive (non-stopword) token. False merges have to be
  undone manually, so erring toward more clusters is safer. Use the editor's
  **Cluster** dropdown to merge missed variants.
- The `confidence` field on a cluster is the minimum pairwise Jaro-Winkler
  similarity across its members (1.0 for singletons). Low confidence is a hint
  to inspect, not a verdict. The metric is implemented in `normalize.py` in pure
  Python — verify it with `python3 scripts/test_normalize.py`. Note that it only
  runs for clusters the authority file does *not* cover; authority clusters are
  assigned 1.0 outright, so at present it is dormant.
- **The cluster is authoritative for author romanization.** `canonical_translit`
  and `full_name` on the cluster are what the public catalogue displays. The
  row-level `author_translit` / `author_translation` fields remain in the schema
  so existing values round-trip, but they are not offered in the app's
  **Edit columns** sweep and should not be filled in bulk.
- `catalog_note` holds the cataloguer's description of the item, including its
  physical form where that was recorded (*texte imprimé*, *texte dactylographié*,
  *lithographie*). It is distinct from `discrepancy_note`, which records a
  conflict between Nwyia's entry and the holding library's catalogue.
- `pub_status` defaults to `unknown`. The four values are `unknown`,
  `published`, `partial` (partial edition), `manuscript` (manuscript only).
- Discrepancy notes are free-text; the intent is to record alternative or
  corrected attributions inline without overwriting Nwyia's original reading.

## Known extraction artifacts

Word-export PDFs paint Arabic glyphs in visual (LTR) order with presentation
forms; the extractor reverses Arabic runs and NFKC-normalizes them. A few
edge cases survive into the data:

- Numbers next to Arabic occasionally lose their separating space
  (e.g. *50 خصلة الامام* → `خصلة الامام50`).
- Shadda placement may drift by one base letter in cluster boundaries
  (e.g. *الحلّاج* may appear with shadda on the alif rather than the lām).

Both are searchable (the search index strips diacritics) and easily corrected
in the **Title** / **Author** fields of the editor.
