# Literature grounding — three lessons promoted 2026-08-13

Single cycle, user-triggered. Covers the three advances promoted to skills while building the
transliteration-adjudication app and its ingest:

1. **Default-in-the-predicate** (`html-annotation-app`) — a prefilled field's default must live in the
   completeness predicate, not only in the markup.
2. **Patch, don't assign** (`html-annotation-app`, ingest contract) — a later pass must patch the current
   value, never assign a whole value the app precomputed.
3. **The invisible KEEP** (`annotation-app-design`) — a residual filter derived from the DATA cannot see a
   "keep / not-a-fault" ruling.

Verdicts: all three are **EXTENSION** — the components are established, the specific fusion is not.
Nothing here is claimed as NOVEL, and three sub-claims came back genuinely ungrounded (flagged below).

---

## 1. Default-in-the-predicate

**The bug.** A smart default was offered by rendering `value="${item.suggested}"` into an input, but
nothing was written to the state store. The done-gate read the store, found the axis unset, and disabled
Confirm — on a card that visibly showed a filled field. Two sources of truth for one value.

### Bibliography

| Source | Grounds |
|---|---|
| React, *Forms / controlled components* — react.dev/reference/react-dom/components/input; legacy.reactjs.org/docs/forms.html. "React state is the single source of truth." | The exact mechanism: an input whose visible value is not backed by the state object that owns it. React's ban on mixing controlled/uncontrolled inputs exists for this class. **Caveat:** the docs cover the DOM/state split generally, not the default-vs-predicate variant — analogous, not a direct match. |
| Redux, *Three Principles* — redux.js.org/understanding/thinking-in-redux/three-principles | The architectural principle the bug violated: one authoritative state tree. |
| Redux, *Deriving Data with Selectors* — redux.js.org/usage/deriving-data-selectors | **The shape of the correct fix.** Keep state minimal, derive the rest, because duplication "requires logic to… keep them in sync". Our fix is a selector by another name. |
| Hunt & Thomas, *The Pragmatic Programmer* (1999/2019), DRY: "every piece of knowledge must have a single, unambiguous, authoritative representation" | The general two-sources-of-truth diagnosis. |
| Meyer, "Applying Design by Contract", *IEEE Computer* 25(10), 1992, DOI 10.1109/2.161279 | One specification that both implementation and checker consult = one function both renderer and predicate call. **Caveat: DOI search-corroborated, not independently fetched.** |
| King, "Parse, Don't Validate" (2019), lexi-lambda.github.io | Reframes the fix as parsing the default into state (preserving evidence) rather than asserting a value the predicate never sees. Vocabulary fit; type-level in origin, so an analogy. |
| Nielsen, "Inactive GUI Controls: Show, Disable, or Hide?" (2024), uxtigers.com/post/inactive-buttons — "a disabled control must not be a communication dead end" | **Direct, strong.** Grounds the user-facing half: a disabled primary control with no explanation of the unmet condition. NN/G's *Why Disabled Buttons Hurt UX* corroborates. |
| Jachimowicz, Duncan, Weber & Johnson, "When and Why Defaults Influence Decisions: A Meta-Analysis of Default Effects", *Behavioural Public Policy* 3(2), 2019 (pooled d = 0.68, 58 studies) | Why offering a smart default matters at all — and why our provenance corollary matters: defaults strongly shape choice, so silently converting one into a confirmed answer is exactly the failure this predicts. |

### Link-up

**EXTENSION.** Single-source-of-truth (React/Redux/DRY) grounds the mechanism; Nielsen grounds the
symptom. What no source states is the **provenance corollary** — that seeding state at render time is the
*wrong* fix because it forges "the human touched this", so an untouched default must still export as
unchanged-from-source. That ties UI-state discipline to data-provenance integrity, a concern native to
annotation tooling rather than general UI engineering. That fusion is ours.

**Combine:**
- Adopt Redux's **derived-state / selector** vocabulary: name it `resolveDefault(item)`, a pure function
  called by both renderer and predicate. Gives the pattern a citable name and generalises to any
  prefilled or computed UI value ("is this stored or derived?").
- Adopt Nielsen's rule as the explicit HCI companion: a control disabled by an unmet predicate must
  render *why* — name the unmet axis — not merely grey out. Our app currently does the greying without
  the naming; this is a real open gap.
- Borrow DbC framing for the provenance half: the resolver returns `{value, touched}`, so touched-ness is
  part of the contract's output type rather than an afterthought.

**Ungrounded (flag).** "Prefilled-but-unconfirmed" has **no name** in survey methodology. AAPOR's
*Standard Definitions* formalises item nonresponse but does not distinguish a prefilled default that was
never actively confirmed from either an answer or a nonresponse. Genuine gap.

---

## 2. Patch, don't assign

