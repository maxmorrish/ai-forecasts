from pathlib import Path

import pytest
import yaml

from ai_forecasts.model import ValidationError, load_forecast, save_forecast, validate_forecast


FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_fixture_loads() -> None:
    forecast = load_forecast(FIXTURES / "valid.yaml")
    assert forecast["id"] == "valid"
    assert forecast["created"] == "2026-01-01"


@pytest.mark.parametrize("probability", [0, 1, -0.1, 1.1])
def test_probability_must_be_strictly_between_zero_and_one(probability: float) -> None:
    raw = yaml.safe_load((FIXTURES / "valid.yaml").read_text())
    raw["probability"] = probability
    with pytest.raises(ValidationError, match="strictly between"):
        validate_forecast(raw)


def test_objective_resolution_rule_is_required() -> None:
    raw = yaml.safe_load((FIXTURES / "valid.yaml").read_text())
    raw["resolution_criteria"] = "We will decide later."
    with pytest.raises(ValidationError, match="objective binary rule"):
        validate_forecast(raw)


def test_unknown_schema_field_is_rejected() -> None:
    raw = yaml.safe_load((FIXTURES / "valid.yaml").read_text())
    raw["confidence_label"] = "likely"
    with pytest.raises(ValidationError, match="unknown fields"):
        validate_forecast(raw)


def test_filename_must_match_id(tmp_path: Path) -> None:
    path = tmp_path / "wrong.yaml"
    path.write_text((FIXTURES / "valid.yaml").read_text())
    with pytest.raises(ValidationError, match="match filename"):
        load_forecast(path)


def test_save_is_round_trippable(tmp_path: Path) -> None:
    raw = yaml.safe_load((FIXTURES / "valid.yaml").read_text())
    path = save_forecast(tmp_path, raw)
    assert load_forecast(path) == validate_forecast(raw)


def test_unquoted_yaml_outcome_is_a_string(tmp_path: Path) -> None:
    text = (FIXTURES / "valid.yaml").read_text().replace(
        "resolution: null",
        "resolution:\n  date: 2026-12-31\n  outcome: yes\n  source_url: https://example.com/result",
    )
    path = tmp_path / "valid.yaml"
    path.write_text(text)
    assert load_forecast(path)["resolution"]["outcome"] == "yes"


def test_update_after_resolution_is_rejected() -> None:
    raw = yaml.safe_load((FIXTURES / "valid.yaml").read_text())
    raw["updates"] = [{"date": "2026-12-31", "probability": 0.6, "reason": "Late evidence."}]
    raw["resolution"] = {"date": "2026-06-01", "outcome": "yes", "source_url": "https://example.com/result"}
    with pytest.raises(ValidationError, match="after resolution"):
        validate_forecast(raw)

