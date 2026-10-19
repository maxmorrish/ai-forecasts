# AI Forecasts

AI Forecasts is a local ledger for dated, binary predictions about AI. Each forecast says exactly what would count as “yes,” gives a probability strictly between 1% and 99%, and names a resolution date. The files are plain YAML so a reader can audit the record without this program.

The ledger is intentionally small. It does not place bets, use accounts, send predictions anywhere, or require a database. Network access is used only when `fc baseline` searches public, read-only community-forecast endpoints.

## Install

Python 3.11 or newer is required.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

This installs the `fc` command. PyYAML is the only runtime dependency; pytest is only used for tests.

## Use

Add a forecast with flags:

```sh
fc add \
  --id 2026-10-19-example \
  --claim "A named model will pass the stated benchmark by year end." \
  --criteria "Resolves yes if the benchmark owner publishes a score at or above 80 before the deadline." \
  --resolve-by 2026-12-31 \
  --probability 0.35 \
  --category models \
  --evidence https://example.com/benchmark
```

Omit the main fields to be prompted interactively. A forecast is refused when its probability is 0 or 1, its dates or URLs are malformed, or its resolution criteria do not state an explicit binary rule beginning with language such as “Resolves yes if …”. Every YAML file is validated whenever the ledger is read.

Record a change of mind without erasing the original:

```sh
fc update 2026-10-19-example --probability 0.48 --reason "A public preview shipped."
```

Resolve it from an external source:

```sh
fc resolve 2026-10-19-example --outcome yes \
  --source-url https://example.com/final-result
```

See forecasts due in the next seven days, score the ledger, and render the site:

```sh
fc list --due 7
fc score
fc report
```

Use a different ledger directory by putting the global option before the command:

```sh
fc --data-dir examples report --output site
```

## Community baselines

A baseline answers a useful question: did this forecast add information beyond what a forecasting community already believed? On the forecast’s creation date, search public binary questions and select a match:

```sh
fc baseline 2026-10-19-example --search "benchmark score by 2026"
```

The command queries Manifold’s public API and makes a credential-free request to Metaculus. Manifold currently supports anonymous search. Metaculus currently documents and enforces authentication for its API, so its anonymous request may return a warning and no results. This tool never asks for or sends a token. To avoid pretending a current community probability was historical, it refuses to add a live baseline after the forecast’s creation date.

Use `--provider manifold` or `--provider metaculus` to search one source. In a script, pass `--pick N` to select the numbered result without a prompt.

## Scoring method

For a forecast with probability `p` and outcome `o` (1 for yes, 0 for no), the Brier score is:

```text
(p - o)²
```

Lower is better. A perfect forecast scores 0; being certain and wrong approaches 1. The score uses the most recent recorded probability. Ambiguous resolutions remain visible but are excluded because there is no binary outcome to score.

`fc score` reports the mean Brier score overall and by category. Its calibration buckets compare the average stated probability with the share that actually resolved yes. With a small sample these buckets are descriptive, not proof of skill. Where a community baseline was captured, the command compares both Brier scores on exactly the subset that has baselines.

## File format

Forecasts live in `forecasts/<id>.yaml`; the filename must match `id`. Open forecasts use `resolution: null`.

```yaml
id: 2026-10-19-example
created: 2026-10-19
claim: A named model will pass the stated benchmark by year end.
resolution_criteria: Resolves yes if the benchmark owner publishes a score at or above 80 before the deadline.
resolve_by: 2026-12-31
probability: 0.35
category: models
evidence:
  - https://example.com/benchmark
baseline:
  platform: manifold
  url: https://manifold.markets/example/question
  probability: 0.42
  recorded: 2026-10-19
updates:
  - date: 2026-11-10
    probability: 0.48
    reason: A public preview shipped.
resolution: null
```

`examples/` contains three marked examples and is not the live ledger. `forecasts/` is intentionally empty until real forecasts are written.

## Test

```sh
.venv/bin/pytest
fc --data-dir examples report --output site
```

