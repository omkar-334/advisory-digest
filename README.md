# Advisory Digest

**What the accounting profession is reacting to, read across twelve firm newsrooms by a
fleet of self-healing scrapers.**

Live: **https://advisory-digest.vercel.app** · Built on Bright Data Scraper Studio for
Into the Scrape-Verse, 17-23 August 2026.

> **Scheduled scraping is paused.** The 12-hourly cron in
> [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) is commented out to stop it
> consuming Bright Data credits while the project is not under active development. Everything
> still runs on demand — from the terminal, or from the repository's Actions tab — and the
> dashboard says "runs on demand" rather than claiming a cadence it is not keeping.
> Re-enable by uncommenting the `schedule:` block and setting `cadence_hours` in
> `docs/data/schedule.json` back to 12.

---

## The pipeline

The interesting part of this project is not the scrape. It is everything that happens
after a site changes.

```
DISCOVER      a URL is proposed, classified, and gated before a credit is spent
   ↓
SCRAPE        one Scraper Studio collector per newsroom layout
   ↓
VALIDATE      every run is checked against one output contract
   ↓
DETECT        a break is separated from a failed run: only one of them is repairable
   ↓
HEAL          the contract's own diagnosis becomes the heal prompt. No human writes it
   ↓
RE-SCRAPE     the repair is verified by re-running, because "done" is not proof
   ↓
UNDERSTAND    topics classified, then ranked by independent cross-firm coverage
   ↓
PRODUCT       a dashboard that answers a question no single newsroom can
```

Every stage below is a real file you can run.

---

## 1. Discover

Anyone can propose a source. It is assessed before a credit is spent building anything.

```bash
./scripts/onboard.py https://www.example-advisory.com/insights --dry-run   # classify only
./scripts/onboard.py https://www.example-advisory.com/insights             # build + register
```

The same check runs in the browser from the **Add a source** tab, via
`api/check-source.mjs` on Vercel. Building a collector takes minutes, so that stays a
terminal command; deciding whether a source *qualifies* takes two seconds.

**Three refusals are absolute**, enforced in code and pinned by
`tests/test_onboard_gate.py`:

| Refused | Why |
|---|---|
| Government sites | Barred by rule 7. Rejected on host suffix as well as on the classifier's judgement, because a model can be wrong and the rule does not depend on its opinion |
| Login-walled content | Barred by rule 6. Nothing here authenticates, bypasses a login, or reuses a session cookie |
| Paywalled content | Barred by rule 6 |

**HTTP 403 is not a refusal.** `crowe.com` and `marcumllp.com` both reject a plain request
and both work through Bright Data's unblocking layer. `gate()` never sees the HTTP status,
and a test asserts it never will.

> Being blocked as a bot is a transport problem, and Bright Data solves it.
> Being behind a login is a permission boundary, and we stop there.

## 2. Scrape

One collector per newsroom layout, registered in
[`scripts/collectors.json`](scripts/collectors.json).

```bash
./scripts/run_fleet.sh          # run every collector, merge, validate
```

**Why not one collector for all twelve?** Scraper Studio generates extraction code against
a specific site. We tried the other way: twelve URLs through a single RSM-built collector,
of which eleven returned nothing, then a heal asked to "cover all of them" that ran for
forty minutes and returned `status: error`. The collector was left untouched, which is
worth knowing on its own — heal is non-destructive.

Concurrency is 2. At 5, seven of thirteen sources came back with
`Crawler error: Navigation failed ... too many`. Running a collector does not consume an
AI-Flow generation slot, but it is rate limited at the crawler.

## 3. Validate

[`scripts/validate.py`](scripts/validate.py) is the single definition of healthy output,
evaluated **per source** so one firm's redesign does not implicate the fleet.

Three findings that shaped it, each from a real failure:

**A source that disappears must not disappear from the report.** A site returning no
envelope produces no rows and no source, so it was invisible. The validator now takes the
list of URLs the run was asked to cover.

**Partial data is not always a defect.** BDO's listing mixes dated articles with evergreen
podcast hubs and eBooks that carry no date. The contract flagged 47% date coverage as a
break, sent `heal` after it, and `heal` correctly changed nothing — the scraper was fine
and the contract was wrong. Coverage below 25% is a break; partial coverage is content.

**A row with no title and no URL is not an article.** That rule catches extraction noise
the original contract accepted.

## 4. Detect

The distinction the whole loop depends on:

| Signal | Diagnosis | Exit | Action |
|---|---|---|---|
| Errors outnumber usable rows | run failure | 1 | re-run, never heal |
| Source produced no envelope at all | never ran | 1 | re-run, never heal |
| Clean run, zero rows | broken selector | 2 | heal |
| Clean run, field coverage collapsed | broken selector | 2 | heal |

