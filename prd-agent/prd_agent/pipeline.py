"""Notes -> PRD draft -> critique -> revised PRD."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from . import prompts
from .llm import complete

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Result:
    draft: str
    critique: dict
    final: str | None = None
    files: list[Path] = field(default_factory=list)


def load_sources(paths: list[Path]) -> str:
    """Read note files and label each one so the PRD can cite it."""
    if not paths:
        raise ValueError("Give at least one notes file.")
    parts = []
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"{path} is empty.")
        parts.append(f'<source label="{path.name}">\n{text}\n</source>')
    return "\n\n".join(parts)


def draft_prd(client: anthropic.Anthropic, sources: str, title: str | None, effort: str) -> str:
    ask = "Write the PRD from these sources."
    if title:
        ask += f" The feature is: {title}."
    return complete(client, system=prompts.DRAFT_SYSTEM, user=f"{sources}\n\n{ask}", effort=effort)


def critique_prd(client: anthropic.Anthropic, sources: str, draft: str, effort: str) -> dict:
    user = f"{sources}\n\n<prd_draft>\n{draft}\n</prd_draft>\n\nReview this PRD against the sources."
    raw = complete(
        client,
        system=prompts.CRITIQUE_SYSTEM,
        user=user,
        effort=effort,
        output_format={"type": "json_schema", "schema": prompts.CRITIQUE_SCHEMA},
    )
    critique = json.loads(raw)
    critique["findings"].sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 99))
    return critique


def revise_prd(client: anthropic.Anthropic, sources: str, draft: str, critique: dict, effort: str) -> str:
    user = (
        f"{sources}\n\n<prd_draft>\n{draft}\n</prd_draft>\n\n"
        f"<review_findings>\n{json.dumps(critique['findings'], indent=2)}\n</review_findings>\n\n"
        "Revise the PRD."
    )
    return complete(client, system=prompts.REVISE_SYSTEM, user=user, effort=effort)


def render_critique(critique: dict) -> str:
    """Turn the structured critique into a readable Markdown review."""
    lines = ["# PRD Review", "", critique["summary"], "", "## Scores (1-5)", ""]
    lines += ["| Dimension | Score |", "|---|---|"]
    for name, score in critique["scores"].items():
        lines.append(f"| {name.replace('_', ' ').capitalize()} | {score} |")

    findings = critique["findings"]
    lines += ["", f"## Findings ({len(findings)})", ""]
    if not findings:
        lines.append("No findings.")
    for i, f in enumerate(findings, 1):
        lines.append(f"### {i}. [{f['severity'].upper()}] {f['section']}")
        if f["quote"]:
            lines.append(f"> {f['quote']}")
            lines.append("")
        lines.append(f"**Issue:** {f['issue']}")
        lines.append("")
        lines.append(f"**Fix:** {f['fix']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(
    client: anthropic.Anthropic,
    note_paths: list[Path],
    out_dir: Path,
    *,
    title: str | None = None,
    revise: bool = True,
    effort: str = "high",
    log=print,
) -> Result:
    sources = load_sources(note_paths)
    out_dir.mkdir(parents=True, exist_ok=True)

    log("1/3 Drafting PRD...")
    draft = draft_prd(client, sources, title, effort)
    result = Result(draft=draft, critique={})
    result.files.append(_write(out_dir / "1-prd-draft.md", draft))

    log("2/3 Reviewing draft...")
    result.critique = critique_prd(client, sources, draft, effort)
    result.files.append(_write(out_dir / "2-review.json", json.dumps(result.critique, indent=2) + "\n"))
    result.files.append(_write(out_dir / "2-review.md", render_critique(result.critique)))

    if revise:
        log("3/3 Revising PRD with review findings...")
        result.final = revise_prd(client, sources, draft, result.critique, effort)
        result.files.append(_write(out_dir / "3-prd-final.md", result.final))
    return result


def _write(path: Path, text: str) -> Path:
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return path
