# Product Management Portfolio: Pricing Systems for Veterinary E-commerce

**Monic** · Senior Technical Product Manager · 25 years in IT (e-commerce pricing, telecom billing)

This repo shows how I work as a technical PM. It covers three things: PRDs that engineers can build from, eval frameworks that decide when an AI feature is ready to ship, and a working prototype I built to test a product hypothesis.

All work comes from a consulting engagement with a veterinary pharmacy e-commerce company. Company names, people, internal system names, and data have been removed or replaced with placeholders. Prices and SKUs are illustrative.

---

## The problem

The pricing team managed wholesale prices for thousands of pharmacy and nutrition SKUs through a tool that depended on spreadsheets:

- New SKUs had to be imported by hand, and only the last 2 prices per SKU were kept
- Per-pill (VPD) home-delivery fees were hard-coded, so every manufacturer cost change meant re-entering values by hand
- Sales submitted pricing requests outside the tool, and Pricing rebuilt the context from scratch
- There was no audit trail of who approved what, or when

The result was slow turnaround, rounding and margin errors, and low trust in the published price.

## What's here

| Folder | What it is | What it shows |
|---|---|---|
| [`prds/`](prds/) | PRD for the new Pricing Management Tool (v3) and a scoped PRD for the VPD Fee Calculator | Turning interviews and technical sessions into P0/P1/P2 scope, user journeys, acceptance criteria, risks, and open questions |
| [`ai-evals/`](ai-evals/) | LLM-as-judge eval suites for two AI pricing features | Defining "good enough to ship" for AI: weighted rubrics, adversarial test cases, ship/iterate/pivot thresholds |
| [`pricing_monitor/`](pricing_monitor/) | Working Python app that tracks competitor prices with Claude | Validating a feature idea with a real prototype before asking engineering to build it |

---

## 1. PRDs

**[Pricing Management Tool: PRD v3](prds/pmt-v3-pricing-management-tool.txt)**
Replaces the spreadsheet-driven workflow with one governed path from Sales intake to published price. The PRD is organized in three layers:
1. **Data:** pull SKUs directly from the source catalog; no replicated tables
2. **Workflow:** structured intake with validation gates, sandbox margin check, approval with required reasons, and an append-only audit log
3. **Fees:** a modular fee engine (stackable formula "tiles") replaces hard-coded overrides; line-level fees for per-pill pricing; future-dated pricing

Includes 10 user stories with acceptance criteria, testing requirements, success metrics with targets, a risk register, and a list of explicit open questions for engineering.

**[VPD Fee Calculator PRD](prds/vpd-fee-calculator/vpd-fee-calculator-prd.md)**
A smaller, buildable slice: auto-calculate per-dose pricing for home-delivery SKUs. Each research finding is traced to its source, and the PRD names the riskiest assumption explicitly: that per-unit MAP can be derived from the parent-SKU hierarchy. The goal is to cut time to price a SKU from about 15 minutes to under 2.

## 2. AI eval framework

Before an AI feature ships, I define what failure looks like and test for it. Each suite contains:

- **`product-prompt.md`**: the prompt under test
- **`rubric.json`**: weighted criteria (Critical / High / Medium), with explicit 1/5 and 5/5 definitions
- **`test-cases.json`**: easy, realistic, hard, and adversarial inputs
- **`thresholds.json`**: written ship / iterate / pivot rules, agreed before any results come in

| Suite | Cases | What the adversarial cases check |
|---|---|---|
| [PMT pricing assistant](ai-evals/pmt-pricing-assistant/) | 10 | Zero and negative cost; target margin missing; corporate override below cost; a promo discount that wipes out margin; VPD request missing package size, where the AI must not assume a default |
| [VPD fee calculator](ai-evals/vpd-fee-calculator/) | 4 | Fee above the anomaly threshold; fee value missing, where the AI must not make one up but still calculate the fields it can |

The rule I hold to: **in pricing, a confident wrong number is worse than no number.** Hallucination is weighted Critical in both suites, and the pivot rule applies if the model keeps guessing missing inputs instead of refusing to calculate.

## 3. Competitor pricing monitor (working prototype)

**Hypothesis:** the company loses clinic orders to large online competitors. The cause is not price, since its contracted prices are often lower. The cause is that clinics don't see those prices at the point of ordering. To test that, we first need reliable competitor price data.

**What I built:** a Python pipeline that runs weekly:

```
Playwright screenshots → Claude Haiku extracts prices (vision) → SQLite history
        → Claude Sonnet writes trend analysis → Markdown report + CSV + HTML dashboard
```

- Typed config for competitors and products; rate limiting; concurrency caps for the browser and the API
- Cheap model for high-volume extraction, stronger model for reasoning over 8 weeks of history
- Expected-price-range sanity checks to catch extraction errors
- **195 automated unit and integration tests**, run in CI

See [`pricing_monitor/README.md`](pricing_monitor/README.md) for setup.

---

## How I work

- **Start from the user's real workflow.** Every requirement in these PRDs traces back to an interview or a working session with the people doing the job.
- **Name the riskiest assumption first,** and test it before committing engineering time.
- **Write for the reader.** Engineers get edge cases and acceptance criteria; leadership gets the business problem and the metric that will move.
- **Prototype with AI tools** (Claude Code, the Claude API) to shorten the time between idea and evidence.
