from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from .model import current_probability
from .scoring import score_forecasts


def _score_summary(score: dict[str, Any]) -> str:
    if score["overall_brier"] is None:
        return "No unambiguous resolutions yet."
    return f"Brier score {score['overall_brier']:.4f} across {score['count']} resolved forecasts. Lower is better."


def render_markdown(forecasts: list[dict[str, Any]]) -> str:
    open_items = sorted((item for item in forecasts if item["resolution"] is None), key=lambda item: item["resolve_by"])
    resolved = sorted((item for item in forecasts if item["resolution"] is not None), key=lambda item: item["resolution"]["date"], reverse=True)
    score = score_forecasts(forecasts)
    lines = ["# AI Forecasts", "", f"Generated {date.today().isoformat()}. {_score_summary(score)}", "", "## Open forecasts", ""]
    if not open_items:
        lines.append("No open forecasts.")
    for item in open_items:
        lines.extend(
            [
                f"### {item['claim']}",
                "",
                f"**{current_probability(item):.0%}** · resolves by {item['resolve_by']} · {item['category']} · `{item['id']}`",
                "",
                item["resolution_criteria"],
                "",
            ]
        )
    lines.extend(["## Resolved forecasts", ""])
    if not resolved:
        lines.append("No resolved forecasts.")
    for item in resolved:
        resolution = item["resolution"]
        lines.extend(
            [
                f"### {item['claim']}",
                "",
                f"**{resolution['outcome'].upper()}** · forecast {current_probability(item):.0%} · resolved {resolution['date']} · [source]({resolution['source_url']}) · `{item['id']}`",
                "",
            ]
        )
    lines.extend(["## Score", "", _score_summary(score), ""])
    if score["categories"]:
        lines.extend(["| Category | Forecasts | Brier |", "|---|---:|---:|"])
        for category, item in score["categories"].items():
            lines.append(f"| {category} | {item['count']} | {item['brier']:.4f} |")
        lines.append("")
    if score["calibration"]:
        lines.extend(["### Calibration", "", "| Bucket | N | Mean forecast | Observed yes |", "|---|---:|---:|---:|"])
        for item in score["calibration"]:
            lines.append(f"| {item['bucket']} | {item['count']} | {item['mean_probability']:.1%} | {item['actual_rate']:.1%} |")
        lines.append("")
    if score["baseline"]:
        item = score["baseline"]
        lines.append(f"Baseline subset ({item['count']}): ledger {item['forecast_brier']:.4f}; community {item['baseline_brier']:.4f}.")
        lines.append("")
    return "\n".join(lines)


def render_html(forecasts: list[dict[str, Any]]) -> str:
    open_items = sorted((item for item in forecasts if item["resolution"] is None), key=lambda item: item["resolve_by"])
    resolved = sorted((item for item in forecasts if item["resolution"] is not None), key=lambda item: item["resolution"]["date"], reverse=True)
    score = score_forecasts(forecasts)

    def cards(items: list[dict[str, Any]], resolved_cards: bool = False) -> str:
        if not items:
            return '<p class="empty">None yet.</p>'
        chunks = []
        for item in items:
            if resolved_cards:
                resolution = item["resolution"]
                badge = f'<span class="outcome {escape(resolution["outcome"])}">{escape(resolution["outcome"].upper())}</span>'
                meta = f'{current_probability(item):.0%} forecast · resolved {escape(resolution["date"])} · <a href="{escape(resolution["source_url"], quote=True)}">source</a>'
            else:
                badge = f'<span class="probability">{current_probability(item):.0%}</span>'
                meta = f'Resolves by {escape(item["resolve_by"])} · {escape(item["category"])}'
            chunks.append(
                f'<article>{badge}<h3>{escape(item["claim"])}</h3><p class="meta">{meta}</p><p>{escape(item["resolution_criteria"])}</p><code>{escape(item["id"])}</code></article>'
            )
        return "".join(chunks)

    category_rows = "".join(
        f'<tr><td>{escape(category)}</td><td>{item["count"]}</td><td>{item["brier"]:.4f}</td></tr>'
        for category, item in score["categories"].items()
    ) or '<tr><td colspan="3">No scored forecasts.</td></tr>'
    calibration_rows = "".join(
        f'<tr><td>{item["bucket"]}</td><td>{item["count"]}</td><td>{item["mean_probability"]:.1%}</td><td>{item["actual_rate"]:.1%}</td></tr>'
        for item in score["calibration"]
    ) or '<tr><td colspan="4">No calibration data.</td></tr>'
    baseline = ""
    if score["baseline"]:
        item = score["baseline"]
        baseline = f'<p>Baseline subset ({item["count"]}): ledger {item["forecast_brier"]:.4f}; community {item["baseline_brier"]:.4f}.</p>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Forecasts</title><style>
:root{{--bg:#f6f4ee;--panel:#fffefa;--text:#20201d;--muted:#67665f;--line:#d8d4c8;--accent:#245f4d;--yes:#1d6a43;--no:#9a332d}}
@media(prefers-color-scheme:dark){{:root{{--bg:#151714;--panel:#1e211d;--text:#edf0e9;--muted:#a9afa4;--line:#3b4038;--accent:#8dd5b8;--yes:#84d5a7;--no:#f19a91}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,sans-serif}}main{{max-width:840px;margin:auto;padding:3rem 1rem 5rem}}header{{border-bottom:1px solid var(--line);margin-bottom:2.5rem}}h1{{font-size:clamp(2.25rem,8vw,4.5rem);line-height:1;margin:.25rem 0 1rem;letter-spacing:-.04em}}h2{{margin-top:3rem}}.lede,.meta,.empty{{color:var(--muted)}}.grid{{display:grid;gap:1rem}}article{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1.2rem}}article h3{{font-size:1.1rem;margin:.65rem 0}}.probability,.outcome{{display:inline-block;color:var(--accent);font-weight:800;letter-spacing:.03em}}.outcome.no{{color:var(--no)}}.outcome.yes{{color:var(--yes)}}code{{font-size:.78rem;color:var(--muted)}}table{{width:100%;border-collapse:collapse;background:var(--panel)}}th,td{{padding:.7rem;border:1px solid var(--line);text-align:left}}th:not(:first-child),td:not(:first-child){{text-align:right}}a{{color:var(--accent)}}
</style></head><body><main><header><p class="lede">A dated, falsifiable record</p><h1>AI Forecasts</h1><p>{escape(_score_summary(score))}</p></header>
<section><h2>Open forecasts</h2><div class="grid">{cards(open_items)}</div></section>
<section><h2>Resolved forecasts</h2><div class="grid">{cards(resolved, True)}</div></section>
<section><h2>Score</h2><p>{escape(_score_summary(score))}</p><table><thead><tr><th>Category</th><th>Forecasts</th><th>Brier</th></tr></thead><tbody>{category_rows}</tbody></table>{baseline}
<h3>Calibration</h3><table><thead><tr><th>Bucket</th><th>N</th><th>Mean forecast</th><th>Observed yes</th></tr></thead><tbody>{calibration_rows}</tbody></table></section>
</main></body></html>'''


def write_report(forecasts: list[dict[str, Any]], output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    markdown_path = output / "index.md"
    html_path = output / "index.html"
    markdown_path.write_text(render_markdown(forecasts), encoding="utf-8")
    html_path.write_text(render_html(forecasts), encoding="utf-8")
    return html_path, markdown_path