**The bug.** The ingest applies several kinds of decision in sequence over the same field (pass 1 fixes a
spelling inside a title; pass 2 removes an attribution phrase from its end). Each payload was rendered
from a snapshot taken when the worklist was *built*. Pass 2 assigned `record.title = decision.new_title`
and silently reverted pass 1. Invisible three ways: each pass truthfully reported success, the visible
part of pass 2 looked right, and it surfaced only as a re-run finding work already done.

### Bibliography

| Source | Grounds |
|---|---|
| Berenson, Bernstein, Gray, Melton, O'Neil & O'Neil, "A Critique of ANSI SQL Isolation Levels", SIGMOD 1995, DOI 10.1145/223784.223785 (preprint arXiv:cs/0701157) | **The classic name.** P4 Lost Update: T1 reads X, T2 writes X, T1 writes from its stale read — T2's update silently lost, both commits report success. **Scope limit, stated below.** |
| Kung & Robinson, "On Optimistic Methods for Concurrency Control", *ACM TODS* 6(2), 1981, DOI 10.1145/319566.319567 | Grounds the **fix**: read → **validate** → write. Our "accept only if the result matches the adjudicated value modulo normalization, else refuse" is the validation phase. (Could not confirm the paper itself uses "lost update"; the mechanism is confirmed.) |
| Ellis & Gibbs, "Concurrency Control in Groupware Systems", SIGMOD 1989, DOI 10.1145/67544.66963 | Foundational Operational Transformation: propagate and apply the **operation**, transformed against intervening ones, not the whole document. |
| Shapiro, Preguiça, Baquero & Zawirski, "Conflict-Free Replicated Data Types", SSS 2011, DOI 10.1007/978-3-642-24550-3_29 | **The sharpest formalism.** CvRDT (state-based, merge whole state) vs CmRDT (op-based, apply against current). "Assign whole value" vs "apply operation" is exactly that axis. Their LWW-Register is documented as still losing updates when a newer whole-value write discards a concurrent one — our bug in CRDT terms. |
| RFC 9110 (HTTP Semantics), IETF 2022, §13.1.1 `If-Match` | The compare-and-swap formulation: a write is accepted only if the current ETag matches the one read; else 412. MDN frames it explicitly as preventing lost update. |
| Jacobson, "A Formalization of Darcs Patch Theory Using Inverse Semigroups", UCLA CAM Report 09-83, 2009 | Patch commutation and inverse — the algebra of why operations compose where snapshots clobber. **Grey literature (tech report), cite as such.** |
| Breck, Polyzotis, Roy, Whang & Zinkevich, "Data Validation for Machine Learning", MLSys 2019 | Loose support only: per-stage success ≠ pipeline correctness. Their subject is schema/statistical anomalies, not sequential-edit conservation. |
| Kimball & Caserta, *The Data Warehouse ETL Toolkit*, Wiley 2004 — audit-balance-control / control totals | End-state reconciliation as a discipline. **Specific passage not verified this pass — cite the concept, not a quotation.** |

### Link-up

**EXTENSION, with a scope correction worth carrying.** Lost Update is formally defined over **two
concurrent, overlapping transactions**. Our bug is **single-threaded and sequential**: pass 1 completes
before pass 2 starts, and the staleness comes from a snapshot taken at worklist-build time, not from a
racing transaction. The anomaly's *shape* is identical (truthful per-step success, one write erasing
another's committed effect); the *cause* is not concurrency. Say so, or the citation overclaims.

Likewise **"blind write" does not fit**: a blind write has no prior read of the item; pass 2 *did* read —
it read stale. Ours is a stale read-modify-write. Claiming the blind-write label would overclaim
precision. **Write skew and ABA are not matches** either — ABA is the opposite direction (a spuriously
*unchanged*-looking value, not a genuinely stale one).

**Combine:**
- Name it **"stale-snapshot write"** rather than reusing "lost update" unqualified — a lost-update-shaped
  anomaly with a stale-snapshot cause, in a sequential pipeline.
- Give each decision a **read-version** (a hash or normalized form of the field at snapshot time) and
  treat it as an `If-Match` precondition; apply as a CmRDT-style operation, or abort and requeue.
- Strengthen the conservation check from "what pass N removed is gone" to a **replay**:
  `current == apply(op_n, … apply(op_1, original))` modulo normalization. That is ETL audit-balance-control
  crossed with patch composition — the end state becomes provable rather than spot-checked.

---

## 3. The invisible KEEP

**The bug.** The residual worklist is computed by asking the source "is the fault still there?" — cheap,
needs no decision store, self-healing. But a ruling of *keep / not-a-fault* resolves an item while
changing nothing, so the detector fires again and re-proposes what the annotator already settled.

### Bibliography

