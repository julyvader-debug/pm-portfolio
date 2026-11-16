# PRD: VPD Fee Calculator — Auto-calculate variable per-dose pricing for home delivery SKUs

## 1. Problem Statement

The pricing team manually calculates individual pill costs and VPD fees for every home delivery SKU added to PMT. The current tool supports only a flat monthly-dose fee that cannot be split to the per-pill level without overpricing the product. Pricing is stored as hard-coded values, so when a manufacturer raises their price, the team must manually re-enter fees for every affected SKU — a process that takes hours per cycle and introduces errors that the company is ultimately responsible for.

## 2. Research Summary

- Pricing team manually divides acquisition cost by units per package to get individual pill cost for every VPD SKU. (pricing team working session)
- The only available fee type in PMT today is "monthly dose," a flat amount. Applying it per pill makes the retail price unacceptably high, because the fee can exceed the cost of the pill itself. (pricing team working session)
- Hard-coded pricing in the system means manufacturer price changes require manual re-entry of every hard-coded fee — there is no way to re-run the calculator and propagate. (pricing team working session)
- Packaging breakdown (units per box/bottle) already exists in PMT but is not surfaced in the pricing calculator. (pricing team working session)
- Acquisition cost per SKU is already in the system; the calculator should auto-pull it rather than require keying. (pricing team working session)
- Parent-SKU inheritance pattern: when adding a new package size for an existing product, the manufacturer, strategy, and fee structure should carry over from the parent. (pricing team working session)
- The business model sells to practices at variable wholesale prices; practices sell to end clients. Fees must support both percentage-of-price and flat line-level structures. (pricing team working session)
- Line-level fee goal: one flat charge per dispensing event regardless of quantity (e.g., same $X fee whether a practice orders 1 pill or 100). (pricing team working session)
- VPD pricing stories were confirmed as the next sprint focus once future-dated pricing ships. (stakeholder alignment call)
- Pricing team "owns" company pricing and must not be blind to changes — all fee changes should be auditable. (stakeholder alignment call)

## 3. Users and Use Cases

**Primary user:** Pricing Analysts (Pricing Team Lead, Pricing Manager). They add VPD pricing for home delivery pharmacy SKUs when a new product is onboarded or when manufacturer prices change annually. They care about accuracy, speed, and not recalculating the same formula manually for every SKU.

**Secondary user:** Pricing Ops. They run periodic pricing validations and competitive reviews. They care about data consistency and having a clean audit record when something needs to be investigated.

**Explicit exclusions:**
- Practices — they receive wholesale prices, they do not set them
- End consumers — The company has no direct relationship with end clients
- Retail partner pricing teams (retail partner path) — they use a separate retail calculator; this PRD does not touch that flow

## 4. User Journey with Ins and Outs

**Screen 1 — SKU Catalog / Unpriced SKU List**
- Way in: Pricing analyst logs in and sees a queue of VPD SKUs with no fee set (or with stale hard-coded fees flagged after a manufacturer price update)
- Way out: Clicks "Set VPD Pricing" on a specific SKU row

**Screen 2 — SKU Detail + Packaging Confirmation**
- Way in: From catalog with SKU selected
- Shows: product name, NDC, manufacturer, units per package, acquisition cost (auto-populated from database), parent SKU link if it exists
- Way out: Confirms data is correct and clicks "Open Calculator," or edits packaging data if wrong

**Screen 3 — VPD Fee Calculator (AI-assisted)**
- Way in: From SKU detail after packaging confirmation
- System auto-populates: unit cost (acquisition cost ÷ units per package), vet list per unit, MAP per unit derived from parent SKU if available
- Analyst selects fee type (percentage or flat line-level) and enters fee value
- System previews resulting wholesale price at 1, 30, and 90 units in real time
- Flags anomalies inline (e.g., fee > 25% of unit cost, resulting price below acquisition cost)
- Way out: Clicks "Save Draft" or "Preview & Publish"

**Screen 4 — Fee Preview + Anomaly Review**
- Way in: From calculator after fee entry
- Shows: full price breakdown at 1 / 30 / 90 units, any anomaly flags with explanation, comparison to parent SKU price if available
- Way out: "Approve & Publish" or "Back to Edit"

**Screen 5 — Audit Confirmation**
- Way in: After publishing
- Shows: confirmation that fee is live, audit record summary (who set it, formula used, acquisition cost at time of publish, timestamp)
- Way out: Navigate to next unpriced SKU in queue or return to catalog

## 5. Goals and Non-Goals

**Goals:**
1. Reduce time to price a VPD SKU from ~15 minutes of manual calculation to under 2 minutes
2. Eliminate hard-coded fee entries — 100% of VPD fees stored as formulas, not static values, by end of rollout
3. Reduce VPD pricing errors reported by the pricing team by 50% within 60 days of launch
4. Support both fee types: percentage-of-price and flat line-level fee per dispensing event
5. Auto-populate acquisition cost and packaging units from existing PMT/easy catalog database for 90%+ of new VPD SKUs without manual entry

**Non-goals:**
- Does not replace the retail partner calculator (retail/wholesale partner path) — that flow uses different fee logic and is out of scope
- Does not manage manufacturer price change imports — the spreadsheet import process is a separate epic
- Does not set practice-level or end-consumer retail prices — the company sets wholesale; practices determine client pricing independently
- Does not include competitor price benchmarking in this scope — that is a separate AI competitor tracking feature

