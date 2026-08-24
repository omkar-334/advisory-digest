# API reference

Two kinds of interface: HTTP endpoints served from the deployed site, and the command-line
scripts that make up the pipeline. Everything the dashboard does, you can do from a terminal.

Base URL: `https://advisory-digest.vercel.app`

---

## HTTP

### `POST /api/check-source`

Assess whether a URL qualifies as a source. Returns in about two seconds. Nothing is built
and no credit is spent.

**Request**

```json
{ "url": "https://www.example-advisory.com/insights" }
```

**Response `200` — eligible**

```json
{
  "url": "https://www.example-advisory.com/insights",
  "http_status": 200,
  "note": "",
  "eligible": true,
  "blocked": [],
  "publisher": "Example Advisory LLP",
  "content_type": "professional articles",
  "article_count_estimate": 20,
  "confidence": 0.9,
  "reason": "The page lists many distinct articles, each with a headline and link.",
  "description": "Extract title, summary, published_date as ISO 8601, absolute article_url and tags from each article card. Do not extract author names.",
  "command": "./scripts/onboard.py https://www.example-advisory.com/insights"
}
```

**Response `200` — refused**

`eligible` is `false` and `blocked` carries one entry per rule broken:

```json
{
  "eligible": false,
  "blocked": [
    { "rule": "Government sites",
      "why": "Barred by hackathon rule 7, and Scraper Studio rejects these domains outright." }
  ]
}
```

| Rule | Triggered by |
|---|---|
| Government sites | classifier verdict, **or** host suffix `.gov` `.gov.in` `.gov.uk` `.gov.au` `.mil` `.nic.in` `.gouv.fr` |
| Login-walled content | classifier verdict |
| Paywalled content | classifier verdict |
| Pages about private individuals | classifier verdict of `personal_data_risk: high` |
| Not an article listing | a single article, homepage or product page |

The host-suffix check runs independently of the classifier. A language model can be wrong, or
be talked out of a judgement by page content, and rule 7 does not depend on its opinion.

**An HTTP 403 from the target is not a refusal.** Several legitimate sources reject naive
clients and work correctly through Bright Data's unblocking layer. When the target returns
401, 403 or 429, `note` says so and assessment continues.

**Errors**

| Status | Meaning |
|---|---|
| `400` | `url` missing or not `http(s)://` |
| `405` | Not a POST |
| `422` | The page returned almost no readable text to assess |
| `502` | Could not reach the URL, or the classifier failed |
| `503` | `OPENAI_API_KEY` not set on the deployment |

---

### `POST /api/add-source`

Queue an eligible source to actually be built and added to the fleet.

Building a collector takes four to twenty minutes, which no serverless function can wait for.
This dispatches a GitHub Actions run that does the work on a runner with the CLI, the
credentials and the time. The response is immediate.

**Request**

```json
{
  "url": "https://www.example-advisory.com/insights",
  "description": "Extract title, summary, published_date …"
}
```

Pass the `description` returned by `/api/check-source`. It must be at least 20 characters.

**Response `202`**

```json
{
  "queued": true,
  "url": "https://www.example-advisory.com/insights",
  "firm": "example-advisory.com",
  "watch": "https://github.com/omkar-334/advisory-digest/actions/workflows/add-source.yml",
  "message": "Queued. The collector is being built now…"
}
```

| Status | Meaning |
|---|---|
| `400` | Missing URL, or a description shorter than 20 characters |
| `403` | Government domain. Refused here as well as in `check-source`, because this endpoint is public and a rule that only exists upstream is not a rule |
| `502` | GitHub rejected the dispatch. `fallback` carries the CLI command |
| `503` | `GITHUB_TOKEN` not set. `fallback` carries the CLI command |

---

### `POST /api/ask`

One natural-language entry point to the corpus. Ask a question, or describe a company — the
model decides which the input is before answering.

These were two endpoints. That was a distinction the machine cared about and the reader did
not: both are "put words in, get back the relevant part of what the firms published".

