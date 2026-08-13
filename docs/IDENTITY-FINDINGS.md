# Identity findings — author clusters and title attributions

Produced by `python3 scripts/audit_identity.py` (read-only) on 2026-08-13, then
assessed by hand.

**Findings 1 and 2 were ruled on and APPLIED on 2026-08-13** — see the notes on each.
The rest remain proposals awaiting a ruling.

The audit applies refutations that a similarity score cannot express — a
similarity function only ever ACCUMULATES, so two people who share enough
onomastic surface merge however violently they disagree on a discriminating
element. Rules follow the `network-disambiguation` skill: a confidently-parsed
**ism mismatch refuses** rather than penalises, a **kunyah names the son** rather
than the man, a **nisbah is confirmatory and never decisive**, and an **attested
date impossibility is a veto**.

---

## 1. c060 conflates two men three and a half centuries apart — APPLIED

The cluster claims **Muḥammad b. Murtaḍā, Muḥsin Fayḍ al-Kāshānī, d. 1090/1679**
(the Safavid polymath). It holds two rows:

| row | author as catalogued | title |
|---|---|---|
| r0083 | عبد الرزاق بن ابي الغنائم القاشاني | اصطلاحات الصوفية |
| r0058 | القلشاني | اصطلاح في علم التصوف |

r0083 is **ʿAbd al-Razzāq b. Abī al-Ghanāʾim al-Qāšānī** (al-Kāšānī), d. c. 736/1335,
the Ibn ʿArabī-school commentator. Four independent signals:

- **Ism veto** — ʿAbd al-Razzāq against the cluster's Muḥammad/Muḥsin. Two men.
- **Date impossibility** — 736 against 1090: **354 years**. No lifetime spans both.
- **The work** — *Iṣṭilāḥāt al-ṣūfiyya* is al-Qāšānī's signature lexicon, not Fayḍ's.
- **The only link is the nisbah** — al-Qāšānī / al-Kāšānī, which the skill is
  explicit is confirmatory and never decisive. This is the textbook homonym merge.

*Context:* the project log records a dedup merge `c066 → c060`. That merge is the
likely origin of this conflation.

**Applied.** r0083 now sits in a new cluster **c124 · ʿAbd al-Razzāq al-Qāšānī**
(Kamāl al-Dīn ʿAbd al-Razzāq b. Abī al-Ġanāʾim al-Qāšānī, d. c. 736/1335), with the
reasoning recorded in the row's `discrepancy_note`.

**Still open, and it matters:** c060 now holds **one row, r0058 (`القلشاني`)** — and
its name, its dates (d. 1090/1679) and its **seven authority links** (TDVİA, Wikidata,
VIAF, GND, Wikipedia, OpenAlex, Google Scholar) all describe Fayḍ al-Kāšānī, whom no
remaining row clearly attests. Rule on whether r0058 is a spelling of القاشاني or the
Maghribi al-Qalshānī; if it is neither man, that metadata should be retired rather
than left attached.

## 2. r0172 *Maqāmāt al-qulūb* is al-Nūrī, not al-Nawawī — APPLIED

r0172 (Süleymaniye, Bağdatlı Vehbi 2150) is catalogued as
`ابو زكريا يحيى بن شرف الدين النووي` — **al-Nawawī**, d. 676/1277, the Shāfiʿī
jurist — and is the *only* row in cluster c088. Four converging signals:

- ***Maqāmāt al-qulūb* is Abū al-Ḥasan al-Nūrī's work** (d. 295/907), not a work
  of the jurist al-Nawawī, whose corpus is ḥadīth and fiqh.
- **النوري vs النووي** differ by one letter (ر / و) — the classic confusion.
- **Same Fonds cote (078) as r0201**, which carries *the same title* under
  al-Nūrī. The people who catalogued Nwyia's office bundled them together.
- The corpus already holds two other *Maqāmāt al-qulūb* rows (r0201, r0212), both
  under al-Nūrī.

**Applied.** r0172 now sits in **c036 (Abū al-Ḥasan Aḥmad b. Muḥammad al-Nūrī,
d. 295/907)**, which holds three rows; **c088 held no rows and was dropped** on the
re-cluster, taking its six authority links with it. The author cell was corrected to
`ابو الحسن النوري` as well — leaving Nwyia's `النووي` in place kept the audit
re-raising a decided case every run — and his wording is preserved in the row's
`discrepancy_note`.

*Worth verifying at your end:* Nwyia himself published al-Nūrī's mystical texts,
which would explain three copies of this treatise sitting in his collection. I have
not verified the exact edition reference — do not print it on my say-so.

## 3. r0035 is not Ibn ʿAbbād al-Rundī — HIGH confidence it is misfiled

