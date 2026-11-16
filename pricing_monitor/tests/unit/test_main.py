"""
Unit tests for __main__.py.

Tests cover: argument parsing, cleanup logic, report/export file handling.
The `run` command is not tested here — it's covered by test_runner.py.
"""
import shutil
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from cli import (
    build_parser,
    cmd_cleanup,
    cmd_report,
    cmd_export,
    _available_run_dates,
    _cutoff_date,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(data_dir: Path, run_date: str, with_report=True, with_csv=True) -> Path:
    run_dir = data_dir / "runs" / run_date
    (run_dir / "screenshots").mkdir(parents=True)
    (run_dir / "extractions").mkdir(parents=True)
    if with_report:
        (run_dir / "report.md").write_text(f"# Report {run_date}", encoding="utf-8")
    if with_csv:
        (run_dir / "report.csv").write_text("run_date,competitor_slug\n", encoding="utf-8")
    return run_dir


def _args(data_dir: Path, **kwargs):
    """Build a minimal namespace for command handlers."""
    import argparse
    ns = argparse.Namespace(data_dir=str(data_dir), log_level="INFO", **kwargs)
    return ns


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_run_command_parsed(self):
        args = build_parser().parse_args(["run"])
        assert args.command == "run"
        assert args.date is None

    def test_run_with_date(self):
        args = build_parser().parse_args(["run", "--date", "2026-04-14"])
        assert args.date == "2026-04-14"

    def test_report_command_parsed(self):
        args = build_parser().parse_args(["report"])
        assert args.command == "report"

    def test_export_with_output(self):
        args = build_parser().parse_args(["export", "--output", "/tmp/out.csv"])
        assert args.output == "/tmp/out.csv"

    def test_cleanup_default_weeks(self):
        args = build_parser().parse_args(["cleanup"])
        assert args.weeks == 12

    def test_cleanup_custom_weeks(self):
        args = build_parser().parse_args(["cleanup", "--weeks", "4"])
        assert args.weeks == 4

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_data_dir_default(self):
        args = build_parser().parse_args(["run"])
        assert args.data_dir == "data"

    def test_data_dir_override(self):
        args = build_parser().parse_args(["--data-dir", "/custom/path", "run"])
        assert args.data_dir == "/custom/path"


# ---------------------------------------------------------------------------
# _available_run_dates / _cutoff_date helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_available_run_dates_sorted_newest_first(self, tmp_path):
        for d in ["2026-03-01", "2026-04-14", "2026-04-07"]:
            (tmp_path / "runs" / d).mkdir(parents=True)
        result = _available_run_dates(tmp_path)
        assert result == ["2026-04-14", "2026-04-07", "2026-03-01"]

    def test_available_run_dates_empty_when_no_runs(self, tmp_path):
        assert _available_run_dates(tmp_path) == []

    def test_available_run_dates_missing_dir(self, tmp_path):
        assert _available_run_dates(tmp_path / "nonexistent") == []

    def test_cutoff_date_is_n_weeks_ago(self):
        n = 12
        expected = date.today() - timedelta(weeks=n)
        assert _cutoff_date(n) == expected


# ---------------------------------------------------------------------------
# cmd_cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_removes_screenshots_older_than_cutoff(self, tmp_path):
        old_date = (date.today() - timedelta(weeks=13)).isoformat()
        run_dir = _make_run(tmp_path, old_date)

        rc = cmd_cleanup(_args(tmp_path, weeks=12))

        assert rc == 0
        assert not (run_dir / "screenshots").exists()
        assert not (run_dir / "extractions").exists()

    def test_keeps_report_files_after_cleanup(self, tmp_path):
        old_date = (date.today() - timedelta(weeks=13)).isoformat()
        run_dir = _make_run(tmp_path, old_date)

        cmd_cleanup(_args(tmp_path, weeks=12))

        assert (run_dir / "report.md").exists()
        assert (run_dir / "report.csv").exists()

    def test_preserves_recent_runs(self, tmp_path):
        recent_date = (date.today() - timedelta(weeks=2)).isoformat()
        run_dir = _make_run(tmp_path, recent_date)

        cmd_cleanup(_args(tmp_path, weeks=12))

        assert (run_dir / "screenshots").exists()
        assert (run_dir / "extractions").exists()

    def test_only_old_runs_cleaned(self, tmp_path):
        old_date = (date.today() - timedelta(weeks=14)).isoformat()
        new_date = (date.today() - timedelta(weeks=2)).isoformat()
        old_run = _make_run(tmp_path, old_date)
        new_run = _make_run(tmp_path, new_date)

        cmd_cleanup(_args(tmp_path, weeks=12))

        assert not (old_run / "screenshots").exists()
        assert (new_run / "screenshots").exists()

    def test_no_runs_dir_exits_cleanly(self, tmp_path):
        rc = cmd_cleanup(_args(tmp_path, weeks=12))
        assert rc == 0

    def test_non_date_dirs_skipped(self, tmp_path):
        # A directory that isn't a YYYY-MM-DD date should not be touched
        weird_dir = tmp_path / "runs" / "not-a-date"
        (weird_dir / "screenshots").mkdir(parents=True)

        rc = cmd_cleanup(_args(tmp_path, weeks=12))

        assert rc == 0
        assert (weird_dir / "screenshots").exists()

    def test_already_cleaned_run_no_error(self, tmp_path):
        old_date = (date.today() - timedelta(weeks=13)).isoformat()
        run_dir = _make_run(tmp_path, old_date)
        shutil.rmtree(run_dir / "screenshots")  # already gone

        rc = cmd_cleanup(_args(tmp_path, weeks=12))
        assert rc == 0


# ---------------------------------------------------------------------------
# cmd_report
# ---------------------------------------------------------------------------

class TestReport:
    def test_prints_report_for_given_date(self, tmp_path, capsys):
        _make_run(tmp_path, "2026-04-14")
        rc = cmd_report(_args(tmp_path, date="2026-04-14"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Report 2026-04-14" in out

    def test_uses_most_recent_when_no_date(self, tmp_path, capsys):
        _make_run(tmp_path, "2026-04-07")
        _make_run(tmp_path, "2026-04-14")
        rc = cmd_report(_args(tmp_path, date=None))
        assert rc == 0
        out = capsys.readouterr().out
        assert "2026-04-14" in out

    def test_missing_report_returns_error(self, tmp_path):
        rc = cmd_report(_args(tmp_path, date="2026-04-14"))
        assert rc == 1

    def test_no_runs_returns_error(self, tmp_path):
        rc = cmd_report(_args(tmp_path, date=None))
        assert rc == 1


# ---------------------------------------------------------------------------
# cmd_export
# ---------------------------------------------------------------------------

class TestExport:
    def test_prints_csv_to_stdout(self, tmp_path, capsys):
        _make_run(tmp_path, "2026-04-14")
        rc = cmd_export(_args(tmp_path, date="2026-04-14", output=None))
        assert rc == 0
        out = capsys.readouterr().out
        assert "run_date" in out

    def test_copies_csv_to_output_path(self, tmp_path):
        _make_run(tmp_path, "2026-04-14")
        dest = tmp_path / "exports" / "out.csv"
        rc = cmd_export(_args(tmp_path, date="2026-04-14", output=str(dest)))
        assert rc == 0
        assert dest.exists()

    def test_creates_output_parent_dirs(self, tmp_path):
        _make_run(tmp_path, "2026-04-14")
        dest = tmp_path / "deep" / "nested" / "out.csv"
        cmd_export(_args(tmp_path, date="2026-04-14", output=str(dest)))
        assert dest.exists()

    def test_uses_most_recent_when_no_date(self, tmp_path, capsys):
        _make_run(tmp_path, "2026-04-07")
        _make_run(tmp_path, "2026-04-14")
        rc = cmd_export(_args(tmp_path, date=None, output=None))
        assert rc == 0

    def test_missing_csv_returns_error(self, tmp_path):
        _make_run(tmp_path, "2026-04-14", with_csv=False)
        rc = cmd_export(_args(tmp_path, date="2026-04-14", output=None))
        assert rc == 1

    def test_no_runs_returns_error(self, tmp_path):
        rc = cmd_export(_args(tmp_path, date=None, output=None))
        assert rc == 1


# ---------------------------------------------------------------------------
# main() integration
# ---------------------------------------------------------------------------

class TestMain:
    def test_report_via_main(self, tmp_path, capsys):
        _make_run(tmp_path, "2026-04-14")
        rc = main(["--data-dir", str(tmp_path), "report", "--date", "2026-04-14"])
        assert rc == 0

    def test_cleanup_via_main(self, tmp_path):
        rc = main(["--data-dir", str(tmp_path), "cleanup", "--weeks", "12"])
        assert rc == 0

    def test_export_via_main(self, tmp_path, capsys):
        _make_run(tmp_path, "2026-04-14")
        rc = main(["--data-dir", str(tmp_path), "export", "--date", "2026-04-14"])
        assert rc == 0
