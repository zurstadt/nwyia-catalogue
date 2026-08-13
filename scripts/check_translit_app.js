/**
 * Headless gate for review/translit_adjudicate.html.
 *
 * Drives the REAL baked JavaScript through a minimal DOM stub — a static read of
 * the source cannot catch a render that throws, a Confirm gate that opens on a
 * half-answered card, or an export that silently omits items nobody clicked.
 *
 *     node scripts/check_translit_app.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP = path.join(__dirname, "..", "review", "translit_adjudicate.html");
const html = fs.readFileSync(APP, "utf8");

const payload = html.match(
  /<script type="application\/json" id="payload">([\s\S]*?)<\/script>/)[1];
const code = html.match(
  /<script>\n"use strict";([\s\S]*?)<\/script>\s*<\/body>/)[1];

/* ---- DOM stub ---------------------------------------------------------- */
// Every node records the HTML written into it, so assertions can inspect what a
// render actually produced rather than what the source appears to produce.
function node(id){
  return {
    id, _html: "", textContent: "", value: "", disabled: false,
    style: {}, dataset: {},
    classList: {_s:new Set(),
      add(c){this._s.add(c)}, remove(c){this._s.delete(c)},
      toggle(c){this._s.has(c)?this._s.delete(c):this._s.add(c)},
      contains(c){return this._s.has(c)}},
    get innerHTML(){ return this._html; },
    set innerHTML(v){ this._html = String(v); },
    focus(){}, blur(){}, click(){ this.onclick && this.onclick(); },
    appendChild(){}, addEventListener(){},
  };
}

// Parse a rendered <button> GENERICALLY — attributes in any order, every data-*
// captured. The previous version matched `data-ax` followed by `data-val`, which
// silently excluded the ortho competing-reading chips (they carry `data-fill`)
// from the very flat list the digit handler indexes. A gate whose selector is
// narrower than the browser's cannot see a mislabelled option, and its assertion
// passes vacuously. Match what the browser matches: class contains "opt".
const BTN_RE = /<button\b([^>]*)>([\s\S]*?)<\/button>/g;
function attrsOf(s){
  const out = {};
  const re = /([a-zA-Z][\w-]*)\s*=\s*"([^"]*)"/g;
  let m;
  while ((m = re.exec(s))) out[m[1]] = m[2];
  return out;
}

function boot(payloadText){
  // Per-boot DOM and storage. Module-global state made a second payload
  // impossible, which is why the empty strata could never be exercised.
  const nodes = new Map();
  function byId(id){ if (!nodes.has(id)) nodes.set(id, node(id)); return nodes.get(id); }

  function parseButtons(selector){
    const src = selector === ".opt" ? byId("app")._html : byId("tabs")._html;
    const out = [];
    let m;
    BTN_RE.lastIndex = 0;
    while ((m = BTN_RE.exec(src))) {
      const a = attrsOf(m[1]), body = m[2];
      const classes = (a.class || "").split(/\s+/);
      if (selector === ".opt" ? !classes.includes("opt") : a["data-tab"] === undefined)
        continue;
      const b = node(null);
      b.dataset = {};
      for (const k of Object.keys(a))
        if (k.startsWith("data-"))
          b.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = a[k];
      // Capture the PRINTED number too. Discarding it is what let a card print one
      // digit on an option and fire a different one — the gate has to compare the
      // label the annotator reads against the index the key handler uses.
      const k = body.match(/<span class="k">(\d+)<\/span>/);
      if (k) b.label = Number(k[1]);
      out.push(b);
    }
    return out;
  }

  const store = new Map();
  const sandbox = {
    console,
    localStorage: {
      getItem: k => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: k => store.delete(k),
    },
    document: {
      getElementById: id => (id === "payload" ? {textContent: payloadText} : byId(id)),
      querySelectorAll: sel => parseButtons(sel),
      createElement: () => ({click(){}, set href(v){}, get href(){return "";}}),
      addEventListener(){},
    },
    window: {scrollTo(){}},
    alert: msg => { throw new Error("unexpected alert: " + msg); },
    Blob: function(){}, URL: {createObjectURL: () => "", revokeObjectURL(){}},
    setTimeout: () => 0,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, {filename: "translit_adjudicate.html"});
  const R = sandbox.__review;
  return {R, sandbox, byId, store, data: R.data(),
          strata: Object.keys(R.data().strata)};
}