r0035, *Nuzhat al-nāẓir al-mutaʾammil wa-qayd al-sātir al-mustaʿjil*, is
catalogued `سيدي الصبرجي` — **Sīdī al-Ṣabrajī**, which shares no token with
*Ibn ʿAbbād al-Rundī* (full name Abū ʿAbd Allāh Muḥammad b. Ibrāhīm Ibn ʿAbbād
al-Nafzī). Its five cluster-mates are all plainly `ابن عبّاد`.

**Proposed:** split r0035 out. Who Sīdī al-Ṣabrajī is, I cannot establish — flagged
rather than guessed. The project log already lists this row as held/ambiguous.

## 4. r0255 is an anthology, not a work by one author — MEDIUM confidence

r0255, *Miʿyār al-taṣawwuf wa-māhiyyatihi min kalām al-shuyūkh* ("...from the words
of the shaykhs"), carries the author cell
`ابو سعيد الخرّاز، الوسي، التستري` — three comma-separated names: al-Kharrāz,
al-Wāsiṭī(?), al-Tustarī. The title says outright that it excerpts several masters,
so the cell lists the shaykhs anthologised, not an author. Filing it under
al-Tustarī (c025) picks one arbitrarily.

**Proposed:** treat as a multi-author anthology — unassign from c025 and record the
excerpted names in `catalog_note`. The same pattern was already resolved once in
this corpus (the garbled `الخواص، التستري` cell, now r0167 under al-Sulamī), so it
is a recurring shape of the source rather than a one-off.

## 5. Two rows may be a different al-Baṣrī — MEDIUM confidence, needs your eye

Cluster c009 (**al-Ḥasan al-Baṣrī**, d. 110/728) holds two rows catalogued
`ابو الحسن البصري`:

| row | title | cote |
|---|---|---|
| r0170 | رسالة في الاحاديث المتفرقة | 086 |
| r0204 | شرح اوراد حفظية | 086 |

- **al-Ḥasan al-Baṣrī's kunyah is Abū Saʿīd, not Abū al-Ḥasan.** A kunyah names
  the son: *Abū al-Ḥasan* is the father of a Ḥasan, not Ḥasan himself.
- The five genuine al-Ḥasan al-Baṣrī rows sit at cotes **075 and 091**; these two
  sit together at **086** — a different bundle.
- Neither title is characteristic of al-Ḥasan al-Baṣrī: a *sharḥ* on *awrād* is a
  much later genre.

**Proposed:** split r0170 + r0204 into their own cluster pending identification.
Several well-known figures are "Abū al-Ḥasan … al-Baṣrī"; I am not going to pick
one for you.

## 6. The Rabat *Iṣṭilāḥāt* codex — needs your eye

r0317 and r0318 are both Rabat, General Library **D984** — one manuscript.

- r0318 `النيسابوري` — *Iṣṭilāḥāt al-ṣūfiyya*, filed under n000 al-Naysābūrī, a
  cluster the project log already flags as "which one?"
- r0317 `ابن عبّاد` — title *اصطلاحات الصوفية، تعريف بابن عباد*, i.e. "…, **a notice
  about Ibn ʿAbbād**". That reads as a description of the codex's contents, not an
  authorship claim, so filing it under Ibn ʿAbbād as author may be an artefact.

Given finding 1, the *Iṣṭilāḥāt al-ṣūfiyya* in this codex is most likely
al-Qāšānī's as well — which would make three of the corpus's four copies his.

## 7. Not errors — recorded so they are not re-raised

- **رسائل عبد الملك بن مروان وحسن البصري** (r0132 / r0133) is a *correspondence*,
  correctly filed under both parties. The audit flags it structurally; it is
  right as it stands. (Compare the Ṭūsī–Qūnawī correspondence, already dissolved
  the same way.)
- **تفسير القران** under both Jaʿfar al-Ṣādiq (r0057) and Ibn Barrajān (r0140) —
  a generic title, and both men wrote tafsīr. No conflict.

## 8. One title, two spellings — affects the sweep in progress

| row | as catalogued | should be |
|---|---|---|
| r0110 | ادآب العبادات | آداب العبادات |
| r0225 | آداب العبادات | — |

Both are Shaqīq al-Balkhī's *Ādāb al-ʿibādāt* (c017). r0110's spelling transposes
the alif-madda. **Both must receive the same transliteration** — *Ādāb
al-ʿibādāt* — or the index will carry one work under two romanizations. Worth
fixing the title itself on r0110 while you are in the sweep.

---

## Method note: a bundle signal needs a second dimension

The Fonds cote is independent evidence — the colleagues who catalogued Nwyia's
office bundled items with the material in front of them, and the clusterer never
saw those numbers. But cote co-membership **alone** is nearly worthless: a cote is
a box of unrelated works, so cote-mates in different clusters is the normal case.
Unconditioned, that check produced **73 hits, nearly all benign**.

Conditioned on a second dimension — *the same work, in the same bundle, attributed
two ways* — it produced **2 hits, one of them finding 2 above**. The signal is real;
it is the conjunction that carries it.

---

# Titles expanded to the work they name — applied 2026-08-13

Nwyia's index often records a bare genre word or a cataloguer's label where the author
already settles the work. **33 titles were expanded in place**, each keeping his own
wording in `discrepancy_note` and the basis in `catalog_note`.

The largest class: **14 rows reading `الحكم` / `حكم` under Ibn ʿAṭāʾ Allāh** are all
*al-Ḥikam al-ʿAṭāʾiyya*, the work Nwyia edited in 1972. Then al-Ḥallāǧ's *Ṭawāsīn* (2),
al-Qušayrī's *Laṭāʾif al-išārāt* (2), al-Sulamī's *Ḥaqāʾiq al-tafsīr* (2), al-Māturīdī's
*Kitāb al-Tawḥīd* and *Taʾwīlāt al-Qurʾān*, three monographs of Ibn Abī al-Dunyā,
al-Tustarī's *Tafsīr*, al-Niffarī's *Mawāqif*, and Abū Madyan's *Ḥikam* (3).

## What the BnF settled

- **r0299 «Opera»** — Arabe 5018 is *«12 traités de théologie et de philosophie par
  Abou Abd Allah Mohammad ibn Ali al-Tirmidi»*: a majmūʿ of twelve treatises, 212 ff.,
  14th-c. Egyptian naskh, entered 1890. The al-Tirmiḏī attribution is **confirmed**.
  Two of the twelve are edited (*al-Ḥaǧǧ wa-asrāruhu*, Cairo 1969; *al-Iḥtiyāṭāt*,
  Beirut 2011), so the row is now `pub_status: partial`.
- **r0295 «Traité médicale»** — Arabe 3038 is a majmūʿ of three medical texts; Ibn
  Sīnā's is the third, *al-Manẓūma fī al-ṭibb* (f. 62). The other two are *Zād
  al-musāfir* and a treatise on the pulse by Muḥammad b. Aḥmad b. al-ʿĀṣ.
- **r0306 «تفسير»** — Arabe 6962 is *Kitāb al-iṣṭilāḥ ʿalā baṭn al-Qurʾān* (GAL Suppl.
  II, 281; Ahlwardt I, 874–875), copied 895/1490. It expounds the inner senses of the
  Qurʾān rather than being a running commentary, so "tafsīr" was a loose descriptor.

## Deliberately NOT expanded

- **r0294 «جفر» under Ibn al-ʿArabī** — BnF Arabe 2669 is a majmūʿ of jafr texts dated
  1026/1617 (predictions ascribed to ʿAlī; an extract from the *Ǧafr al-kabīr* of
  Muḥammad b. Sālim al-Ḫallāl). **The notice does not mention Ibn al-ʿArabī at all.**
  Jafr literature is routinely pseudepigraphic; the attribution needs a ruling, not an
  expansion.
- **r0036 «مجموع» under al-Fārābī** — the shelfmark `Arabe d 84` is already flagged as
  mis-transcribed, and no such Fārābī collection is there.
- **r0183 «تفسير» under Ibn Barraǧān** — he wrote two Qurʾān commentaries; which one
  Carullah 534 holds needs the catalogue, not a guess.
- **`فريضة` under al-Ḥasan al-Baṣrī** (r0199, r0247) — a *farīḍa* text is not
  characteristic of him, and this overlaps finding 5 above.

## Residue — needs your portal access

Behind the login-gated Türkiye Yazma Eserler portal, or otherwise unresolvable here:

| row | shelfmark | what to look for |
|---|---|---|
| r0143 | Köprülü 1602 | no title and no author in the index |
| r0144 | Köprülü 1620 | untitled; index gives Ibn al-Fāriḍ |
| r0168 | Süleymaniye, Ayasofya 4128 (ff. 151a–170) | untitled continuation item |
| r0186 | Süleymaniye, Fatih 2553 (ff. 58a–68a) | untitled; index gives al-Isfarāyīnī |
| r0107 | Mingana 635 | untitled; index gives Šaqīq al-Balḫī |
| r0078 | Berlin, 3319 mo 225 | untitled; Qalamos may settle it |
| r0259 | BL 3336 (2 vols.) | untitled; index gives Gabriel Qaṭraya |
| r0005, r0032, r0033 | — | *Documents divers*, *Fragments (sans titre)* — loose papers |
