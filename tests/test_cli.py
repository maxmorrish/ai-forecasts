from datetime import date, timedelta
from pathlib import Path

import pytest

from ai_forecasts.cli import main
from ai_forecasts.model import load_forecast


def test_add_update_resolve_lifecycle(tmp_path: Path) -> None:
    forecast_id = "test-lifecycle"
    assert main([
        "--data-dir", str(tmp_path), "add", "--id", forecast_id,
        "--claim", "A test release will happen by the deadline.",
        "--criteria", "Resolves yes if the official release page publishes version 1.0 by the deadline.",
        "--resolve-by", (date.today() + timedelta(days=5)).isoformat(),
        "--probability", "0.4", "--category", "tooling",
        "--evidence", "https://example.com/roadmap",
    ]) == 0
    assert main(["--data-dir", str(tmp_path), "update", forecast_id, "--probability", "0.6", "--reason", "A release candidate appeared."]) == 0
    assert main(["--data-dir", str(tmp_path), "resolve", forecast_id, "--outcome", "yes", "--source-url", "https://example.com/release"]) == 0
    forecast = load_forecast(tmp_path / f"{forecast_id}.yaml")
    assert forecast["updates"][-1]["probability"] == 0.6
    assert forecast["resolution"]["outcome"] == "yes"


def test_due_list_filters_window(tmp_path: Path, capsys) -> None:
    for forecast_id, days in (("soon", 3), ("later", 20)):
        main([
            "--data-dir", str(tmp_path), "add", "--id", forecast_id,
            "--claim", f"The {forecast_id} test event will happen.",
            "--criteria", "Resolves yes if the official source records the event before the deadline.",
            "--resolve-by", (date.today() + timedelta(days=days)).isoformat(),
            "--probability", "0.5", "--category", "other",
        ])
    capsys.readouterr()
    main(["--data-dir", str(tmp_path), "list", "--due", "7"])
    output = capsys.readouterr().out
    assert "soon" in output
    assert "later" not in output


def test_report_from_examples(tmp_path: Path) -> None:
    examples = Path(__file__).parents[1] / "examples"
    assert main(["--data-dir", str(examples), "report", "--output", str(tmp_path)]) == 0
    html = (tmp_path / "index.html").read_text()
    markdown = (tmp_path / "index.md").read_text()
    assert "Open forecasts" in html
    assert "Resolved forecasts" in markdown
    assert "Brier score" in html


def test_add_rejects_certainty(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main([
            "--data-dir", str(tmp_path), "add", "--id", "certain",
            "--claim", "A test event will happen.",
            "--criteria", "Resolves yes if the official source records the event before the deadline.",
            "--resolve-by", (date.today() + timedelta(days=1)).isoformat(),
            "--probability", "1", "--category", "other",
        ])
    assert exc.value.code == 2

