from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from .baselines import search_all
from .model import CATEGORIES, ValidationError, current_probability, load_forecast, load_forecasts, save_forecast
from .reporting import write_report
from .scoring import format_score, score_forecasts


def _probability(value: str) -> float:
    try:
        probability = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number strictly between 0 and 1") from exc
    if not 0 < probability < 1:
        raise argparse.ArgumentTypeError("must be strictly between 0 and 1")
    return probability


def _prompt(value: str | None, label: str) -> str:
    if value:
        return value
    if not sys.stdin.isatty():
        raise ValidationError(f"{label} is required in non-interactive mode")
    answer = input(f"{label}: ").strip()
    if not answer:
        raise ValidationError(f"{label} is required")
    return answer


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    return f"{date.today().isoformat()}-{slug or 'forecast'}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fc", description="Maintain and score a forecasting ledger.")
    parser.add_argument("--data-dir", type=Path, default=Path("forecasts"), help="forecast YAML directory (default: forecasts)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="add a forecast")
    add.add_argument("--id")
    add.add_argument("--created", default=date.today().isoformat())
    add.add_argument("--claim")
    add.add_argument("--criteria")
    add.add_argument("--resolve-by")
    add.add_argument("--probability", type=_probability)
    add.add_argument("--category", choices=sorted(CATEGORIES))
    add.add_argument("--evidence", action="append", default=[])

    update = subparsers.add_parser("update", help="record a probability update")
    update.add_argument("id")
    update.add_argument("--date", default=date.today().isoformat())
    update.add_argument("--probability", required=True, type=_probability)
    update.add_argument("--reason", required=True)

    resolve = subparsers.add_parser("resolve", help="resolve a forecast")
    resolve.add_argument("id")
    resolve.add_argument("--date", default=date.today().isoformat())
    resolve.add_argument("--outcome", required=True, choices=("yes", "no", "ambiguous"))
    resolve.add_argument("--source-url", required=True)

    listing = subparsers.add_parser("list", help="list forecasts")
    listing.add_argument("--due", type=int, metavar="DAYS", help="only unresolved forecasts due in the next DAYS")

    subparsers.add_parser("score", help="print Brier score and calibration")

    report = subparsers.add_parser("report", help="render the static report")
    report.add_argument("--output", type=Path, default=Path("site"))

    baseline = subparsers.add_parser("baseline", help="record a public community baseline")
    baseline.add_argument("id")
    baseline.add_argument("--search", required=True)
    baseline.add_argument("--provider", choices=("both", "manifold", "metaculus"), default="both")
    baseline.add_argument("--pick", type=int, help="1-based result number (otherwise prompt)")
    baseline.add_argument("--replace", action="store_true")
    return parser


def _path(directory: Path, forecast_id: str) -> Path:
    return directory / f"{forecast_id}.yaml"


def command_add(args: argparse.Namespace) -> None:
    claim = _prompt(args.claim, "claim")
    criteria = _prompt(args.criteria, "resolution criteria (start with 'Resolves yes if')")
    resolve_by = _prompt(args.resolve_by, "resolve by (YYYY-MM-DD)")
    probability = args.probability
    if probability is None:
        probability = _probability(_prompt(None, "probability (0-1 exclusive)"))
    category = args.category or _prompt(None, f"category ({', '.join(sorted(CATEGORIES))})")
    data = {
        "id": args.id or _slug(claim),
        "created": args.created,
        "claim": claim,
        "resolution_criteria": criteria,
        "resolve_by": resolve_by,
        "probability": probability,
        "category": category,
        "evidence": args.evidence,
        "baseline": None,
        "updates": [],
        "resolution": None,
    }
    print(save_forecast(args.data_dir, data))


def command_update(args: argparse.Namespace) -> None:
    data = load_forecast(_path(args.data_dir, args.id))
    if data["resolution"] is not None:
        raise ValidationError("resolved forecasts cannot be updated")
    data["updates"].append({"date": args.date, "probability": args.probability, "reason": args.reason})
    print(save_forecast(args.data_dir, data, overwrite=True))


def command_resolve(args: argparse.Namespace) -> None:
    data = load_forecast(_path(args.data_dir, args.id))
    if data["resolution"] is not None:
        raise ValidationError("forecast is already resolved")
    data["resolution"] = {"date": args.date, "outcome": args.outcome, "source_url": args.source_url}
    print(save_forecast(args.data_dir, data, overwrite=True))


def command_list(args: argparse.Namespace) -> None:
    forecasts = load_forecasts(args.data_dir)
    if args.due is not None:
        if args.due < 0:
            raise ValidationError("--due must be zero or greater")
        today = date.today()
        cutoff = today + timedelta(days=args.due)
        forecasts = [
            item for item in forecasts if item["resolution"] is None and today <= date.fromisoformat(item["resolve_by"]) <= cutoff
        ]
    for item in sorted(forecasts, key=lambda value: value["resolve_by"]):
        state = item["resolution"]["outcome"] if item["resolution"] else "open"
        print(f"{item['resolve_by']}  {state:9}  {current_probability(item):.0%}  {item['id']}  {item['claim']}")


def command_baseline(args: argparse.Namespace) -> None:
    data = load_forecast(_path(args.data_dir, args.id))
    if data.get("baseline") and not args.replace:
        raise ValidationError("forecast already has a baseline; use --replace to replace it")
    if data["created"] != date.today().isoformat():
        raise ValidationError("a live baseline can only be recorded on the forecast creation date")
    candidates, errors = search_all(args.search, args.provider)
    for error in errors:
        print(f"warning: {error}", file=sys.stderr)
    if not candidates:
        raise ValidationError("no public binary baseline candidates were available")
    for index, candidate in enumerate(candidates, 1):
        print(f"{index}. [{candidate.platform}] {candidate.probability:.1%} — {candidate.title}\n   {candidate.url}")
    pick = args.pick
    if pick is None:
        if not sys.stdin.isatty():
            raise ValidationError("--pick is required in non-interactive mode")
        try:
            pick = int(input("Record which result? "))
        except ValueError as exc:
            raise ValidationError("selection must be a result number") from exc
    if pick < 1 or pick > len(candidates):
        raise ValidationError(f"--pick must be between 1 and {len(candidates)}")
    selected = candidates[pick - 1]
    data["baseline"] = {
        "platform": selected.platform,
        "url": selected.url,
        "probability": selected.probability,
        "recorded": data["created"],
    }
    print(save_forecast(args.data_dir, data, overwrite=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "add":
            command_add(args)
        elif args.command == "update":
            command_update(args)
        elif args.command == "resolve":
            command_resolve(args)
        elif args.command == "list":
            command_list(args)
        elif args.command == "score":
            print(format_score(score_forecasts(load_forecasts(args.data_dir))))
        elif args.command == "report":
            html, markdown = write_report(load_forecasts(args.data_dir), args.output)
            print(f"wrote {html} and {markdown}")
        elif args.command == "baseline":
            command_baseline(args)
    except (ValidationError, OSError) as exc:
        parser.exit(2, f"fc: error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

