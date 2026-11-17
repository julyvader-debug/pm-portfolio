# PRD Agent: notes in, reviewed PRD out

Discovery leaves me with a pile of meeting notes, call transcripts, and Slack threads. Turning that into a PRD engineers can build from takes hours, and the first draft always has gaps that someone finds in sprint planning.

This tool runs three passes with Claude:

```
notes / transcripts ──► 1. Draft PRD ──► 2. Review ──► 3. Revised PRD
                         (template,       (structured     (applies findings;
                          cites sources)   findings +      gaps go to
                                           scores)         Open Questions)
```

1. **Draft:** writes the PRD in a fixed template (problem, research with sources, users, journey, P0/P1/P2, acceptance criteria, edge cases, metrics, riskiest assumption, open questions).
2. **Review:** a second pass acts as a skeptical principal engineer. It returns JSON: a 1-5 score on five dimensions and findings with severity, the quoted text, the issue, and the fix.
3. **Revise:** applies every finding the notes support. If a finding asks for something the notes don't contain, it goes to Open Questions instead of being made up.

## The design choice that matters

**The agent may not invent facts.** In a PRD, a confident wrong requirement is worse than an open question: engineers build it. So:

- Every research bullet cites its source file.
- Gaps become Open Questions, never assumptions.
- The reviewer flags any claim not found in the notes as **critical**.
- The revise pass is told to move, not fill, unsupported gaps.

The review is a separate pass with its own instructions, so the reviewer doesn't share the drafter's blind spots.

## Run it

```bash
cd prd-agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # or: ant auth login

python -m prd_agent examples/kickoff-notes.md examples/followup-slack.md \
    --title "Promo stacking rules" --out output/promo-stacking
```

Output:

| File | What it is |
|---|---|
| `1-prd-draft.md` | First draft |
| `2-review.md` | Scores and findings, sorted by severity |
| `2-review.json` | The same review as structured data |
| `3-prd-final.md` | Revised PRD |

Options: `--no-revise` stops after the review; `--effort low|medium|high|xhigh|max` trades depth for speed and cost (default `high`).

The files in [`examples/`](examples/) are fictional notes. They are written to include the gaps a real kickoff leaves, such as margin floor values nobody stated and a promos table with no channel field, so you can see whether the agent asks about them or invents them.

## Implementation notes

- Model: `claude-opus-5-5` with adaptive thinking, streamed to avoid timeouts on long PRDs.
- The review uses structured outputs (JSON schema), so findings can be counted, sorted, and later checked against an eval suite like the ones in [`ai-evals/`](../ai-evals/).
- Server-side refusal fallback is enabled. Refusals and truncated output raise a clear error instead of writing a partial PRD.
- 15 unit tests run against a fake client, with no API key or network: `python -m pytest -q`.
