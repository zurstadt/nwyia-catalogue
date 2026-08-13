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
const nodes = new Map();
function byId(id){ if (!nodes.has(id)) nodes.set(id, node(id)); return nodes.get(id); }

// querySelectorAll only ever needs to enumerate the option buttons and the tab
// buttons the last render wrote; parse them back out of the recorded HTML.
function parseButtons(selector){
  const app = byId("app")._html, tabs = byId("tabs")._html;
  const src = selector === ".opt" ? app : tabs;
  const out = [];
  const re = selector === ".opt"
    ? /<button class="opt[^"]*"\s+data-ax="([^"]*)"\s*\n?\s*data-val="([^"]*)"/g
    : /<button data-tab="([^"]*)"/g;
  let m;
  while ((m = re.exec(src))) {
    const b = node(null);
    if (selector === ".opt"){ b.dataset = {ax: m[1], val: m[2]}; }
    else { b.dataset = {tab: m[1]}; }
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
    getElementById: id => (id === "payload" ? {textContent: payload} : byId(id)),
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
const DATA = R.data();

/* ---- assertions -------------------------------------------------------- */
let failures = 0;
function ok(cond, label, detail){
  if (cond) { console.log(`  ok   ${label}`); }
  else { failures++; console.log(`  FAIL ${label}${detail ? " — " + detail : ""}`); }
}

console.log("render");
for (const t of ["witness", "homograph", "ortho"]) {
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
  for (const t of ["witness", "homograph", "ortho"])
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
  const MARKS = /[\u064B-\u0652\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]/g;
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

console.log("\northography second axis");
{
  const it = R.items("ortho").find(x => x.confidence === "clear");
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

console.log("\nexport contract");
{
  const d = R.decisions();
  const total = ["witness","homograph","ortho"].reduce((a,t)=>a+R.items(t).length, 0);
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
{
  const it = R.items("witness")[0];
  R.setAx(it.id, "verdict", "fix");
  sandbox.__review.state()[it.id].confirmed = true;
  ok(R.complete(it), `${it.id}: confirmed is complete`);
  sandbox.__review.state()[it.id].deferred = true;
  sandbox.__review.state()[it.id].confirmed = false;
  const rec = R.decisions().find(x => x.id === it.id);
  ok(rec.disposition === "deferred" && rec.done === false,
     `${it.id}: deferred exports as parked, not resolved`);
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

console.log(`\n${failures === 0 ? "PASS" : "FAIL"} — ${failures} failing assertion(s)`);
process.exit(failures === 0 ? 0 : 1);
