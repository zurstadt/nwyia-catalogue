# UX decisions — the adjudicator app

A do-not-lose contract. Each row is a deliberate interaction decision, where it lives (as a **stable
anchor** — a selector, a function name, or a quoted comment; never a line number), why it is that way,
and what guards it.

**Maintenance rule.** Touching an area re-verifies its rows. A row is removed only deliberately, and
named in the commit message. New deliberate behaviour gets a row in the same commit.

Guards: `node scripts/test_translit_logic.js` covers the transliteration logic (it lifts the pure
region out of `app/index.html` and runs against stubs — it never opens a browser or edits the app).
`python3 scripts/test_normalize.py` covers the pipeline's string metrics and the one Arabic
word/mark definition. `python3 scripts/test_apply_translit_adjudication.py` covers the adjudication
ingest against in-memory fixtures, and `python3 scripts/test_cluster.py` the variant merge.
`node scripts/check_translit_app.js` drives the REAL baked adjudication app — including a hand-built
fixture payload for the strata that empty out, so an assertion over them cannot pass by skipping.
Rows still reading **UNGUARDED** are an honest gap, not a formality; the priority list at the end
says which to close next.

---

## The Edit-columns sweep

A sweep is one question asked hundreds of times, so anything on that screen is paid for once per row.
The screen therefore holds exactly two things: the **source** being read from, and the **field** being
typed into.

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| Source rendered large, **above** the input | `#cols-source`, `sweepSourceFor()` | It is the raw artifact the task reads from. It used to sit *below* the input inside the context card, under up to eleven other fields. | **UNGUARDED** |
| Source falls back to LTR when it is not Arabic | `.sweep-source.ltr`, `hasArabic()` | Some titles in the fonds are French ("Documents divers"); forced RTL renders them as gibberish. | **UNGUARDED** |
| The field being edited is named **once**, by the Column select | `#cols-progress`, `#cols-field` | It was previously stated four times — progress line, card `<h2>`, input `<label>`, prompt banner — on every row. | **UNGUARDED** |
| No prompt banner | *(removed `#cols-prompt`)* | A *uniform* sweep has no per-entry question. A banner repeating one sentence 344 times is noise, not guidance. Per-entry prompts remain right for heterogeneous adjudication views. | **UNGUARDED** |
| No on-screen diacritic palette | *(removed `#translit-palette`)* | The user has their own input method and asked for it gone. | **UNGUARDED** |
| No per-word lexicon chips | *(removed `#translit-tokens`)* | Drawn on every entry to say what the field tint already says. | **UNGUARDED** |
| Progress reports **column completion**, not cursor position | `#cols-progress` | Percent-of-cursor reads "0%" on the first of 344 rows and means nothing; "3 of 347 filled (1%)" is the number the typist wants. | **UNGUARDED** |
| `kbd-bar` hidden in this view only | `renderKbdHints()` else-branch | It was the third place the same two keys were printed. Other views still use it. | **UNGUARDED** |
| Context, key reference, shorthand legend and go-to-row behind one `ctx ▾` | `#cols-ctx`, `#cols-ctx-toggle`, `SS_KEY_CTX` | Removed from the sweep, **not** from the app. Open/closed persists for the session. | **UNGUARDED** |
| Toggling `ctx` returns focus to the field | `#cols-ctx-toggle` click handler | The sweep must never lose the caret to chrome. | **UNGUARDED** |

## Keyboard

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| `Alt+↑` copies the previous row's value | `#cols-edit` keydown handler; `colsCopyPrevious()` | **`onKey()` early-returns on `inField`**, so during a sweep the global bindings (`j`/`k`, `z`) are inert. A button was the only reachable form — and buttons are what this screen is avoiding. Any future "just add a shortcut" must account for this. | **UNGUARDED** |
| No Prev / Next / Go buttons | *(removed `#cols-prev`, `#cols-next`)* | `Enter` and `Shift+Enter` already do it. Go-to-row survives inside `ctx`. | **UNGUARDED** |