A partially rate-limited run returns a handful of rows and looks *identical* to a scraper
that stopped iterating. BDO once returned 1 row from 17 envelopes — 16 were errors. Row
count cannot tell you which it is; only the cause can.

Healing a scraper that works is the most expensive mistake this system can make: it spends
credits and can leave a working collector worse than it started.

## 5. Heal

```bash
./scripts/heal_loop.sh
```

`run → validate → (break) → heal → approve → re-run → validate → publish`

```bash
./scripts/heal_loop.sh              # unattended: heal, auto-approve, verify
REVIEW=1 ./scripts/heal_loop.sh     # stop at the approval gate instead
```

In review mode the loop stops once a fix is proposed and prints the collector to inspect, so
it can be accepted with `bdata scraper approve <id>` or discarded with
`bdata scraper approve <id> --reject`. CI runs unattended; a human debugging a stubborn
source usually should not.

The prompt is never hand-written. [`scripts/broken_sources.py`](scripts/broken_sources.py)
turns the contract's findings into one instruction per broken collector, and only for
sources that actually ran. Collector IDs never change, so a repair touches nothing
downstream. `MAX_HEAL_ATTEMPTS` is 2, which stopped an unsatisfiable contract from looping
forever.

## 6. Re-scrape

**A heal reporting `status: done` is not proof of repair.** BDO's heal completed, was
approved, saved, and changed nothing. The loop re-runs and re-validates instead of trusting
the status, which is the only reason that surfaced.

### Two verified repairs

| | Control page | Baker Tilly |
|---|---|---|
| Break | staged: classes renamed, headline nested deeper | **organic**, found on a routine run |
| Contract said | 0 articles extracted | `article_url` 0%, `published_date` 0% |
| After heal | **0 → 6 articles** | **0% → 100%** on both fields |
| Collector ID | `c_mt5tj2ej2p93igloht`, unchanged | `c_mt5vy4lr2psac64sae`, unchanged |

The control page (`docs/control/insights.html`) is hosted by this repository and broken on
purpose, so self-healing can be shown against a real markup change rather than a staged
schema extension. It is logged separately from repairs to real sources.

## 7. Understand

A feed of advisory articles is a newsreader, and nobody needs another one. The reason to
read twelve firms is that **agreement between independent firms carries information no
single site does**.

One firm publishing five times is marketing. Five firms publishing once each, in the same
fortnight, means something changed.

```bash
./scripts/classify_topics.py   # build a taxonomy, assign 1-3 labels per article
./scripts/signals.py           # rank subjects by independent cross-firm coverage
```

The first version matched topics with a hand-written dictionary of regexes — the same
maintenance burden this project argues against, so it was replaced by a classifier. The
patterns survive as an offline fallback, so a fork with no API key still builds a working
site.

## 8. Product

The dashboard answers three questions a reading list cannot.

**What happened?** A digest on the overview: what moved since the last one, what several
firms converged on, and what went quiet. `scripts/digest.py`.

**What are they actually saying?** A brief per subject rather than a list of links —
what the firms agree on, where they differ, and who it affects. Plus who published first
within a burst of coverage. `scripts/brief.py`.

**Does it apply to me, and what are they actually saying?** One input takes either a
question or a description of a business, and returns the part of the corpus that bears on it
with the firm behind each answer. `api/ask.mjs`, over data already collected — no vector
database, because 213 articles fit in a context window and retrieval would only add a way to
miss the right one.

**Which of these sites can actually be scraped?** A reliability scorecard built from the
repair log: what broke, whether the fix held, and which sources have never worked. It exists
only because the pipeline keeps a contract and records every repair attempt.

### Two things the numbers had to earn

**A lead is only a lead inside a burst.** The first version reported "RSM first by 439 days",
which is not a scoop — it is older, unrelated coverage of a perennial subject. A lead now
requires three or more firms publishing within 45 days of each other. Seven of ten subjects
report no lead at all, which is the honest answer.

**The control page is not a firm.** `docs/control/insights.html` is a fixture we wrote to
prove self-healing. Counting it as coverage inflated every consensus figure with our own
text, which would have made the product's central claim quietly false. It is excluded from
signals and briefs.


The dashboard leads with a **coverage matrix**: subjects down the side, firms across the
top, a mark where a firm covered a subject. Reading a row shows how broad the agreement is;
reading a column shows what one firm is pushing. Neither is visible on any single site.

