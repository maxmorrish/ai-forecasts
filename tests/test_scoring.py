from pathlib import Path

import pytest

from ai_forecasts.model import load_forecasts
from ai_forecasts.scoring import brier, score_forecasts


def test_brier_score() -> None:
    assert brier(0.75, 1) == pytest.approx(0.0625)
    assert brier(0.2, 0) == pytest.approx(0.04)


def test_examples_score_latest_probabilities() -> None:
    examples = Path(__file__).parents[1] / "examples"
    result = score_forecasts(load_forecasts(examples))
    assert result["count"] == 2
    assert result["overall_brier"] == pytest.approx((0.25**2 + 0.2**2) / 2)
    assert result["categories"]["agents"]["brier"] == pytest.approx(0.25**2)
    assert result["baseline"]["count"] == 1
    assert result["baseline"]["baseline_brier"] == pytest.approx(0.45**2)