const BAKE = boot(payload);
const {R, sandbox, byId} = BAKE;
const DATA = BAKE.data;
// One list, consumed everywhere. A stratum added to the app but not here would
// make the export-completeness assertion silently under-count instead of fail.
const STRATA = Object.keys(DATA.strata);
// What a "decided" value looks like per axis, so a test can settle any card without
// knowing which stratum it came from.
const FILL = {verdict: "fix", disposition: "keep", form: "accept", translit: "x"};
function axesOf(it){
  if (it.stratum === "witness") return ["verdict"];
  if (it.stratum === "attribution") return ["disposition"];
  if (it.stratum === "homograph") return it.keys.map(k => "key:" + k.key);
  return (it.rows && it.rows.length) || (it.scope && it.scope.titles.length)
       ? ["form", "translit"] : ["form"];
}

/* ---- assertions -------------------------------------------------------- */
let failures = 0;
function ok(cond, label, detail){
  if (cond) { console.log(`  ok   ${label}`); }
  else { failures++; console.log(`  FAIL ${label}${detail ? " — " + detail : ""}`); }
}

console.log("render");
for (const t of STRATA) {
  const n = R.items(t).length;
  let threw = null;
  for (let i = 0; i < n; i++) {
    try { R.go(t, i); } catch (e) { threw = `${t}[${i}]: ${e.message}`; break; }
    if (!byId("app")._html.includes("card")) { threw = `${t}[${i}] rendered no card`; break; }
  }
  ok(!threw, `every ${t} card renders (${n})`, threw);
}

console.log("\nescaping");
{
  // Nothing from the payload may reach innerHTML as markup: the two sentinels the
  // highlighter uses must never survive into the rendered string.
  let leaked = null;
  for (const t of STRATA)
    for (let i = 0; i < R.items(t).length; i++) {
      R.go(t, i);
      const h = byId("app")._html;
      if (h.includes("") || h.includes("")) leaked = `${t}[${i}]`;
    }
  ok(!leaked, "no highlight sentinel survives a render", leaked);
  ok(!html.includes("</script>", html.indexOf('id="payload"') + 1)
     || !payload.includes("</"), "inlined JSON contains no raw </");
}

console.log("\nconjunction gate");
// The homograph stratum empties out once every contest is settled. A skipped
// assertion is announced, never silently passed.
if (R.items("homograph").filter(x => x.keys.length > 1).length === 0) {
  console.log("  skip homograph conjunction — no multi-key homograph left in the bake");
} else {
  const multi = R.items("homograph").filter(x => x.keys.length > 1);
  const it = multi[0];
  R.setAx(it.id, "key:" + it.keys[0].key, it.keys[0].options[0].value);
  ok(!R.ready(it), `${it.id}: one of ${it.keys.length} readings answered is NOT ready`);
  R.setAx(it.id, "key:" + it.keys[1].key, it.keys[1].options[0].value);
  ok(R.ready(it), `${it.id}: both readings answered is ready`);
  ok(!R.complete(it), `${it.id}: ready but unconfirmed is NOT complete`);
  // toggling an axis back off must reopen the whole decision
  R.setAx(it.id, "key:" + it.keys[0].key, it.keys[0].options[0].value);
  ok(!R.ready(it), `${it.id}: un-answering one axis reopens the decision`);
}

