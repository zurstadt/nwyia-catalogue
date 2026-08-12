# UX decisions — the adjudicator app

A do-not-lose contract. Each row is a deliberate interaction decision, where it lives (as a **stable
anchor** — a selector, a function name, or a quoted comment; never a line number), why it is that way,
and what guards it.

**Maintenance rule.** Touching an area re-verifies its rows. A row is removed only deliberately, and
named in the commit message. New deliberate behaviour gets a row in the same commit.

The app has no test suite, so most rows read **UNGUARDED**. That is an honest gap, not a formality —
the priority list at the end says which to close first.

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
| ASCII shorthand applies to `*_translit` fields only | `isTranslitField()` | An English translation must never be rewritten under the typist — `'` and `.` are ordinary punctuation there. | **UNGUARDED** |
| Shorthand expands around the caret, both sides separately | `#cols-edit` input handler | So the caret lands after the character just produced, however much the text before it shrank. | **UNGUARDED** |
| A title is pre-filled only when **every** word is known | `translitSuggestion()` | A half-known suggestion is a sentence with holes, and accepting it by reflex would commit them silently. | **UNGUARDED** |
| Lexicon pairs are **skipped, never guessed**, when Arabic and Latin token counts disagree | `buildTranslitLexicon()` | One wrong pair would propagate into every later suggestion. | **UNGUARDED** |
| A suggestion is committed only by an explicit `Enter` | `#cols-edit` keydown handler | Displaying is not accepting. Stepping past with `Shift+Enter` or changing column leaves the row blank rather than banking something nobody read. | **UNGUARDED** |
| The tint is the entire prefill signal | `#cols-edit.prefilled` | A sentence explaining it would be drawn on every prefilled row. | **UNGUARDED** |

### Known limitation — suggestion provenance

A suggestion accepted with `Enter` lands in `data/data.json` **byte-identical** to a hand-typed value,
and `harvest_authority.py` has no field to carry the difference. So the store cannot currently
distinguish a confirmed machine suggestion from an independent human answer.

Do **not** fix this with a flag set in an event handler — that flag is wrong the moment a value
arrives by any other path (restore, preseed, batch accept). Provenance is a **comparison**: at export
time, a committed value equal to what the lexicon would have suggested for that row *is* an accepted
suggestion. If this becomes load-bearing (e.g. for measuring agreement), emit it as a side-car list
rather than a new schema field.

---

## Unguarded-rows priority list

The headless checks already written against the real app are the first candidates to promote into a
test file:

1. **Suggestion is not banked without `Enter`** — the highest-consequence row here; a regression
   silently fabricates scholarly data.
2. **Lexicon skips mismatched token counts** — a regression corrupts every later suggestion.
3. **Shorthand does not touch `title_translation`** — a regression rewrites English prose.
4. `Alt+↑` copies the previous row (the only route to the feature in-field).
5. Source renders above the input and both fit the viewport unscrolled.
6. `kbd-bar` is hidden in columns and populated elsewhere.

## Kept by ruling

- **Copy-previous advances the queue** rather than showing the copied value for review. This is
  pre-existing behaviour (`colsCopyPrevious()` → `renderColumnsView()` → the filled row leaves the
  blank filter), retained deliberately so the key behaves exactly like `Enter`. Revisit only if the
  copied value needs editing more often than not.
