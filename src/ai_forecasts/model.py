from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urlparse

import yaml


class ForecastLoader(yaml.SafeLoader):
    """Safe YAML loader that keeps unquoted yes/no as strings.

    YAML 1.1 treats those words as booleans, while the ledger schema uses them
    as literal outcome values.
    """


ForecastLoader.yaml_implicit_resolvers = {
    key: [item for item in values if item[0] != "tag:yaml.org,2002:bool"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


CATEGORIES = {
    "models",
    "agents",
    "tooling",
    "open-source",
    "policy",
    "hardware",
    "business",
    "other",
}
OUTCOMES = {"yes", "no", "ambiguous"}
REQUIRED_KEYS = {
    "id",
    "created",
    "claim",
    "resolution_criteria",
    "resolve_by",
    "probability",
    "category",
    "evidence",
    "updates",
    "resolution",
}
ALLOWED_KEYS = REQUIRED_KEYS | {"baseline"}


class ValidationError(ValueError):
    pass


def parse_date(value: Any, field: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a date in YYYY-MM-DD form")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be a date in YYYY-MM-DD form") from exc


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number strictly between 0 and 1")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a number strictly between 0 and 1") from exc
    if not 0 < result < 1:
        raise ValidationError(f"{field} must be strictly between 0 and 1")
    return result


def _url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an http(s) URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(f"{field} must be an http(s) URL")
    return value


def _criteria_is_objective(value: Any) -> bool:
    if not isinstance(value, str) or len(value.strip()) < 20:
        return False
    lowered = value.strip().lower()
    if lowered in {"tbd", "to be decided", "use judgment", "subjective"}:
        return False
    # A binary forecast needs an explicit decision rule, not merely more prose.
    return any(
        marker in lowered
        for marker in (
            "resolves yes if",
            "resolve yes if",
            "outcome is yes if",
            "yes when",
            "yes iff",
        )
    )


def validate_forecast(raw: Any, *, path: Path | None = None) -> dict[str, Any]:
    where = f" in {path}" if path else ""
    if not isinstance(raw, dict):
        raise ValidationError(f"forecast{where} must be a YAML mapping")
    missing = REQUIRED_KEYS - raw.keys()
    if missing:
        raise ValidationError(f"forecast{where} is missing: {', '.join(sorted(missing))}")
    extra = raw.keys() - ALLOWED_KEYS
    if extra:
        raise ValidationError(f"forecast{where} has unknown fields: {', '.join(sorted(extra))}")

    data = dict(raw)
    forecast_id = data["id"]
    if not isinstance(forecast_id, str) or not forecast_id.strip():
        raise ValidationError("id must be a non-empty string")
    if "/" in forecast_id or "\\" in forecast_id or forecast_id in {".", ".."}:
        raise ValidationError("id may not contain a path separator")
    if path and path.stem != forecast_id:
        raise ValidationError(f"id {forecast_id!r} must match filename {path.name!r}")

    created = parse_date(data["created"], "created")
    resolve_by = parse_date(data["resolve_by"], "resolve_by")
    if resolve_by < created:
        raise ValidationError("resolve_by may not be earlier than created")
    data["created"] = created.isoformat()
    data["resolve_by"] = resolve_by.isoformat()

    claim = data["claim"]
    if not isinstance(claim, str) or not claim.strip() or "\n" in claim:
        raise ValidationError("claim must be one non-empty sentence on one line")
    if claim.strip()[-1] not in ".?!" or re.search(r"[.!?]\s+[A-Z]", claim.strip()[:-1]):
        raise ValidationError("claim must contain exactly one sentence")
    data["claim"] = claim.strip()
    if not _criteria_is_objective(data["resolution_criteria"]):
        raise ValidationError(
            "resolution_criteria must give an explicit objective binary rule, such as 'Resolves yes if ...'"
        )
    data["resolution_criteria"] = data["resolution_criteria"].strip()
    data["probability"] = _probability(data["probability"], "probability")

    if data["category"] not in CATEGORIES:
        raise ValidationError(f"category must be one of: {', '.join(sorted(CATEGORIES))}")
    if not isinstance(data["evidence"], list):
        raise ValidationError("evidence must be a list of URLs")
    data["evidence"] = [_url(item, "evidence item") for item in data["evidence"]]

    baseline = data.get("baseline")
    if baseline is not None:
        if not isinstance(baseline, dict):
            raise ValidationError("baseline must be null or a mapping")
        for key in ("platform", "url", "probability", "recorded"):
            if key not in baseline:
                raise ValidationError(f"baseline is missing {key}")
        if baseline["platform"] not in {"manifold", "metaculus"}:
            raise ValidationError("baseline.platform must be manifold or metaculus")
        baseline = dict(baseline)
        baseline["url"] = _url(baseline["url"], "baseline.url")
        baseline["probability"] = _probability(baseline["probability"], "baseline.probability")
        baseline["recorded"] = parse_date(baseline["recorded"], "baseline.recorded").isoformat()
        if baseline["recorded"] != data["created"]:
            raise ValidationError("baseline.recorded must equal the forecast creation date")
        data["baseline"] = baseline

    if not isinstance(data["updates"], list):
        raise ValidationError("updates must be a list")
    updates: list[dict[str, Any]] = []
    previous = created
    for index, update in enumerate(data["updates"]):
        if not isinstance(update, dict) or set(update) != {"date", "probability", "reason"}:
            raise ValidationError(f"updates[{index}] must contain date, probability, and reason")
        updated = parse_date(update["date"], f"updates[{index}].date")
        if updated < created or updated < previous:
            raise ValidationError("updates must be chronological and not predate creation")
        reason = update["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError(f"updates[{index}].reason must be non-empty")
        updates.append(
            {"date": updated.isoformat(), "probability": _probability(update["probability"], f"updates[{index}].probability"), "reason": reason.strip()}
        )
        previous = updated
    data["updates"] = updates

    resolution = data["resolution"]
    if resolution is not None:
        if not isinstance(resolution, dict) or set(resolution) != {"date", "outcome", "source_url"}:
            raise ValidationError("resolution must be null or contain date, outcome, and source_url")
        resolved = parse_date(resolution["date"], "resolution.date")
        if resolved < created:
            raise ValidationError("resolution.date may not predate creation")
        if resolution["outcome"] not in OUTCOMES:
            raise ValidationError("resolution.outcome must be yes, no, or ambiguous")
        if updates and parse_date(updates[-1]["date"], "last update date") > resolved:
            raise ValidationError("updates may not be dated after resolution")
        data["resolution"] = {
            "date": resolved.isoformat(),
            "outcome": resolution["outcome"],
            "source_url": _url(resolution["source_url"], "resolution.source_url"),
        }
    return data


def load_forecast(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=ForecastLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"could not read {path}: {exc}") from exc
    return validate_forecast(raw, path=path)


def load_forecasts(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        raise ValidationError(f"data directory does not exist: {directory}")
    forecasts = [load_forecast(path) for path in sorted(directory.glob("*.yaml"))]
    ids = [item["id"] for item in forecasts]
    if len(ids) != len(set(ids)):
        raise ValidationError("forecast ids must be unique")
    return forecasts


def save_forecast(directory: Path, data: dict[str, Any], *, overwrite: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    normalized = validate_forecast(data)
    path = directory / f"{normalized['id']}.yaml"
    if path.exists() and not overwrite:
        raise ValidationError(f"forecast already exists: {normalized['id']}")
    with NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as handle:
        yaml.safe_dump(normalized, handle, sort_keys=False, allow_unicode=True)
        temporary = Path(handle.name)
    temporary.replace(path)
    return path


def current_probability(forecast: dict[str, Any]) -> float:
    if forecast["updates"]:
        return float(forecast["updates"][-1]["probability"])
    return float(forecast["probability"])