console.log("\nšaddah proposals");
{
  // A šaddah card must differ from its word ONLY by inserted combining marks. If a
  // derivation ever changes a letter, this catches it before it reaches the card.
  // The mark class comes from the PAYLOAD, i.e. from the pipeline's own
  // unicodedata-derived definition. The hand-written copy that stood here was a
  // FOURTH definition of "mark" in this repo and it disagreed with the two it was
  // checking — a gate that grades against its own private rule grades nothing.
  ok(typeof DATA.mark_class === "string" && DATA.mark_class.length > 2,
     "the payload carries the pipeline's own mark class", String(DATA.mark_class));
  const MARKS = new RegExp(DATA.mark_class, "g");
  const sh = R.items("ortho").filter(x => String(x.confidence).startsWith("shadda"));
  const bad = sh.filter(x => x.proposed &&
                        x.proposed.replace(MARKS, "") !== x.word.replace(MARKS, ""));
  ok(bad.length === 0, `${sh.length} šaddah cards: every proposal differs only by marks`,
     bad.map(x => `${x.word}->${x.proposed}`).join(", "));
  const noProp = sh.filter(x => !x.proposed);
  ok(noProp.length === 0 || noProp.every(x => /type the form/i.test(x.reason)),
     `${noProp.length} undecidable placements say so on the card`);
  // A card with no proposal must not offer "accept" — there is nothing to accept.
  if (noProp.length) {
    R.go("ortho", R.items("ortho").indexOf(noProp[0]));
    const opts = [...sandbox.document.querySelectorAll(".opt")].map(b => b.dataset.val);
    ok(!opts.includes("accept"), "a no-proposal card offers no accept option",
       opts.join(","));
    R.setAx(noProp[0].id, "form", "keep");
    ok(R.ready(noProp[0]), "a no-proposal card can still be settled as keep");
  }
}

console.log("\nhamza proposals");
{
  const CARRIERS = "\u0623\u0625\u0622\u0671";           // أ إ آ ٱ
  const hz = R.items("ortho").filter(x => String(x.confidence).startsWith("hamza"));
  // A hamza card restores a CARRIER on an existing bare ālif. It may therefore
  // differ from its word in exactly one position, that position must hold a
  // carrier, and the word must have held a plain ālif there. Anything else means
  // the derivation changed a letter it had no business touching.
  const bad = hz.filter(x => {
    if (!x.proposed) return false;
    if (x.proposed.length !== x.word.length) return true;
    const diff = [...x.word].map((c,i) => c === x.proposed[i] ? null : i).filter(i => i !== null);
    return diff.length !== 1 || !CARRIERS.includes(x.proposed[diff[0]])
        || x.word[diff[0]] !== "\u0627";
  });
  ok(bad.length === 0, `${hz.length} hamza cards: each swaps one bare ālif for a carrier`,
     bad.map(x => `${x.word}->${x.proposed}`).join(", "));

  // Hamzat waṣl must never be proposed for a carrier. These are attested in the
  // corpus and every one of them is form VII/VIII/X or closed-class.
  const WASL = ["\u0627\u0635\u0637\u0644\u0627\u062d",
                "\u0627\u0635\u0637\u0644\u0627\u062d\u0627\u062a",
                "\u0627\u0644\u0627\u0635\u0637\u0644\u0627\u062d",
                "\u0627\u0644\u0627\u0646\u062a\u0635\u0627\u0631",
                "\u0627\u0628\u0646"];
  const leaked = WASL.filter(w => hz.some(x => x.word === w));
  ok(leaked.length === 0, "no hamzat-waṣl word is offered a carrier", leaked.join(", "));

  // A derived card restores a carrier and nothing else, so it must be key-neutral.
  // Only a hand-written ORTHO card may move a normalized key, and it must say so.
  const derived = R.items("ortho").filter(x => /^[hs]-/.test(x.id));
  const moved = derived.filter(x => x.key_changes);
  ok(moved.length === 0, "no derived šaddah/hamza card moves a normalized key",
     moved.map(x => x.word).join(", "));
  const declared = R.items("ortho").filter(x => x.key_changes);
  ok(declared.every(x => x.translit),
     "every key-moving card carries the transliteration its new key needs",
     declared.filter(x => !x.translit).map(x => x.id).join(", "));

  // Every surface a card claims to touch must be non-empty somewhere, or the card
  // is proposing an edit with no target. This once covered the derived cards only,
  // because only they carried a scope — which is precisely how a hand-written card
  // came to be judged on titles alone and dropped while eleven author fields and
  // three cluster names still spelled the fault.
  const all = R.items("ortho");
  const noScope = all.filter(x => !x.scope);
  ok(noScope.length === 0, "every ortho card carries a three-surface scope",
     noScope.map(x => x.id).join(", "));
  const empty = all.filter(x => x.scope && !x.scope.titles.length
                             && !x.scope.authors.length && !x.scope.clusters.length);
  ok(empty.length === 0, "every ortho card names at least one surface to edit",
     empty.map(x => x.word).join(", "));

  // A card whose word sits ONLY in author fields and cluster names must still be
  // answerable: it has no per-word romanization, so demanding one leaves Confirm
  // dead forever. The complement of the same rule as the transliteration axis.
  const nameOnly = all.filter(x => x.scope && !x.scope.titles.length
                                && (x.scope.authors.length || x.scope.clusters.length));
  const dead = nameOnly.filter(x => {
    R.setAx(x.id, "form", "accept");
    const isReady = R.ready(x);
    R.setAx(x.id, "form", "accept");            // toggle back off
    return !isReady;
  });
  ok(dead.length === 0,
     `${nameOnly.length} name-only card(s) are answerable on the Arabic form alone`,
     dead.map(x => x.id).join(", "));
}

