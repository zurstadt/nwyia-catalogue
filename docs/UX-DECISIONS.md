# UX decisions — the adjudicator app

A do-not-lose contract. Each row is a deliberate interaction decision, where it lives (as a **stable
anchor** — a selector, a function name, or a quoted comment; never a line number), why it is that way,
and what guards it.

**Maintenance rule.** Touching an area re-verifies its rows. A row is removed only deliberately, and
named in the commit message. New deliberate behaviour gets a row in the same commit.

Guards: `node scripts/test_translit_logic.js` covers the transliteration logic (it lifts the pure
region out of `app/index.html` and runs against stubs — it never opens a browser or edits the app).
`python3 scripts/test_normalize.py` covers the pipeline's string metrics. Rows still reading
**UNGUARDED** are an honest gap, not a formality; the priority list at the end says which to close
next.

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

## Kept by ruling

- **Copy-previous advances the queue** rather than showing the copied value for review. This is
  pre-existing behaviour (`colsCopyPrevious()` → `renderColumnsView()` → the filled row leaves the
  blank filter), retained deliberately so the key behaves exactly like `Enter`. Revisit only if the
  copied value needs editing more often than not.
