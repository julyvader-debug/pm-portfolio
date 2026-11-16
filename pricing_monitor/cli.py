"""
CLI entry point: python -m pricing_monitor <command> [options]

Commands:
  run      Execute a full pricing run (scrape → extract → analyze → report)
  report   Print the markdown report for a given run date
  export   Copy the CSV for a given run date to a destination path
  cleanup  Delete screenshots/extractions older than N weeks (keeps pricing.db)
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import logger as log_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_DATA_DIR = Path("data")


def _run_dir(data_dir: Path, run_date: str) -> Path:
    return data_dir / "runs" / run_date


def _available_run_dates(data_dir: Path) -> list[str]:
    runs = data_dir / "runs"
    if not runs.exists():
        return []
    return sorted(
        (d.name for d in runs.iterdir() if d.is_dir()),
        reverse=True,
    )


def _cutoff_date(weeks: int) -> date:
    return date.today() - timedelta(weeks=weeks)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    log_module.configure(args.log_level)
    from scheduler.runner import run

    run_date = args.date or date.today().isoformat()
    data_dir = Path(args.data_dir)

    print(f"Starting pricing run for {run_date} …")
    try:
        report = asyncio.run(
            run(
                run_date=run_date,
                data_dir=data_dir,
            )
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Done. {report.success_count} extracted, "
        f"{report.failure_count} failed. "
        f"Report: {_run_dir(data_dir, run_date) / 'report.md'}"
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)

    if args.date:
        run_date = args.date
    else:
        dates = _available_run_dates(data_dir)
        if not dates:
            print("No runs found.", file=sys.stderr)
            return 1
        run_date = dates[0]

    report_path = _run_dir(data_dir, run_date) / "report.md"
    if not report_path.exists():
        print(f"No report found for {run_date}: {report_path}", file=sys.stderr)
        return 1

    print(report_path.read_text(encoding="utf-8"))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)

    if args.date:
        run_date = args.date
    else:
        dates = _available_run_dates(data_dir)
        if not dates:
            print("No runs found.", file=sys.stderr)
            return 1
        run_date = dates[0]

    csv_path = _run_dir(data_dir, run_date) / "report.csv"
    if not csv_path.exists():
        print(f"No CSV found for {run_date}: {csv_path}", file=sys.stderr)
        return 1

    if args.output:
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(csv_path, dest)
        print(f"Exported to {dest}")
    else:
        print(csv_path.read_text(encoding="utf-8"))

    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    cutoff = _cutoff_date(args.weeks)
    runs_dir = data_dir / "runs"

    if not runs_dir.exists():
        print("No runs directory found — nothing to clean.")
        return 0

    removed: list[str] = []
    for run_path in sorted(runs_dir.iterdir()):
        if not run_path.is_dir():
            continue
        try:
            run_date = date.fromisoformat(run_path.name)
        except ValueError:
            continue  # skip non-date directories

        if run_date >= cutoff:
            continue

        for subdir in ("screenshots", "extractions"):
            target = run_path / subdir
            if target.exists():
                shutil.rmtree(target)
                removed.append(str(target))

    if removed:
        print(f"Cleaned {len(removed)} director{'y' if len(removed) == 1 else 'ies'}:")
        for p in removed:
            print(f"  {p}")
    else:
        print(f"Nothing to clean (cutoff: {cutoff.isoformat()}).")

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pricing_monitor",
        description="Competitor pricing monitor for veterinary e-commerce",
    )
    parser.add_argument(
        "--data-dir",
        default=str(_DEFAULT_DATA_DIR),
        help="Root data directory (default: data/)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Execute a full pricing run")
    p_run.add_argument("--date", help="Run date as YYYY-MM-DD (default: today)")

    # report
    p_report = sub.add_parser("report", help="Print the markdown report for a run date")
    p_report.add_argument("--date", help="Run date (default: most recent)")

    # export
    p_export = sub.add_parser("export", help="Export the CSV for a run date")
    p_export.add_argument("--date", help="Run date (default: most recent)")
    p_export.add_argument("--output", "-o", help="Destination file path (default: stdout)")

    # cleanup
    p_cleanup = sub.add_parser(
        "cleanup",
        help="Delete screenshots/extractions older than N weeks",
    )
    p_cleanup.add_argument(
        "--weeks",
        type=int,
        default=12,
        help="Delete subdirs from runs older than this many weeks (default: 12)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "run": cmd_run,
        "report": cmd_report,
        "export": cmd_export,
        "cleanup": cmd_cleanup,
    }
    return handlers[args.command](args)