## Transliteration assistance

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| ASCII shorthand applies to `*_translit` fields only | `isTranslitField()` | An English translation must never be rewritten under the typist — `'` and `.` are ordinary punctuation there. | `scripts/test_translit_logic.js` |
| Shorthand expands around the caret, both sides separately | `#cols-edit` input handler | So the caret lands after the character just produced, however much the text before it shrank. | **UNGUARDED** |
| A title is pre-filled only when **every** word is known | `translitSuggestion()` | A half-known suggestion is a sentence with holes, and accepting it by reflex would commit them silently. | `scripts/test_translit_logic.js` |
| Lexicon pairs are **skipped, never guessed**, when Arabic and Latin token counts disagree | `buildTranslitLexicon()` | One wrong pair would propagate into every later suggestion. | `scripts/test_translit_logic.js` |
| A suggestion is committed only by an explicit `Enter` | `#cols-edit` keydown handler | Displaying is not accepting. Stepping past with `Shift+Enter` or changing column leaves the row blank rather than banking something nobody read. | **UNGUARDED** |
| The tint is the entire prefill signal | `#cols-edit.prefilled` | A sentence explaining it would be drawn on every prefilled row. | **UNGUARDED** |

### Suggestion provenance — closed

Accepting a suggestion is a real decision, but it is not the same act as reading the Arabic and
writing the line out, and in `data/data.json` the two are byte-identical. That distinction is now
recoverable.

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| The app stores **what the machine proposed**, not what it thinks the human did | `shownSuggestion`, `recordSuggestionFor()` | An "accepted" flag set in a handler is wrong the moment a value arrives by another route — restore, preseed, batch accept. The record is an observation; the verdict is derived from it. | `scripts/test_translit_logic.js` |
| The proposal is captured **at decision time**, not recomputed later | `recordSuggestionFor()` called from the `Enter` branch | The lexicon grows as the sweep proceeds. Recomputing at export would answer "what would the finished lexicon say now?" and silently reclassify rows decided when it knew less. | **UNGUARDED** |
| A proposal is recorded only on an actual commit | `Enter` branch, `#cols-edit` keydown | A row stepped past has no decision to attribute. | `scripts/test_translit_logic.js` |
| The verdict is a **comparison**, computed outside the app | `classify()` in `scripts/report_provenance.py` | accepted = value equals proposal · overridden = a proposal was shown and something else was written · independent = no proposal existed. | **UNGUARDED** |
| Proposals live in `authority.json`, not in the rows | `harvest_authority.py` `machine_suggestions` | It is provenance about the curation, not catalogue content; the published `data.json` should not carry it. | **UNGUARDED** |
| Proposals **accumulate** across harvests | `harvest_authority.py`, `prior` merge | `cluster.py` does not re-emit the block, so a later export carrying none would otherwise wipe the record. | **UNGUARDED** |
| A proposal whose field has been emptied is pruned | `harvest_authority.py`, `live` filter | With nothing to compare against, it describes a decision that no longer exists. | **UNGUARDED** |

Report it with `python3 scripts/report_provenance.py [--field …] [--list]`. Verified end to end:
accept / override / step-past classify correctly; a second harvest with no block preserves the
earlier records; emptying a field prunes its proposal.

**Do not** report accepted rows as hand-transliterated. They are confirmed compositions of your own
word-level decisions — a different and weaker claim, and the report says so in its own output.

**A later bulk normalization RECLASSIFIES provenance, and that is correct rather than a bug.** The
verdict compares the proposal against what the field holds *now*. Lowercasing five titles on
2026-08-13 moved two rows from `accepted` to `overridden`, because their committed value no longer
equals what was proposed. The comparison is still telling the truth — the stored value does differ
from the machine's output — but the difference is now an editorial pass, not the annotator's
judgement at the time. When reporting an acceptance rate as evidence about the *suggester*, say
which normalizations have run since. Do not "fix" this by freezing the verdict at decision time:
that would reintroduce the event-flag failure the whole design avoids.

### House style: title transliterations are lowercase

Ruled 2026-08-13. Arabic-source titles are romanized entirely in lowercase (`kitāb al-tawahhum`),
and `scripts/audit_identity.py` reports any drift under "Transliteration case drift". A
**Latin-script** source is exempt — r0006 is Nwyia's own French volume, where `Ibn ʿAṭāʾ Allāh` is a
proper noun rather than a transliteration. Author names on clusters keep their capitals; this rule
governs titles only.

