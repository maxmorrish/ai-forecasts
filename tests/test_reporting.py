from pathlib import Path

from ai_forecasts.model import load_forecasts
from ai_forecasts.reporting import render_html, render_markdown


def test_reports_escape_html_and_include_sections() -> None:
    forecasts = load_forecasts(Path(__file__).parents[1] / "examples")
    forecasts[0]["claim"] = "A <script>alert(1)</script> claim."
    html = render_html(forecasts)
    markdown = render_markdown(forecasts)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "## Score" in markdown