**No vector database.** The whole corpus — title plus a short summary for ~213 articles — is
roughly 15k tokens and fits in context. Retrieval would add an embedding step, a store to
keep in sync, and a failure mode that does not exist today: the retriever misses the right
article and the model answers confidently from the wrong ones. Revisit past ~5,000 articles.

**Request**

```json
{ "input": "Do the firms agree on how AI should be used in audits?" }
```

`question` and `profile` are also accepted as keys, so the older callers keep working.

**Response `200` — a question**

```json
{
  "mode": "question",
  "answer": "The firms do not agree. RSM emphasises human judgment alongside AI…",
  "confidence": "high",
  "citations": [
    { "title": "…", "firm": "rsmus.com", "url": "…", "date": "2026-08-19", "why": "" }
  ],
  "followups": ["What specific AI applications are firms exploring in audits?"],
  "searched": 140
}
```

**Response `200` — a profile**

`mode` is `"profile"`, `answer` says what the profession is publishing that bears on the
business, and each citation carries a `why` specific to it.

| Status | Meaning |
|---|---|
| `400` | Input shorter than 5 characters |
| `502` | Could not read the dataset, or the model failed |
| `503` | `OPENAI_API_KEY` not set, or nothing published yet |

**An empty answer is treated as a failure, not a result.** "Nothing applies" and "the model
broke" look identical to a reader, and only one of them is true.

---

## Published data

Static JSON, refreshed every twelve hours by CI. No authentication.

### `GET /data/latest.json`

Every collected article, deduplicated on canonical URL, byline fields stripped.

```json
[{
  "title": "5 ways private companies can use an audit to unlock strategic value",
  "summary": "Five ways audits provide insight beyond compliance.",
  "published_date": "2026-08-17",
  "article_url": "https://rsmus.com/insights/…",
  "tags": ["Audit", "Private equity"],
  "_firm": "rsmus.com",
  "_source": "https://rsmus.com/insights.html"
}]
```

`_firm` and `_source` are added by the pipeline: the host the row came from, and the listing
page it was collected from.

### `GET /data/health.json`

The contract report for the most recent run.

```json
{
  "stamp": "20260823T175358Z",
  "total_rows": 226,
  "sources": 13,
  "healthy_sources": 8,
  "failed_runs": 5,
  "healthy": false,
  "run_failures": ["bakertilly.com: the run failed with 19 error(s) …"],
  "per_firm": {
    "rsmus.com": { "rows": 73, "healthy": true, "run_failed": false, "errors": 0, "problems": [] }
  },
  "params": { "min_rows_per_source": 3, "min_field_coverage": 0.7, "min_healthy_sources": 0.6 }
}
```

`run_failed` is the field that matters. A source with `healthy: false, run_failed: true` is
**not** broken — its run failed, and it must be re-run rather than repaired.

### `GET /data/signals.json`

Subjects ranked by how many distinct firms covered them, plus which subjects share coverage.

```json
{
  "topic_source": "llm:gpt-4o-mini",
  "generated_from": 181,
  "window_days": 30,
  "as_of": "2026-08-21",
  "signals": [{
    "topic": "Business Tax Compliance and Consulting",
    "firms": 6,
    "firm_list": ["bdo.com", "claconnect.com", "…"],
    "articles": 12,
    "recent_articles": 5,
    "recent_firms": 4,
    "examples": [{ "title": "…", "firm": "…", "url": "…", "date": "…" }]
  }],
  "cooccurrence": [
    { "a": "Business Tax Compliance", "b": "AI in Auditing", "shared": 4, "firms": ["…"] }
  ]
}
```

`topic_source` is `llm:<model>` when topics were classified, or `regex-fallback` when no API
key was available.

### `GET /data/heals.json`

Every repair attempt, including ones that changed nothing.

```json
[{
  "stamp": "20260823T143500Z",
  "firm": "bakertilly.com",
  "collector": "c_mt5vy4lr2psac64sae",
  "kind": "production",
  "outcome": "repaired",
  "trigger": "Found by the contract on a routine run. Not staged.",
  "diagnosis": "'article_url' was empty on 20 of 20 articles …",
  "metrics": [{ "label": "article_url populated", "before": "0%", "after": "100%" }]
}]
```