console.log("\nattribution");
if (R.items("attribution").length === 0) {
  console.log("  skip — attribution stratum is empty (all tails settled)");
} else {
  const at = R.items("attribution");
  const it = at[0];
  R.setAx(it.id, "disposition", "strip");
  const rec = R.decisions().find(d => d.id === it.id);
  ok(rec.tail === it.tail && rec.was === it.title,
     "a strip exports the tail it removes AND the title it removed it from");
  ok(rec.target === it.proposed_title, "…and the resulting title");
  ok(at.every(x => x.title.includes(x.tail)),
     "every tail is a literal substring of its title");
  ok(at.every(x => !x.aligned || x.proposed_translit !== null),
     "an aligned row carries a trimmed transliteration");
  R.setAx(it.id, "disposition", "strip");   // toggle back off
  ok(!R.ready(it), "un-answering the disposition reopens the decision");
}

console.log("\northography second axis");
// Pick any card that actually HAS the second axis, rather than a fixed confidence
// tier — the tiers empty out as the batch is worked through.
{
  const it = R.items("ortho").find(x => x.proposed && axesOf(x).includes("translit"));
  if (!it) console.log("  skip — no ortho card with a transliteration axis remains");
  else {
  R.setAx(it.id, "form", "accept");
  ok(R.ready(it), `${it.id}: accept + prefilled translit is ready`);
  const rec = R.decisions().find(d => d.id === it.id);
  ok(rec.translit === it.translit, `${it.id}: export carries the transliteration`,
     JSON.stringify(rec.translit));
  R.setAx(it.id, "form", "keep");
  const keep = R.decisions().find(d => d.id === it.id);
  ok(keep.target === it.word && keep.translit === null,
     `${it.id}: "keep" exports the word unchanged and no new translit`);
  }
}

console.log("\nevery card is answerable");
{
  // The defect this catches: a card whose required axis asks for a value that does
  // not exist for it, so Confirm is dead and the annotator has no way to proceed.
  // Accepting the proposal must make a card ready — except where the corpus itself
  // records competing readings, which is a real question and must be ANSWERABLE.
  const stuck = [], needsPick = [];
  for (const it of R.items("ortho")) {
    R.setAx(it.id, "form", "accept");
    if (R.ready(it)) continue;
    // pick the first competing reading, the way the chips let the annotator do
    if ((it.translits || []).length > 1) {
      R.state()[it.id].translit = it.translits[0];
      (R.ready(it) ? needsPick : stuck).push(it.id);
    } else stuck.push(it.id);
  }
  ok(stuck.length === 0, "accepting a proposal makes every ortho card confirmable",
     stuck.join(", "));
  console.log(`  note ${needsPick.length} card(s) additionally require picking among `
            + `competing recorded readings: ${needsPick.join(", ") || "none"}`);

  for (const t of ["witness", "attribution"]) {
    const items = R.items(t);
    if (!items.length) { console.log(`  skip ${t} — stratum is empty`); continue; }
    const bad = [];
    for (const it of items) {
      R.setAx(it.id, t === "witness" ? "verdict" : "disposition",
              t === "witness" ? "fix" : "strip");
      if (!R.ready(it)) bad.push(it.id);
    }
    ok(bad.length === 0, `every ${t} card is confirmable once answered`, bad.join(", "));
  }
}