## 6. Functional Requirements

1. When a pricing analyst selects a SKU for VPD pricing, the system retrieves and displays the acquisition cost from the existing database without requiring manual entry.
2. The system calculates and displays unit cost = acquisition cost ÷ units per package, using the packaging breakdown already stored in PMT.
3. The system derives and displays MAP per unit = parent SKU MAP price ÷ parent package quantity, when a parent SKU MAP exists. If no parent MAP exists, the field displays as empty and is not required to proceed.
4. The system supports two fee types for VPD SKUs: (a) percentage of unit price and (b) flat line-level fee charged once per dispensing event regardless of quantity ordered.
5. When a fee type and value are entered, the system previews the resulting wholesale price at 1, 30, and 90 unit quantities in real time without requiring a page reload.
6. The system displays an inline warning before saving when: the fee percentage exceeds 25% of unit cost, or the resulting wholesale price per unit falls below acquisition cost per unit.
7. When a new SKU shares a manufacturer and product line with an existing priced SKU, the system pre-populates the fee type and fee percentage from the existing pattern; the analyst can override before saving.
8. Fee structures are stored as formulas (fee type + fee value), not hard-coded dollar amounts. When acquisition cost is updated via a manufacturer price import, the system recalculates affected VPD prices and surfaces them in a "Needs Review" queue for analyst approval before re-publishing.
9. The calculator supports a Save Draft state. A draft record is visible to the analyst in a separate "In Progress" queue and does not affect live pricing until published.
10. Every published VPD fee record stores: analyst who published it, fee formula used, acquisition cost at time of publish, previous fee value if one existed, and UTC timestamp.

## 7. Riskiest Assumption

My product only works if the system can consistently derive accurate per-unit MAP prices from parent SKU hierarchy data across all packaging configurations — including products where the parent-child SKU relationship is not yet explicitly mapped in the current database.

## 8. Eval Plan

The AI-assisted calculation layer is evaluated using four files in this folder:

- **rubric.json** — five criteria with weights: calculation_accuracy (Critical), hallucination (Critical), anomaly_detection (High), null_handling (High), output_format (Medium)
- **test-cases.json** — four test cases: easy (clean flat fee), realistic (percentage fee with parent MAP), hard (fee exceeds anomaly threshold), adversarial (missing fee value — must not fabricate)
- **thresholds.json** — ship/iterate/pivot decision rules tied to specific score thresholds per criterion
- **product-prompt.md** — the system prompt used by the VPD calculation assistant at runtime

Grading method: LLM-as-judge via `scripts/run-evals.py`.

## 9. Success Metrics and Open Questions

**Success Metrics:**
- 30 days: 90% of new VPD SKUs priced using the calculator with no manual override or hard-code workaround documented
- 60 days: Pricing team self-reports average time-to-price per VPD SKU under 2 minutes (baseline ~15 min per pricing team working session)
- 90 days: Zero VPD pricing errors attributed to stale hard-coded fees in post-launch audit (vs. TBD baseline from current error log)

**Open Questions:**
1. Does the parent SKU relationship currently exist as a queryable field in PMT, or does it need to be added as a new data model element before this calculator can work? (Engineering must answer before sprint planning.)
2. What is the agreed decimal precision standard for unit-cost calculations? A stakeholder alignment call raised that inconsistent decimal handling across systems causes rounding errors and mismatches with the ERP — this must be locked in before the formula is implemented.
3. Should fee recalculation on manufacturer price change be automatic (triggers on import completion) or manual-trigger (analyst sees a "Needs Review" queue and re-runs)? This affects the workflow design for Screen 3 and the audit trail.
4. Who has publish permission for a VPD fee change — analyst only, or does it require approval from the Pricing Manager before going live?

## 10. Design Reference and Prototype Fidelity

See `design-refs/README.md` for the full reference list and avoid-list.

**Reference products and what to borrow:**
- **Linear** — borrow the inline anomaly flag pattern: a subtle warning banner appears inside the form when a value is out of range, without blocking progress or using a modal
- **Height** — borrow the side-by-side calculator panel: input fields on the left, live preview of results on the right, updating in real time
- **Notion** — borrow the Save Draft / published state toggle: clear visual distinction between a draft record (gray chip) and a published record (green chip), visible in list views
- **Monday** — borrow the queue/board view for the unpriced SKU list: SKUs grouped by status (Needs Pricing, In Progress, Published, Needs Review), with counts per group

**Avoid:**
- No gradients
- No purple defaults (Shadcn default palette)
- No emoji empty states
- No shadcn default component styling without customization
- No Lorem ipsum in any UI state

**Seeded-data spec** (mirrors fixtures.md):
- SKU queue shows 6 SKUs: 2 in "Needs Pricing," 2 in "In Progress" (drafts), 1 in "Needs Review" (stale fee after manufacturer update), 1 "Published"
- Products drawn from research: Simparica Trio 5.6-11 lbs, Adequan Canine Injectable 100mg/mL, Carprofen 75mg Chewable 30ct, Atenolol 25mg 30ct, Metronidazole 250mg 60ct, Advantage II for Dogs 3-10 lbs
- Owners: fictional pricing analysts (A. Rivera, D. Chen) shown in audit records

**UI-state rules:**
- No loading skeletons — calculator screen always shows seeded data on load
- No empty states — every screen must show the seeded SKU data by default
- One-click login — no auth form in the prototype
