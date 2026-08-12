# Identity findings — author clusters and title attributions

Produced by `python3 scripts/audit_identity.py` (read-only) on 2026-08-13, then
assessed by hand. Nothing here has been applied: every item is a proposal awaiting
your ruling.

The audit applies refutations that a similarity score cannot express — a
similarity function only ever ACCUMULATES, so two people who share enough
onomastic surface merge however violently they disagree on a discriminating
element. Rules follow the `network-disambiguation` skill: a confidently-parsed
**ism mismatch refuses** rather than penalises, a **kunyah names the son** rather
than the man, a **nisbah is confirmatory and never decisive**, and an **attested
date impossibility is a veto**.

---

## 1. c060 conflates two men three and a half centuries apart — HIGH confidence

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

**Proposed:** split r0083 into a new cluster for ʿAbd al-Razzāq al-Qāšānī
(d. 736/1335). Note that once it leaves, **no row supports the Fayḍ identity at
all** — r0058 is the only remainder, and *al-Qalshānī* is a Maghribi nisbah
(Qalshāna, Ifrīqiya), not obviously Kāšānī. So the cluster's name and dates are
themselves in question, not just its membership.

**Needs your ruling:** is r0058's القلشاني a spelling of القاشاني (join it to
al-Qāšānī), or the Maghribi al-Qalshānī (its own cluster)? If neither row is
Fayḍ, c060's metadata should be retired rather than inherited.

*Context:* the project log records a dedup merge `c066 → c060`. That merge is the
likely origin of this conflation.

## 2. r0172 *Maqāmāt al-qulūb* is al-Nūrī, not al-Nawawī — HIGH confidence

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

**Proposed:** reattribute r0172 to **c036 (Abū al-Ḥasan Aḥmad b. Muḥammad al-Nūrī,
d. 295/907)**; c088 then holds no rows and is dropped on the next re-cluster.

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