console.log("\nnumber keys select what they print");
{
  // The digit handler picks `querySelectorAll(".opt")[key-1]`, so the number shown
  // on a button must equal its flat position. A per-group formula silently diverges
  // the moment two groups have different option counts.
  const bad = [];
  for (const t of STRATA) {
    for (let i = 0; i < R.items(t).length; i++) {
      R.go(t, i);
      const opts = sandbox.document.querySelectorAll(".opt");
      opts.forEach((b, ix) => {
        if (b.label !== undefined && b.label !== ix + 1)
          bad.push(`${R.items(t)[i].id}: option ${ix + 1} is printed "${b.label}"`);
      });
    }
  }
  ok(bad.length === 0, "every option's printed number is its flat index",
     bad.slice(0, 6).join("; "));
}

console.log("\nexport contract");
{
  const d = R.decisions();
  const total = STRATA.reduce((a,t)=>a+R.items(t).length, 0);
  ok(d.length === total,
     `export walks the worklist, not touched state (${d.length}/${total})`);
  const untouched = d.filter(x => x.disposition === "open");
  ok(untouched.length > 0 && untouched.every(x => x.done === false),
     "untouched items export as explicit open/not-done records");
  ok(d.every(x => ["resolved","deferred","open"].includes(x.disposition)),
     "every record carries a disposition");
  const hg = d.filter(x => x.stratum === "homograph");
  ok(hg.every(x => x.context && x.context.options),
     "homograph records carry the options that shaped the decision");
}

console.log("\ndeferral is not resolution");
// Any stratum can empty out as its work is settled — the residual bake is supposed
// to shrink to nothing. Pick whatever stratum still has a card rather than assuming
// one; announce the skip if none does.
{
  const host = STRATA.map(t => R.items(t)).find(xs => xs.length);
  const it = host && host[0];
  if (!it) console.log("  skip — every stratum is empty");
  else {
  // Assign, do not toggle: setAx flips a value that is already set, so this test
  // would silently depend on whether an earlier block had touched the same card.
  // Whatever the host stratum is, mark it decided the way its own axes require.
  axesOf(it).forEach(ax => sandbox.__review.state()[it.id][ax] = FILL[ax] || "keep");
  sandbox.__review.state()[it.id].confirmed = true;
  delete sandbox.__review.state()[it.id].deferred;
  ok(R.complete(it), `${it.id}: confirmed is complete`);
  sandbox.__review.state()[it.id].deferred = true;
  sandbox.__review.state()[it.id].confirmed = false;
  const rec = R.decisions().find(x => x.id === it.id);
  ok(rec.disposition === "deferred" && rec.done === false,
     `${it.id}: deferred exports as parked, not resolved`);
  }
}

console.log("\ncomposition lookup table");
{
  let bad = [];
  if (R.items("homograph").length === 0)
    console.log("  skip — homograph stratum is empty");
  for (const it of R.items("homograph")) {
    const combos = Object.keys(it.compositions);
    const expect = it.keys.reduce((n, k) => n * k.options.length, 1);
    if (combos.length !== expect) bad.push(`${it.id}: ${combos.length}≠${expect}`);
    if (combos.some(c => !it.compositions[c])) bad.push(`${it.id}: a null composition`);
  }
  ok(bad.length === 0, "every reading combination is precomputed", bad.join("; "));
}

