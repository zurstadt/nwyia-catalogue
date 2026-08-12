/**
 * Self-checks for the transliteration logic inside app/index.html.
 *
 * Run directly, no dependencies:
 *
 *     node scripts/test_translit_logic.js
 *
 * The app is deliberately one self-contained file, so there is nothing to
 * import. This harness READS app/index.html, lifts out the pure-logic region
 * (everything between the "Transliteration aids" banner and colField), and
 * evaluates it against stubs for the four globals it touches — raw, edits,
 * mergedRow, mergedCluster. Nothing here opens a browser or touches the DOM,
 * and the app is never modified.
 *
 * These cover the rows docs/UX-DECISIONS.md lists as highest-consequence: a
 * regression in any of them corrupts scholarly data silently rather than
 * throwing, which is exactly the failure a test has to catch.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const APP = path.join(__dirname, "..", "app", "index.html");
const START = "// ===== Transliteration aids";
const END = "\nfunction colField(";

function liftPureRegion(source) {
  const from = source.indexOf(START);
  const to = source.indexOf(END, from);
  if (from < 0 || to < 0) {
    throw new Error(
      "Could not find the transliteration region in app/index.html.\n" +
      "The anchors moved — update START/END here, and check whether the " +
      "behaviour these tests guard moved with them."
    );
  }
  return source.slice(from, to);
}

// Stubs for the globals the region closes over. Kept minimal on purpose: if the
// region starts needing more of the app, that is a signal the logic is drifting
// out of "pure" and the test harness should be reconsidered, not quietly grown.
let raw = { rows: [], clusters: [] };
let edits = { rows: {}, clusters: {}, suggestions: {} };
const mergedRow = r => ({ ...r, ...(edits.rows[r.id] || {}) });
const mergedCluster = c => ({ ...c, ...(edits.clusters[c.cluster_id] || {}) });

const region = liftPureRegion(fs.readFileSync(APP, "utf8"));
// Evaluate in this scope so the region's declarations become locals here, and
// return the handles the assertions need.
const api = eval(region + `
  ({ expandShorthand, isTranslitField, arabicKey, arabicWords, hasArabic,
     capitalizeFirst, translitSuggestion, buildTranslitLexicon, sweepSourceFor,
     translitSuggestionFor, recordSuggestionFor,
     getLexicon: () => TRANSLIT_LEXICON,
     setShown: v => { shownSuggestion = v; } })
`);

const failures = [];
const eq = (got, want, label) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) failures.push(`${label}\n      got:      ${g}\n      expected: ${w}`);
};
const ok = (cond, label) => { if (!cond) failures.push(label); };

// ---------------------------------------------------------------- shorthand
// UX-DECISIONS: "shorthand applies to *_translit fields only". A regression
// here rewrites English prose in the translation columns.
eq(api.isTranslitField("title_translit"), true, "title_translit is a translit field");
eq(api.isTranslitField("author_translit"), true, "author_translit is a translit field");
eq(api.isTranslitField("title_translation"), false,
   "title_translation must NOT be treated as a translit field");
eq(api.isTranslitField("author_translation"), false,
   "author_translation must NOT be treated as a translit field");
eq(api.isTranslitField("catalog_note"), false, "catalog_note is not a translit field");

eq(api.expandShorthand("kita:b"), "kitāb", "a: expands to a macron");
eq(api.expandShorthand("al-h.ikma"), "al-ḥikma", "h. expands to h-dot");
eq(api.expandShorthand("s.u:fi:"), "ṣūfī", "several rules in one token");
eq(api.expandShorthand("d_ t_ g_ h_ s_ j_"), "ḏ ṯ ġ ḫ š ǧ", "the underscore set expands");
eq(api.expandShorthand("'ilm"), "ʾilm", "apostrophe becomes hamza");
eq(api.expandShorthand("`ilm"), "ʿilm", "backtick becomes ayn");
eq(api.expandShorthand("Kitab al-tawahhum"), "Kitab al-tawahhum",
   "text with no shorthand markers is returned unchanged");

// -------------------------------------------------------------- arabic keys
eq(api.arabicKey("الحقائق"), "الحقائق", "a bare word is its own key");
eq(api.arabicKey("كِتَابْ"), "كتاب", "vowel marks are dropped for lookup");
eq(api.arabicKey("أحمد"), "احمد", "alif hamza folds to bare alif");
eq(api.arabicKey("إبراهيم"), "ابراهيم", "alif hamza-below folds to bare alif");
eq(api.arabicKey("مصطفى"), "مصطفي", "alif maqsura folds to ya");
eq(api.arabicWords("  كتاب   التوهم "), ["كتاب", "التوهم"], "words split on any whitespace");
eq(api.hasArabic("Documents divers"), false, "a French title carries no Arabic");
eq(api.hasArabic("كتاب"), true, "an Arabic title is detected");

// ------------------------------------------------------------ capitalization
eq(api.capitalizeFirst("kitāb al-tawahhum"), "Kitāb al-tawahhum",
   "only the first letter is capitalized — not every word, and not after al-");
eq(api.capitalizeFirst("  risāla"), "  Risāla", "leading space is preserved");
eq(api.capitalizeFirst(""), "", "empty string is safe");

// ------------------------------------------------------------------ lexicon
// UX-DECISIONS: "pairs are skipped, never guessed, when token counts disagree".
// One wrong pair propagates into every later suggestion.
raw = {
  rows: [
    { id: "a", title: "كتاب الحقائق", title_translit: "Kitāb al-ḥaqāʾiq" }, // 2 ↔ 2, learn
    { id: "b", title: "رسالة في التصوف", title_translit: "Risāla" },        // 3 ↔ 1, skip
    { id: "c", title: "ديوان", title_translit: "" },                        // nothing to learn
  ],
  clusters: [{ cluster_id: "c1", canonical_ar: "السلمي", canonical_translit: "al-Sulamī" }],
};
edits = { rows: {}, clusters: {}, suggestions: {} };
api.buildTranslitLexicon();
const lex = api.getLexicon();
eq(lex.get("كتاب"), "Kitāb", "a matched pair is learned");
eq(lex.get("الحقائق"), "al-ḥaqāʾiq", "the second word of a matched pair is learned");
ok(!lex.has("رسالة"), "a MISMATCHED pair must not be learned (3 words ↔ 1)");
ok(!lex.has("التصوف"), "no word of a mismatched pair is learned");
eq(lex.get("السلمي"), "al-Sulamī", "cluster name pairs seed the lexicon");

// -------------------------------------------------------------- suggestions
// UX-DECISIONS: "pre-filled only when EVERY word is known" — a half-known
// suggestion is a sentence with holes that would be accepted by reflex.
eq(api.translitSuggestion("كتاب الحقائق"), "Kitāb al-ḥaqāʾiq",
   "all words known → a suggestion, first letter capitalized");
eq(api.translitSuggestion("كتاب المجهول"), null,
   "ONE unknown word must suppress the whole suggestion");
eq(api.translitSuggestion("المجهول"), null, "no words known → no suggestion");
eq(api.translitSuggestion(""), null, "empty source → no suggestion");
eq(api.translitSuggestion("كتاب"), "Kitāb", "a single known word suggests");

eq(api.translitSuggestionFor({ key: "title_translit" }, { title: "كتاب الحقائق" }),
   "Kitāb al-ḥaqāʾiq", "suggestions are offered on a translit field");
eq(api.translitSuggestionFor({ key: "title_translation" }, { title: "كتاب الحقائق" }),
   null, "suggestions are NEVER offered on a translation field");

// --------------------------------------------------------------- provenance
// UX-DECISIONS: the record is what the MACHINE proposed, and it is written only
// for the row it was actually shown on.
edits = { rows: {}, clusters: {}, suggestions: {} };
api.setShown({ rowId: "a", field: "title_translit", value: "Kitāb al-ḥaqāʾiq" });
api.recordSuggestionFor("a", "title_translit");
eq(edits.suggestions.a, { title_translit: "Kitāb al-ḥaqāʾiq" },
   "the proposal shown for this row+field is recorded");

edits = { rows: {}, clusters: {}, suggestions: {} };
api.setShown({ rowId: "a", field: "title_translit", value: "Kitāb al-ḥaqāʾiq" });
api.recordSuggestionFor("b", "title_translit");
eq(edits.suggestions, {}, "a proposal shown for row a is NOT recorded against row b");

edits = { rows: {}, clusters: {}, suggestions: {} };
api.setShown({ rowId: "a", field: "title_translit", value: "X" });
api.recordSuggestionFor("a", "title_translation");
eq(edits.suggestions, {}, "a proposal for one field is NOT recorded against another");

edits = { rows: {}, clusters: {}, suggestions: {} };
api.setShown(null);
api.recordSuggestionFor("a", "title_translit");
eq(edits.suggestions, {}, "no proposal shown → nothing recorded");

// ------------------------------------------------------------- sweep source
eq(api.sweepSourceFor({ key: "title_translit" }, { title: "كتاب", author: "السلمي" }),
   { text: "كتاب", arabic: true }, "a title field reads from the title");
eq(api.sweepSourceFor({ key: "author_translit" }, { title: "كتاب", author: "السلمي" }),
   { text: "السلمي", arabic: true }, "an author field reads from the author");
eq(api.sweepSourceFor({ key: "city" }, { title: "كتاب", author: "السلمي" }),
   { text: "كتاب", arabic: true }, "a field with no source still identifies the entry");

// ----------------------------------------------------------------- reporting
if (failures.length) {
  console.log(`FAILED — ${failures.length} check(s):\n`);
  for (const f of failures) console.log(`  ✗ ${f}\n`);
  process.exit(1);
}
console.log("OK — transliteration logic passes all checks.");