| Field | Values |
|---|---|
| `kind` | `production` (a real source) · `verification` (the control page, broken on purpose) |
| `outcome` | `repaired` · `no_change_needed` · `failed` |

`metrics` records what moved. A repair can return the same row count while restoring two
fields from 0% to 100%, and a row count alone makes that look like a no-op.

### `GET /data/briefs.json`

One brief per subject: what the firms agree on, where they differ, who it affects, and who
published first within a burst of coverage.

### `GET /data/digest.json`

Editions covering a rolling window, newest first. Each records what moved, what was new
since the previous edition, and the widest cross-firm coverage in that window.

### `GET /data/reliability.json`

How reliably each source can be scraped: repairs that held, false alarms where the contract
was wrong rather than the scraper, and sources that have never worked. A byproduct of
running a self-healing collector fleet, which is why nobody else has it.

### `GET /data/schedule.json`

```json
{ "cadence_hours": 12, "cron": "0 3,15 * * *", "timezone": "UTC", "description": "…" }
```

---

## Command line

### Exit codes

`scripts/validate.py`, and therefore `run_fleet.sh` and `heal_loop.sh`, share one contract.
Everything downstream depends on it:

| Code | Meaning | Correct response |
|---|---|---|
| `0` | Contract satisfied | publish |
| `1` | A run failed, or nothing was collected | **re-run — never heal** |
| `2` | A real break | heal |
| `3` | `heal_loop.sh` only: stopped at the approval gate | review, then re-run |

Exit 1 covers rate limits, navigation timeouts, a source that returned no envelope at all,
and an empty run. None of these are repairable, and healing a scraper that works spends
credits and can leave it worse.

### Scripts

| Command | Does |
|---|---|
| `./scripts/onboard.py <url> [--dry-run]` | Classify, gate, build, register. `--dry-run` stops after the verdict |
| `./scripts/create_collector.sh <name> <url> "<description>"` | Build a collector and register it |
| `./scripts/run_fleet.sh` | Run every collector, merge, validate |
| `./scripts/heal_loop.sh` | Run, repair what broke, re-run, verify |
| `REVIEW=1 ./scripts/heal_loop.sh` | Stop at the approval gate instead of auto-approving |
| `python3 scripts/validate.py <run.json> [outdir] [expected-urls.txt]` | The contract. Prints the heal prompt on stdout, findings on stderr |
| `python3 scripts/broken_sources.py` | TSV of genuinely heal-worthy sources |
| `python3 scripts/classify_topics.py` | Build a topic taxonomy and assign labels |
| `python3 scripts/signals.py` | Rank subjects by independent coverage |
| `python3 scripts/publish.py` | Publish rows, contract report and repair log |

### Environment

| Variable | Needed by | Effect if missing |
|---|---|---|
| `BRIGHTDATA_API_KEY` | everything that scrapes | scripts fail |
| `OPENAI_API_KEY` | `onboard.py`, `classify_topics.py`, `/api/check-source` | signals fall back to patterns; the endpoint returns 503 |
| `GITHUB_TOKEN` | `/api/add-source` | the endpoint returns 503 with the CLI fallback |
| `FLEET_CONCURRENCY` | `run_fleet.sh` | defaults to 2. Higher triggers crawler rate limits |
| `RUN_ID` | `run_fleet.sh` | a run is resumable under a fixed id |
| `MAX_HEAL_ATTEMPTS` | `heal_loop.sh` | defaults to 2 |
| `REVIEW` | `heal_loop.sh` | `1` stops at the approval gate |

### The fleet registry

`scripts/collectors.json` is the source of truth for what runs:

```json
{ "collectors": [
  { "firm": "rsmus.com", "name": "RSM",
    "collector_id": "c_mt5sgta91r4gozaifs",
    "url": "https://rsmus.com/insights.html", "status": "live" }
]}
```

`firm` is the bare host and is the key everything joins on. An entry without a
`collector_id` is skipped.
