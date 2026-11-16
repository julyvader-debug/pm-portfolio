# AI Eval Suites

LLM-as-judge evals for two AI features in the Pricing Management Tool.

| Suite | Feature under test |
|---|---|
| [`pmt-pricing-assistant/`](pmt-pricing-assistant/) | Calculates the recommended sell price and margin for a Sales pricing request, and flags risks for the Pricing reviewer |
| [`vpd-fee-calculator/`](vpd-fee-calculator/) | Calculates per-dose (VPD) wholesale price and fee for home-delivery SKUs, and flags anomalies |

Each folder contains the prompt under test, a weighted rubric, test cases, and ship / iterate / pivot thresholds.

## Running

```bash
cd ai-evals
python run-evals.py --test-cases pmt-pricing-assistant/test-cases.json
python run-evals.py --test-cases vpd-fee-calculator/test-cases.json
```

Requires [Claude Code](https://claude.com/claude-code) on your PATH. The harness calls `claude -p` for both the feature output and the judge score, then writes `results.json` and `results.md` next to the test cases.

## Credit

`run-evals.py` is the reference harness from the *Claude Code for PMs* course. The prompts, rubrics, test cases, and thresholds in the two suite folders are my own work.