/* ---- fixture bake ------------------------------------------------------- */
// The residual worklist shrinks to nothing as work is settled, so whole strata
// are empty in the shipped bake and every assertion over them SKIPS. A skipped
// assertion guards nothing. This payload is hand-built to the builder's own item
// shapes and driven through the same real app code, so the cards that no longer
// occur in the corpus are still covered — including the two shapes that no bake
// has ever produced together: an ortho card whose word has competing recorded
// readings (two button groups on one card) and a homograph card whose keys offer
// DIFFERENT numbers of options.
const FIXTURE = JSON.stringify({
  schema_version: 1,
  task: "translit-adjudication",
  counts: {witness: 1, homograph: 1, ortho: 1, attribution: 1},
  strata: {
    ortho: [{
      id: "o-fix", stratum: "ortho", word: "الاول", proposed: "الأوّل",
      confidence: "house-style", reason: "fixture: competing recorded readings.",
      key_changes: false, translit: "al-awwal",
      translits: ["al-awwal", "al-ūlā"],          // two chips → a second .opt group
      rows: [{id: "r1", title: "كتاب الاول", after: "كتاب الأوّل",
              translit: "kitāb al-awwal"}],
    }],
    homograph: [{
      id: "r9", stratum: "homograph", title: "كتاب من الفرق", author: "—",
      gloss: [{key: "كتاب", raw: null, translit: "kitāb", contested: false},
              {key: "من", raw: null, translit: null, contested: true},
              {key: "الفرق", raw: null, translit: null, contested: true}],
      // The C2 shape: key one offers TWO readings, key two offers THREE. Any
      // per-key numbering formula agrees with the flat digit handler only when
      // every key happens to offer the same count.
      keys: [
        {key: "من", raw: "من", note: "", suggest: "min", options: [
          {value: "min", witnesses: ["r1"],
           witness_titles: [{id: "r1", title: "t", translit: "min"}]},
          {value: "man", witnesses: ["r2"],
           witness_titles: [{id: "r2", title: "t", translit: "man"}]}]},
        {key: "الفرق", raw: "الفرق", note: "", suggest: "al-farq", options: [
          {value: "al-farq", witnesses: ["r3"],
           witness_titles: [{id: "r3", title: "t", translit: "al-farq"}]},
          {value: "al-firaq", witnesses: ["r4"],
           witness_titles: [{id: "r4", title: "t", translit: "al-firaq"}]},
          {value: "al-furuq", witnesses: ["r5"],
           witness_titles: [{id: "r5", title: "t", translit: "al-furuq"}]}]},
      ],
      compositions: {
        "min|al-farq": "kitāb min al-farq", "min|al-firaq": "kitāb min al-firaq",
        "min|al-furuq": "kitāb min al-furuq", "man|al-farq": "kitāb man al-farq",
        "man|al-firaq": "kitāb man al-firaq", "man|al-furuq": "kitāb man al-furuq",
      },
    }],
    witness: [{
      id: "r8", stratum: "witness", row: "r8", word: "المواقف",
      title: "كتاب المواقف", title_translit: "kitāb al-mawāqif",
      current: "al-mawāqif", proposed: "al-mawāqif",
      why: "fixture: sole witness for a losing reading.", unblocks: ["r9"],
    }],
    attribution: [{
      id: "r7-attr", stratum: "attribution", row: "r7", marker: "لابي",
      verdict: "commentary", note_why: "fixture: li- attribution tail.",
      title: "كتاب المواقف لابي علي", title_translit: "kitāb al-mawāqif li-Abī ʿAlī",
      tail: "لابي علي", tail_translit: "li-Abī ʿAlī",
      proposed_title: "كتاب المواقف", proposed_translit: "kitāb al-mawāqif",
      aligned: true, author_ar: "ابو علي", author: "Abū ʿAlī",
      catalog_note: "", collides_with: [],
    }],
  },
});

