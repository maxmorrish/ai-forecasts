from __future__ import annotations

from collections import defaultdict
from typing import Any

from .model import current_probability


def brier(probability: float, outcome: int) -> float:
    return (probability - outcome) ** 2


def score_forecasts(forecasts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for forecast in forecasts:
        resolution = forecast["resolution"]
        if not resolution or resolution["outcome"] == "ambiguous":
            continue
        outcome = 1 if resolution["outcome"] == "yes" else 0
        probability = current_probability(forecast)
        row = {
            "id": forecast["id"],
            "category": forecast["category"],
            "probability": probability,
            "outcome": outcome,
            "brier": brier(probability, outcome),
        }
        if forecast.get("baseline"):
            baseline_probability = float(forecast["baseline"]["probability"])
            row["baseline_brier"] = brier(baseline_probability, outcome)
        rows.append(row)

    overall = sum(row["brier"] for row in rows) / len(rows) if rows else None
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row["brier"])
    categories = {
        category: {"count": len(values), "brier": sum(values) / len(values)}
        for category, values in sorted(grouped.items())
    }

    buckets = []
    for start in range(0, 100, 10):
        selected = [row for row in rows if start / 100 <= row["probability"] < (start + 10) / 100]
        if selected:
            buckets.append(
                {
                    "bucket": f"{start:02d}-{start + 10:02d}%",
                    "count": len(selected),
                    "mean_probability": sum(row["probability"] for row in selected) / len(selected),
                    "actual_rate": sum(row["outcome"] for row in selected) / len(selected),
                }
            )

    baseline_rows = [row for row in rows if "baseline_brier" in row]
    baseline = None
    if baseline_rows:
        ours = sum(row["brier"] for row in baseline_rows) / len(baseline_rows)
        community = sum(row["baseline_brier"] for row in baseline_rows) / len(baseline_rows)
        baseline = {
            "count": len(baseline_rows),
            "forecast_brier": ours,
            "baseline_brier": community,
            "difference": ours - community,
        }
    return {
        "count": len(rows),
        "overall_brier": overall,
        "categories": categories,
        "calibration": buckets,
        "baseline": baseline,
        "rows": rows,
    }


def format_score(result: dict[str, Any]) -> str:
    if not result["count"]:
        return "No unambiguous resolved forecasts to score."
    lines = [f"Overall Brier score: {result['overall_brier']:.4f} ({result['count']} forecasts)", "", "By category:"]
    for category, item in result["categories"].items():
        lines.append(f"  {category}: {item['brier']:.4f} ({item['count']})")
    lines.extend(["", "Calibration:"])
    for bucket in result["calibration"]:
        lines.append(
            f"  {bucket['bucket']}: predicted {bucket['mean_probability']:.1%}, observed {bucket['actual_rate']:.1%} (n={bucket['count']})"
        )
    if result["baseline"]:
        item = result["baseline"]
        comparison = "better" if item["difference"] < 0 else "worse" if item["difference"] > 0 else "equal"
        lines.extend(
            [
                "",
                f"Baseline comparison ({item['count']}): forecasts {item['forecast_brier']:.4f}, community {item['baseline_brier']:.4f}; {abs(item['difference']):.4f} {comparison}.",
            ]
        )
    return "\n".join(lines)

