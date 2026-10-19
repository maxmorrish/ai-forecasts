from ai_forecasts import baselines


def test_manifold_filters_to_binary_probabilities(monkeypatch) -> None:
    monkeypatch.setattr(
        baselines,
        "_get_json",
        lambda _url: [
            {"outcomeType": "BINARY", "probability": 0.61, "question": "Will it?", "url": "https://manifold.markets/a/b"},
            {"outcomeType": "MULTIPLE_CHOICE", "probability": 0.4, "question": "Which?", "url": "https://manifold.markets/a/c"},
        ],
    )
    result = baselines.search_manifold("query")
    assert [(item.platform, item.probability) for item in result] == [("manifold", 0.61)]


def test_metaculus_parser_handles_public_post_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        baselines,
        "_get_json",
        lambda _url: {"results": [{"id": 12, "title": "Will it?", "question": {"community_prediction": 0.57}}]},
    )
    result = baselines.search_metaculus("query")
    assert result[0].url == "https://www.metaculus.com/questions/12/"
    assert result[0].probability == 0.57

