from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "ai-forecasts/0.1 (public read-only baseline lookup)"


class BaselineError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    platform: str
    title: str
    url: str
    probability: float


def _get_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read(300).decode("utf-8", "replace").strip()
        raise BaselineError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BaselineError(str(exc)) from exc


def search_manifold(term: str, *, limit: int = 5) -> list[Candidate]:
    query = urlencode({"term": term, "filter": "open", "contractType": "BINARY", "limit": limit})
    payload = _get_json(f"https://api.manifold.markets/v0/search-markets?{query}")
    candidates = []
    for item in payload if isinstance(payload, list) else []:
        probability = item.get("probability")
        if item.get("outcomeType") == "BINARY" and isinstance(probability, (int, float)) and 0 < probability < 1:
            candidates.append(Candidate("manifold", str(item.get("question", "Untitled")), str(item["url"]), float(probability)))
    return candidates


def _metaculus_probability(item: dict[str, Any]) -> float | None:
    question = item.get("question") if isinstance(item.get("question"), dict) else item
    aggregations = question.get("aggregations", {}) if isinstance(question, dict) else {}
    candidates = [
        question.get("community_prediction") if isinstance(question, dict) else None,
        item.get("community_prediction"),
        aggregations.get("recency_weighted", {}).get("latest", {}).get("centers", [None])[0]
        if isinstance(aggregations.get("recency_weighted"), dict)
        else None,
    ]
    for value in candidates:
        if isinstance(value, dict):
            value = value.get("full", {}).get("q2") or value.get("q2")
        if isinstance(value, (int, float)) and 0 < value < 1:
            return float(value)
    return None


def search_metaculus(term: str, *, limit: int = 5) -> list[Candidate]:
    # Metaculus currently returns 403 to anonymous callers. This remains a
    # credential-free probe so the command can use public access if restored.
    query = urlencode({"search": term, "limit": limit})
    payload = _get_json(f"https://www.metaculus.com/api/posts/?{query}")
    items = payload.get("results", []) if isinstance(payload, dict) else []
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        probability = _metaculus_probability(item)
        post_id = item.get("id")
        title = item.get("title") or item.get("question", {}).get("title")
        if probability is not None and post_id and title:
            candidates.append(Candidate("metaculus", str(title), f"https://www.metaculus.com/questions/{post_id}/", probability))
    return candidates


def search_all(term: str, provider: str = "both") -> tuple[list[Candidate], list[str]]:
    candidates: list[Candidate] = []
    errors: list[str] = []
    searches = []
    if provider in {"both", "manifold"}:
        searches.append(("Manifold", search_manifold))
    if provider in {"both", "metaculus"}:
        searches.append(("Metaculus", search_metaculus))
    for name, search in searches:
        try:
            candidates.extend(search(term))
        except BaselineError as exc:
            errors.append(f"{name}: {exc}")
    return candidates, errors