| Source | Grounds |
|---|---|
| **Spacco, Hovemeyer & Pugh, "Tracking Defect Warnings Across Versions", MSR 2006, DOI 10.1145/1137983.1138013** | **The strongest single match.** Motivated verbatim by the need "to remember decisions about code that has been reviewed and found to be safe *despite the occurrence of a warning*" — a near-exact prior statement of KEEP-persistence in a detector-scans-source architecture, and it solves the id-drift half too. |
| Mozilla Bugzilla bug 13534, "REMIND and LATER considered harmful" (1999) | The **dual** case, verified: deferral values filed on the *resolution* field, so deferred bugs vanish from open queries. Theirs is a non-resolution treated as settled; ours is a settlement that leaves no mark. |
| Sadowski, van Gogh, Jaspan, Söderberg & Winter, "Tricorder: Building a Program Analysis Ecosystem", ICSE 2015; and *Software Engineering at Google* ch. 20 (abseil.io/resources/swe-book/html/ch20.html) | A production system **caught in the failure mode**: the "Not useful" button (≈250 clicks/day) files a bug against the analyzer author and does **not** suppress the finding next run. |
| van der Sijs, Aarts, Vulto & Berg, "Overriding of Drug Safety Alerts in CPOE", *JAMIA* 13(2), 2006, DOI 10.1197/jamia.M1809 | Independent field, identical fix and identical harm: "entering (coded) overriding decisions **should prevent future alert generation**"; override rates 49–96%, with repetition the dominant driver of alert fatigue. |
| Shapiro et al. 2011, DOI 10.1007/978-3-642-24550-3_29 (as above) | **Tombstones**: deletion is an explicit positive marker that avoids silent resurrection, never inferred from absence. Grounds the structural fix. |
| Reiter, "On Closed World Data Bases", in Gallaire & Minker (eds.), *Logic and Data Bases*, Plenum 1978, 55–76 | **The logical root cause.** The detector performs closed-world inference: "not provably faulty" is read as "not a fault-worthy item", conflating *never checked* with *checked and cleared*. |
| Clark, "Negation as Failure", same volume, 293–322 | The mechanism precisely: `residual = ¬detected(fault, row)`, where ¬detected has two causes NAF cannot distinguish without an explicit fact for the second. |
| Liargkovas, Panourgia & Spinellis, "Quieting the Static: A Study of Static Analysis Alert Suppressions", arXiv:2311.07482 (2023) | Empirical caution on suppression comments across 1,425 Java projects: most suppressions are not about false positives; many encode negligence. Supporting context for the combine idea, not the core lesson. |
| Johnson, Song, Murphy-Hill & Bowdidge, ICSE 2013, DOI 10.1109/ICSE.2013.6606613 | False positives and warning presentation as adoption barriers. **Only abstract-level verification** on the specific re-fire claim. |
| Sadowski et al., "Lessons from Building Static Analysis Tools at Google", *CACM* 61(4), 2018, DOI 10.1145/3188720 | "Developers, not tool authors, determine the perceived false-positive rate" — trust is the scarce resource. **Partially verified (403 on full text).** |

### Link-up

**EXTENSION.** The instance-level lesson is KNOWN and has been **independently rediscovered at least
three times** — bug tracking, static analysis, clinical decision support — each solving it ad hoc with a
different mechanism (a resolution field, a suppression comment, a coded override reason, a fingerprint
match). What no source states is the **abstract, cross-domain form**: that this is a structural property
of any *data-derived* residual filter as against a *decision-log-derived* one, traceable to
closed-world/negation-as-failure unsoundness, with the fix framed as a tombstone requirement. That
synthesis, plus the generalization *"applies wherever the human's answer is 'you are wrong AND the source
is right'"*, is the delta.

**Combine:**
- **Key the KEEP on a content fingerprint, not a row id** (Spacco et al.): normalized surrounding tokens +
  fault type + position-within-field, with an approximate-match fallback, so a keep survives re-ordering
  or a minor edit instead of silently detaching. Our store is currently keyed on the worklist item id,
  which is stable only while the builder's id scheme is.
- **Treat the KEEP store as a tombstone, not a flag** (Shapiro et al.): append-only, monotonic, recording
  "this firing was reviewed and rejected against data as of hash X". That also answers *when a keep
  expires* — a hash mismatch on replay re-surfaces the card for re-confirmation, rather than permanent
  silence or blind re-fire.
- **Mine the KEEP store to fix the detector** (van der Sijs' second-order recommendation): a detector
  accumulating many keeps on one shape of "fault" is miscalibrated. The suppression store becomes a
  precision-regression corpus for free.

**Ungrounded (flag).** No precedent found for "the label with no footprint" as a named phenomenon in
active learning or the reject-option literature. Mild point of contrast worth noting: IR **relevance
feedback stores negative judgements by design** — arguably the field that got this right earliest.

---

## Open questions / what to read next

- Meyer 1992 DOI and the Kimball control-totals passage need direct verification before being quoted.
- Johnson et al. 2013 and Sadowski et al. 2018 need full-text access to confirm they speak to *re-firing
  dismissed findings* specifically, rather than false positives generally.
- Spacco et al.'s exact vs approximate warning-matching strategies are worth reading properly before
  re-keying the KEEP store — they compared several, and the choice determines how a keep behaves under
  upstream edits.