---

## Unguarded-rows priority list

Closed so far by `node scripts/test_translit_logic.js` — shorthand field-scoping, the every-word
pre-fill rule, the mismatched-token-count skip, and both provenance-recording rules. That suite was
mutation-tested: deliberately relaxing the every-word rule fails two of its checks, so it has teeth
rather than merely being green.

Next, hardest first:

1. **A suggestion is not banked without `Enter`.** Still the highest-consequence row. The recording
   half is now guarded, but the commit path itself lives in a DOM handler, so covering it needs a
   headless driver rather than this harness. Detectable after the fact via `report_provenance.py`.
2. **Shorthand expands around the caret.** Pure logic, but the caret arithmetic lives in the input
   listener; lift it into a named function first, then it is trivially testable.
3. **`Alt+↑` copies the previous row** — the only route to the feature in-field.
4. **The harvest side**: proposals accumulate across harvests, and a proposal whose field was emptied
   is pruned. Both are plain Python and belong in a `test_harvest.py` alongside `test_normalize.py`;
   both were verified by hand on a scratch copy but nothing re-checks them.
5. Source renders above the input, and `kbd-bar` is hidden only in the columns view.

## An answer records the question it answered

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| Every item carries a content fingerprint, baked | `fingerprint()` in `build_translit_adjudication.py`; `it.fp` | Item ids are stable literals — which is what lets an in-progress batch survive a rebuild of the residual worklist, and also what let an answer survive a rebuild of a DIFFERENT question. Edit a hand-written ORTHO dict and the next bake emits a new proposal under the same id. | `scripts/check_translit_app.js` |
| The fingerprint covers what the ANSWER depends on, and nothing else | `fingerprint()`, per-stratum signature | Prose, row context and the scope's id lists are excluded: a card must not be invalidated because one unrelated row in its radius was fixed. The scope BOOLEANS are in, because `axes()` keys on them — a card that gains or loses its transliteration axis is a different question. | `scripts/check_translit_app.js` |
| Per-item, never a whole-payload bake id | — | The worklist is residual by design, so every bake differs; a payload-level check would discard the annotator's whole in-progress batch on every rebuild. | `scripts/check_translit_app.js` ("an answer to an UNCHANGED card survives") |
| A stale answer is shown, not deleted, and exports as open | `stale()`, `complete()`, `ready()`, the re-check banner, `rec.stale` | The answer is the annotator's work. It stops counting as a decision until re-confirmed against the card as it stands; it does not stop existing. The ingest reports the count so a shrunken "resolved" is explained rather than merely noticed. | `scripts/check_translit_app.js` |
| A schema change migrates state, never discards it | `migrate()`, `STATE_V` | v1 stored a hand-written attribution title in the enum slot and carried no fingerprints. Both are recovered on load: the title becomes its own answer, and a fingerprint-less answer is stamped with the current card's — the honest reading, since there is no record to say it was given against anything else. | `scripts/check_translit_app.js` |
| The annotator name is written, not only read | `annotator()` | It was read into every export and into the header badge and set nowhere, so every export so far carries `annotator: null` — recorded as such in the applied log. | **UNGUARDED** |

## Every affordance the app renders is consumable

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| A typed title lives in its own state slot, not the enum's | `#custom-title` handler, `s.disposition = "custom"` + `s.title` | One slot carried the sentinels `"keep"`/`"strip"` AND arbitrary user text, so no consumer could tell an answer from a value. | `scripts/check_translit_app.js` |
| A hand-written title asks for its transliteration — but only where the row has one | `axes()`, attribution branch; `#custom-title-translit` | A typed title cannot be trimmed automatically, so without it the row's two sides disagree word-for-word and the composer reads them apart. Where the row has no transliteration there is nothing to desynchronize, and demanding one would leave Confirm dead. | `scripts/check_translit_app.js`, `scripts/test_apply_translit_adjudication.py` |
| The ingest REFUSES an action it does not implement | `apply_translit_adjudication.py`, `if action not in (…)` | The branch tested only for `keep` and let everything else fall into tail-removal, so an unimplemented action was not rejected but silently mis-executed — and the quarantine reason named a cause that had not occurred. A missing `else` is how an affordance becomes a lie. | `scripts/test_apply_translit_adjudication.py` |
| `set_title` ASSIGNS, where every other path patches | `apply_translit_adjudication.py`, the `set_title` branch | The lost-update rule (never assign a value the app computed from a pre-run snapshot) does not apply to a value the ANNOTATOR wrote. What does apply is the from-value guard, which is what makes the assignment safe — so it is not optional. | `scripts/test_apply_translit_adjudication.py` |