| View | Answers |
|---|---|
| Overview | What moved this period, and in the five before it |
| Consensus | What is the profession converging on, and who is silent? |
| Top signals | What did each firm actually say about it? |
| Ask | A question, or your company profile — one input, either way |
| Articles | Everything collected, filterable by firm |
| Pipeline | Which sources are passing, broken, or could not run — and every repair |
| Add a source | Would this site qualify? |

---

## Where this came from

This project began as [Financial-News-Scrapers](https://github.com/omkar-334/Financial-News-Scrapers):
fourteen hand-written Python scrapers, one per firm, each with its own selectors, a
Playwright launcher carrying thirty Chrome flags, and a BeautifulSoup heuristic for
stripping navigation. `rsm.py` alone hardcodes an AEM endpoint six containers deep at
`/insights/_jcr_content/root/container/container/container_copy/cardlist.list.json`.

Every one of those files is a selector waiting to rot, and each rots independently. Here
that is one collector per site plus one shared contract, and adding a firm is one command
rather than one more file to maintain.

## Running it

```bash
npm install
cp .env.example .env          # BRIGHTDATA_API_KEY, and OPENAI_API_KEY for classification
./scripts/run_fleet.sh        # run + validate
./scripts/heal_loop.sh        # run, repair what broke, verify
uv run --with pytest --with pyyaml pytest tests/
```

CI can run it on demand and on any change to the control page
([`.github/workflows/scrape.yml`](.github/workflows/scrape.yml)). Set `BRIGHTDATA_API_KEY`
and `OPENAI_API_KEY` as repository secrets; without the latter, topic classification falls
back to patterns rather than failing the run.

## API reference

Endpoints, published data shapes, exit codes and environment variables:
**[API.md](API.md)**.

## Repository layout

| Path | What it is |
|---|---|
| `scripts/collectors.json` | the fleet registry: one collector per newsroom |
| `scripts/create_collector.sh` | build a collector and register it |
| `scripts/onboard.py` | classify a proposed URL, gate it, build, register |
| `scripts/run_fleet.sh` | run every collector, merge, validate |
| `scripts/validate.py` | the output contract, and the diagnosis heal is given |
| `scripts/heal_loop.sh` | run, repair what broke, re-run, verify |
| `scripts/broken_sources.py` | which sources are genuinely heal-worthy |
| `scripts/classify_topics.py` | LLM topic taxonomy and assignment |
| `scripts/signals.py` | rank subjects by independent cross-firm coverage |
| `scripts/brief.py` | write a plain-English brief per subject, plus lead-lag |
| `scripts/digest.py` | a periodic digest of what moved since the last one |
| `api/ask.mjs` | one natural-language entry point: a question, or a company profile |
| `scripts/reliability.py` | grade each source on how reliably it can be scraped |
| `scripts/verify_new_source.py` | run one newly built collector and record whether it works |
| `scripts/publish.py` | publish rows, contract report and repair log |
| `api/check-source.mjs` | in-browser eligibility check |
| `docs/` | the deployed site, its data, and the control page |
| `tests/` | 52 tests: contract, eligibility gate, publish, signals, workflows. No network |
| `hackathon/` | rules, tips, resources, coding-agent prompts |

Run artifacts under `results/` are gitignored: large and reproducible. What is committed is
the published dataset in `docs/data/` and the latest contract report.

## Example structured output

```json
{
  "title": "5 ways private companies can use an audit to unlock true strategic value",
  "summary": "Five ways audits provide insight beyond compliance.",
  "published_date": "2026-08-17",
  "article_url": "https://rsmus.com/insights/services/business-strategy/...",
  "tags": ["Audit", "Private equity"],
  "_firm": "rsmus.com"
}
```

Full dataset: [`docs/data/latest.json`](docs/data/latest.json) ·
contract report: [`docs/data/health.json`](docs/data/health.json) ·
repairs: [`docs/data/heals.json`](docs/data/heals.json)

## Scraping policy

Public article listing pages only. Government sites, login walls and paywalls are refused
in code, not worked around. Pages about private individuals are out of scope. Author
bylines are excluded at extraction time, the contract fails the run if one appears, and
`publish.py` strips them again before anything reaches the site.

## AI assistance disclosure

Required by rule 11. Built with Claude Code (Claude Opus 5) as a pair programmer: it wrote
the pipeline scripts, contract validator, dashboard and CI, and drove the Bright Data CLI.
Target selection, architecture and every scope decision were made by the author, who
reviewed all code before it was committed. Several agent proposals were rejected on the
author's direction, including an Indian government procurement target that turned out to be
barred by rule 7.
