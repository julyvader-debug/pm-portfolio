"""Unit tests with a fake Claude client. No API key or network needed."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from prd_agent import cli, pipeline
from prd_agent.llm import MODEL, LLMError, complete

CRITIQUE = {
    "summary": "Close, but P0 has no acceptance criteria for the margin block.",
    "scores": {
        "grounded_in_sources": 4,
        "testable_requirements": 3,
        "edge_case_coverage": 2,
        "clear_scope": 4,
        "measurable_success": 2,
    },
    "findings": [
        {"severity": "low", "section": "8", "quote": "", "issue": "No baseline.", "fix": "Add one."},
        {
            "severity": "critical",
            "section": "5",
            "quote": "Block promos below 15% margin",
            "issue": "15% is not in the notes.",
            "fix": "Move the floor value to Open Questions.",
        },
    ],
}


def message(text: str, stop_reason: str = "end_turn", **extra):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        **extra,
    )


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """Returns queued messages in order and records each request."""

    def __init__(self, *messages):
        self.queue = list(messages)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.queue.pop(0))


@pytest.fixture
def notes(tmp_path: Path) -> list[Path]:
    a = tmp_path / "kickoff.md"
    a.write_text("Promos stack and go below cost.", encoding="utf-8")
    b = tmp_path / "slack.md"
    b.write_text("Floors should block for RX.", encoding="utf-8")
    return [a, b]


# --- load_sources ---------------------------------------------------------


def test_load_sources_labels_each_file(notes):
    text = pipeline.load_sources(notes)
    assert '<source label="kickoff.md">' in text
    assert '<source label="slack.md">' in text
    assert "Floors should block for RX." in text


def test_load_sources_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        pipeline.load_sources([empty])


def test_load_sources_requires_input():
    with pytest.raises(ValueError):
        pipeline.load_sources([])


# --- llm.complete -----------------------------------------------------------


def test_complete_sends_model_effort_and_fallback():
    client = FakeClient(message("ok"))
    assert complete(client, system="s", user="u", effort="medium") == "ok"
    call = client.calls[0]
    assert call["model"] == MODEL
    assert call["output_config"] == {"effort": "medium"}
    assert call["extra_body"] == {"fallbacks": "default"}
    assert "thinking" not in call  # adaptive by default on this model


def test_complete_raises_on_refusal():
    refusal = message("", stop_reason="refusal", stop_details=SimpleNamespace(explanation="policy"))
    with pytest.raises(LLMError, match="policy"):
        complete(FakeClient(refusal), system="s", user="u")


def test_complete_raises_on_truncation():
    with pytest.raises(LLMError, match="cut off"):
        complete(FakeClient(message("partial", stop_reason="max_tokens")), system="s", user="u")


def test_complete_raises_on_empty_text():
    with pytest.raises(LLMError, match="empty"):
        complete(FakeClient(message("  ")), system="s", user="u")


# --- pipeline.run -----------------------------------------------------------


def test_run_draft_critique_revise(notes, tmp_path):
    client = FakeClient(message("# Draft PRD"), message(json.dumps(CRITIQUE)), message("# Final PRD"))
    out = tmp_path / "out"

    result = pipeline.run(client, notes, out, title="Promo stacking", log=lambda _: None)

    assert len(client.calls) == 3
    assert "Promo stacking" in client.calls[0]["messages"][0]["content"]
    # The critique pass asks for structured JSON output.
    assert client.calls[1]["output_config"]["format"]["type"] == "json_schema"
    # The revise pass gets the findings.
    assert "15% is not in the notes." in client.calls[2]["messages"][0]["content"]

    assert result.final == "# Final PRD"
    assert [p.name for p in result.files] == ["1-prd-draft.md", "2-review.json", "2-review.md", "3-prd-final.md"]
    assert (out / "3-prd-final.md").read_text(encoding="utf-8") == "# Final PRD\n"


def test_run_sorts_findings_by_severity(notes, tmp_path):
    client = FakeClient(message("# Draft"), message(json.dumps(CRITIQUE)))
    result = pipeline.run(client, notes, tmp_path, revise=False, log=lambda _: None)
    assert [f["severity"] for f in result.critique["findings"]] == ["critical", "low"]


def test_run_no_revise_skips_third_call(notes, tmp_path):
    client = FakeClient(message("# Draft"), message(json.dumps(CRITIQUE)))
    result = pipeline.run(client, notes, tmp_path, revise=False, log=lambda _: None)
    assert len(client.calls) == 2
    assert result.final is None
    assert not (tmp_path / "3-prd-final.md").exists()


# --- render_critique --------------------------------------------------------


def test_render_critique_markdown():
    crit = json.loads(json.dumps(CRITIQUE))
    md = pipeline.render_critique(crit)
    assert "| Grounded in sources | 4 |" in md
    assert "[CRITICAL] 5" in md
    assert "> Block promos below 15% margin" in md
    assert "## Findings (2)" in md


def test_render_critique_no_findings():
    crit = dict(CRITIQUE, findings=[])
    assert "No findings." in pipeline.render_critique(crit)


# --- cli --------------------------------------------------------------------


def test_cli_missing_file_returns_2(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.md")]) == 2
    assert "File not found" in capsys.readouterr().err


def test_cli_end_to_end_with_fake_client(notes, tmp_path, monkeypatch, capsys):
    client = FakeClient(message("# Draft"), message(json.dumps(CRITIQUE)), message("# Final"))
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda: client)
    code = cli.main([*map(str, notes), "--out", str(tmp_path / "o"), "--effort", "low"])
    assert code == 0
    assert client.calls[0]["output_config"]["effort"] == "low"
    out = capsys.readouterr().out
    assert "1 critical, 1 low" in out
    assert "3-prd-final.md" in out


def test_cli_reports_model_error(notes, tmp_path, monkeypatch, capsys):
    client = FakeClient(message("", stop_reason="refusal", stop_details=None))
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda: client)
    assert cli.main([*map(str, notes), "--out", str(tmp_path)]) == 1
    assert "Model error" in capsys.readouterr().err
