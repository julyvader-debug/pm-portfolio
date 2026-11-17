"""Command line entry point: python -m prd_agent notes.md [more.md ...]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic

from .llm import LLMError
from .pipeline import run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prd_agent",
        description="Turn meeting notes and transcripts into a reviewed PRD.",
    )
    p.add_argument("notes", nargs="+", type=Path, help="Notes or transcript files (.md / .txt)")
    p.add_argument("-o", "--out", type=Path, default=Path("output"), help="Output folder (default: output/)")
    p.add_argument("-t", "--title", help="Feature name, if the notes do not make it obvious")
    p.add_argument("--no-revise", action="store_true", help="Stop after the review; skip the revised PRD")
    p.add_argument(
        "--effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        default="high",
        help="How hard the model thinks on each pass (default: high)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    missing = [str(p) for p in args.notes if not p.is_file()]
    if missing:
        print(f"File not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    try:
        result = run(
            client,
            args.notes,
            args.out,
            title=args.title,
            revise=not args.no_revise,
            effort=args.effort,
        )
    except ValueError as e:
        print(f"Input error: {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"Model error: {e}", file=sys.stderr)
        return 1
    except anthropic.AuthenticationError:
        print("Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
        return 1
    except anthropic.RateLimitError:
        print("Rate limited by the API. Wait a minute and try again.", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("Could not reach the API. Check your network connection.", file=sys.stderr)
        return 1

    crit = result.critique
    counts = {}
    for f in crit["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    summary = ", ".join(f"{n} {s}" for s, n in counts.items()) or "none"
    print(f"\nReview findings: {summary}")
    print("Wrote:")
    for path in result.files:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