## What a ruling's breadth is

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| Seeding a reading and settling a key are separate claims with separate gates | `apply_translit_adjudication.py` `record()`; `build_lexicon(…, decontest)` | One field used to do both — the ingest returned `contested - set(overrides)` — so every recorded transliteration ruled on the key's contest whether or not the annotator had ruled on anything, which is the opposite of what the app's own panel promises. | `scripts/test_apply_translit_adjudication.py` |
| The breadth is a recorded field, never inferred | `rec.row_scoped` from the builder's `hand and only_rows` | `shadda_items` and `hamza_items` set `only_rows` mechanically ("rows where the fault survives"), so the field is true nearly everywhere and useless as a gate. Only a hand-authored `only_rows` means "a fault HERE, correct elsewhere". | `scripts/test_apply_translit_adjudication.py` |
| How the transliteration was arrived at travels with it | `rec.translit_source`, computed by COMPARISON in `decisions()` | The box is prefilled, so an untouched one is still a real answer and Confirm stays alive — but accepting a default is not the act of ruling on a contest, and only the second may close one. Derived from the item, not from which handler fired. | `scripts/test_apply_translit_adjudication.py` |
| An affirmative ruling de-contests BOTH keys | `decontest.update({normalize_ar(word), normalize_ar(new_form)})` | The rows still carry the old key. De-contesting only the new one left the old contested forever, exactly where a spelling changed — the gate under-fired as well as over-fired. | `scripts/test_apply_translit_adjudication.py` |
| The panel states the breadth the code enforces | «How far a transliteration reaches» in the Orthography panel | The panel said a šaddah "changes no key and unblocks no title" while its transliteration did both. Prose and gate are now one statement. | **UNGUARDED** (prose) |

## What survives a re-cluster

`cluster.py` rebuilds `data/data.json` from the raw extraction plus `authority.json`, so any field it
recomputes is reverted unless harvest pins it. This is where an edit silently disappears.

| Decision | Anchor | Why | Guard |
|---|---|---|---|
| Cluster `variants` are pinned through harvest and merged back on the normalized key | `harvest_authority.py` cluster meta block; `cluster.merge_variants()` | `variants` is a projection of the row `author` strings, rebuilt every run — so a ruling applied to a cluster name reverted on the very next step the apply script tells you to run. Keyed on `normalize_ar` so the adjudicated spelling REPLACES the raw one rather than sitting beside it. | `scripts/test_cluster.py` |
| A pinned variant whose key no longer occurs is dropped, never re-injected | `cluster.merge_variants()`, the `if k in by_key` guard | Without it a pin is unremovable: a name the corpus stopped writing would resurrect on every re-cluster. The cost that remains: a *wrong* pin is sticky, and undoing it means hand-editing `data/authority.json`. | `scripts/test_cluster.py` |
| The ingest de-duplicates the variants it rewrites | `apply_translit_adjudication.py`, `vs = sorted(set(vs))` | The rewrite was positional, so folding two spellings of one name onto the same target left the identical string twice. | `scripts/test_apply_translit_adjudication.py` |
| The conservation audit inspects author fields, not titles alone | `apply_translit_adjudication.py`, `fault_stands()` | A reverted author edit went unseen where a reverted title edit could not — and an author field is now the only surface some ortho cards touch. | `scripts/test_apply_translit_adjudication.py` |

## Kept by ruling

- **Copy-previous advances the queue** rather than showing the copied value for review. This is
  pre-existing behaviour (`colsCopyPrevious()` → `renderColumnsView()` → the filled row leaves the
  blank filter), retained deliberately so the key behaves exactly like `Enter`. Revisit only if the
  copied value needs editing more often than not.