console.log("\nfixture bake — strata the shipped bake cannot exercise");
{
  const F = boot(FIXTURE);
  const fStrata = F.strata;

  let threw = null;
  for (const t of fStrata)
    for (let i = 0; i < F.R.items(t).length; i++) {
      try { F.R.go(t, i); } catch (e) { threw = `${t}[${i}]: ${e.message}`; break; }
      if (!F.byId("app")._html.includes("card")) threw = `${t}[${i}] rendered no card`;
    }
  ok(!threw, "every fixture card renders", threw);

  // The assertion the shipped bake can only pass vacuously: an ortho card with
  // competing readings renders TWO groups of .opt buttons, and the digit handler
  // indexes them as one flat list.
  const bad = [];
  for (const t of fStrata)
    for (let i = 0; i < F.R.items(t).length; i++) {
      F.R.go(t, i);
      F.sandbox.document.querySelectorAll(".opt").forEach((b, ix) => {
        if (b.label !== undefined && b.label !== ix + 1)
          bad.push(`${F.R.items(t)[i].id}: option ${ix + 1} is printed "${b.label}"`);
      });
    }
  ok(bad.length === 0,
     "every option's printed number is its flat index — two-group ortho card and "
     + "an asymmetric 2+3-option homograph card", bad.join("; "));

  // …and pressing that digit must select the option whose label it is.
  {
    const it = F.R.items("ortho")[0];
    F.R.go("ortho", 0);
    const opts = F.sandbox.document.querySelectorAll(".opt");
    const chip = opts.find(b => b.dataset.val === it.translits[1]
                             || b.dataset.fill === it.translits[1]);
    ok(chip && chip.label === opts.indexOf(chip) + 1,
       "the second competing-reading chip is fired by the digit it prints",
       chip ? `prints ${chip.label}, sits at ${opts.indexOf(chip) + 1}` : "chip not rendered");
  }

  // Conjunction over keys with unequal option counts.
  {
    const it = F.R.items("homograph")[0];
    F.R.setAx(it.id, "key:" + it.keys[0].key, it.keys[0].options[0].value);
    ok(!F.R.ready(it), "one of two readings answered is NOT ready");
    F.R.setAx(it.id, "key:" + it.keys[1].key, it.keys[1].options[2].value);
    ok(F.R.ready(it), "both readings answered is ready");
    const rec = F.R.decisions().find(d => d.id === it.id);
    ok(rec.readings[it.keys[1].key] === "al-furuq",
       "the export carries the reading that was actually chosen",
       JSON.stringify(rec.readings));
  }

  // Attribution: the stratum H2 lives in, empty in every bake since it was built.
  {
    const it = F.R.items("attribution")[0];
    F.R.setAx(it.id, "disposition", "strip");
    const rec = F.R.decisions().find(d => d.id === it.id);
    ok(rec.action === "strip_tail" && rec.target === it.proposed_title,
       "a strip exports strip_tail and the resulting title",
       JSON.stringify([rec.action, rec.target]));
    ok(rec.was === it.title && rec.tail === it.tail,
       "…and the title it removed the tail from");
    ok(rec.target_translit === it.proposed_translit,
       "an aligned row exports the trimmed transliteration");
    F.R.setAx(it.id, "disposition", "keep");
    const keep = F.R.decisions().find(d => d.id === it.id);
    ok(keep.action === "keep" && keep.target === it.title,
       "a keep exports the title unchanged", JSON.stringify([keep.action, keep.target]));
  }

  // Composition table: every combination of an asymmetric key pair is precomputed.
  {
    const it = F.R.items("homograph")[0];
    const expect = it.keys.reduce((n, k) => n * k.options.length, 1);
    const combos = Object.keys(it.compositions);
    ok(combos.length === expect && combos.every(c => it.compositions[c]),
       `all ${expect} reading combinations are precomputed`,
       `${combos.length} present`);
  }
}

console.log(`\n${failures === 0 ? "PASS" : "FAIL"} — ${failures} failing assertion(s)`);
process.exit(failures === 0 ? 0 : 1);
