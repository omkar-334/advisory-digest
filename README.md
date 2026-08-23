# Advisory Digest

One feed of tax, audit and compliance guidance from accounting and advisory firm newsrooms,
collected by a fleet of Bright Data Scraper Studio collectors that repair themselves when a
firm rebuilds its site.

**Live demo:** https://advisory-digest.vercel.app
**Collectors:** [`scripts/collectors.json`](scripts/collectors.json) (RSM: `c_mt5sgta91r4gozaifs`)

Built for Into the Scrape-Verse (WeMakeDevs x Bright Data), 17-23 August 2026.

## What the data is actually for

A feed of advisory articles is a newsreader, and nobody needs another one. The reason to
collect a dozen firms rather than one is that **agreement between independent firms carries
information no single site does**.

One firm publishing five times about a topic is marketing. Five firms publishing once each,
in the same fortnight, means something changed. The Signals view ranks topics by how many
*distinct* firms covered them, so the dashboard answers a question you cannot ask any single
newsroom:

> Seven firms published on tariff accounting this month. What happened, and does it affect me?

That is the justification for the fleet. Without it, twelve collectors are just twelve
scrapers feeding a list.

`scripts/classify_topics.py` builds a canonical taxonomy from the corpus and assigns each
article one to three labels from it; `scripts/signals.py` then ranks topics by how many
independent firms cover them. A topic qualifies only when at least two distinct firms do.

The first version of this matched topics with a hand-written dictionary of regexes. That is
the same maintenance burden this project argues against, so it was replaced by a classifier.
The patterns survive as an offline fallback, so a fork with no API key still produces a
working site.

## Who it is for

A finance lead, controller or founder who needs to know when guidance changes has to check a
dozen firm newsrooms by hand. Nobody does that, so the change gets found late, usually by an
auditor. This puts all of it on one page, refreshed on a schedule, filterable by firm and topic.

## The problem underneath

This project started from [Financial-News-Scrapers](https://github.com/omkar-334/Financial-News-Scrapers):
fourteen hand-written Python scrapers, one per firm, each with its own selectors, a Playwright
launcher carrying thirty Chrome flags, and a BeautifulSoup heuristic for stripping navigation.
`rsm.py` alone hardcodes an AEM endpoint at
`/insights/_jcr_content/root/container/container/container_copy/cardlist.list.json`.

Every one of those files is a selector waiting to rot, and each rots independently. Here that
is replaced by one collector and one contract.

## How Bright Data Scraper Studio is used

| Step | Command |
|---|---|
| Build a collector from a description | `bdata scraper create <url> "<fields>"` |
| Run the fleet and validate it | `./scripts/run_fleet.sh` |
| Repair a collector when its site changes | `bdata scraper heal <collector> "<what broke>" --auto-approve` |
| Review or reject a proposed fix | `bdata scraper approve <collector> [--reject]` |

The Collector ID is the stable interface. A repair changes the scraper in place and leaves the
ID untouched, so nothing downstream is aware that anything happened.

### One collector per layout, not one collector for everything

Scraper Studio generates extraction code against a specific site. A collector built on RSM
returns nothing for BDO or Crowe, and `heal` will not bridge that gap: it repairs a collector
against **its own** target when that target changes.

We established this the expensive way. An early attempt fed twelve firm URLs to a single
collector built against RSM; eleven returned nothing. Healing it to "cover all of them" ran
for forty minutes and returned `status: error`. The collector was left untouched, which is
worth knowing on its own: heal is non-destructive.

So the fleet is one collector per newsroom layout, registered in `scripts/collectors.json`.
What is shared across the fleet is the contract and the repair loop, which is where the
leverage actually is: adding a firm means adding one collector, not another bespoke parser
with its own selectors to maintain.

## Proven self-healing run

A real markup change on a page we control, repaired without a human writing the fix:

| Stage | Result |
|---|---|
| Collector `c_mt5tj2ej2p93igloht` against v1 markup | 6 articles |
| Redesign pushed: classes renamed, headline nested one level deeper | site serving v2 |
| Same collector against v2 | **0 articles** |
| `scripts/validate.py` | exit 2, `0/1 sources healthy` |
| Heal prompt | generated from the contract's own diagnosis |
| `bdata scraper heal --auto-approve` | `status: done` |
| Same collector, same URL, after the repair | **6 articles** |

The Collector ID never changed, so nothing downstream was touched.

Two of the twelve targets (`crowe.com`, `marcumllp.com`) return HTTP 403 to a plain request,
so the unblocking layer is doing real work rather than decorating the pitch. And Bright Data
ships 800+ pre-built scrapers, none of which covers mid-market accounting firm newsrooms, so
there is nothing off the shelf to fall back on.

## The self-healing loop

`scripts/validate.py` is the single definition of healthy output, evaluated per firm. When a
firm's selectors stop matching, the validator's own diagnosis becomes the prompt handed to
`bdata scraper heal`. No human writes the fix.

```
run -> validate -> (violation) -> heal --auto-approve -> re-run -> validate -> publish
```

Two design decisions matter more than they look:

**The contract is evaluated per source, not per run.** One firm redesigning its site fails only
its own source, and the heal prompt names that firm instead of blaming the whole fleet.

**The contract knows which URLs it asked for.** A site that returns no envelope at all produces
no rows and no source, so it would otherwise be invisible. Silent disappearance is the most
dangerous failure mode a scraper has, so `validate.py` takes the expected URL list and reports
anything missing from the output.

## Proving it is not staged

Target sites rarely redesign themselves during a one-week hackathon, which is why most
self-healing demos are really a staged schema extension. `docs/control/insights.html` is a
newsroom page served from this repository's own site. We scrape it, rename its CSS classes in a
commit, and the push triggers CI to detect the break and repair it with no human involved.

## Example structured output

```json
{
  "title": "5 ways private companies can use an audit to unlock true strategic value",
  "summary": "Five ways audits provide insight beyond compliance.",
  "published_date": "2026-08-17",
  "article_url": "https://rsmus.com/insights/services/business-strategy/...",
  "tags": ["Audit", "Private equity"],
  "_firm": "rsmus.com",
  "_source": "https://rsmus.com/insights.html"
}
```

Full published dataset: [`docs/data/latest.json`](docs/data/latest.json).
Contract report: [`docs/data/health.json`](docs/data/health.json).

## Adding a source

The dashboard has an **Add a source** tab: paste a listing-page URL and get a verdict in a
couple of seconds, backed by `api/check-source.mjs` running on Vercel. Building a collector
takes several minutes, so that stays a terminal command; deciding whether a source *qualifies*
is instant, and no credits are spent on a target that was never going to pass.

To enable it on a deployment, set `OPENAI_API_KEY` in the Vercel project environment. Without
it the endpoint returns a clear "not configured" message rather than failing.


Anyone can propose a site. The pipeline decides whether it is eligible before spending a
credit on generating a scraper:

```bash
./scripts/onboard.py https://www.example-firm.com/insights --dry-run   # classify only
./scripts/onboard.py https://www.example-firm.com/insights             # build and register
```

```
fetch -> classify (LLM) -> gate -> create collector -> run -> validate -> register
```

Three rejections are absolute, and are enforced in code rather than left to judgement:

| Rejected | Why |
|---|---|
| government sites | barred by rule 7, and Scraper Studio returns `Domain not allowed` |
| login walls | barred by rule 6. Nothing here attempts to authenticate |
| paywalls | barred by rule 6 |

A **403 is not a rejection**. `crowe.com` and `marcumllp.com` both refuse a plain request and
both work through Bright Data's unblocking layer, which is the reason to route through it.
Pre-judging a target with `curl` would have thrown away two working sources.

Adding a firm is one command plus one line in `scripts/collectors.json`. No new parser, no
new selectors, which is the whole difference from maintaining a file per firm.

## Running it

```bash
npm install
cp .env.example .env          # add your Bright Data API key
./scripts/run_fleet.sh        # run every collector, validate against the contract
./scripts/heal_loop.sh        # run, and repair in place if the contract breaks
uv run --with pytest pytest tests/
```

## Scraping policy

What this project will and will not collect. These are commitments enforced in code and
pinned by tests in `tests/test_onboard_gate.py`, not preferences.

**Refused outright, by `scripts/onboard.py`:**

| Refused | Why |
|---|---|
| Government websites | Barred by hackathon rule 7. Scraper Studio also returns `Domain not allowed` for them. Rejected on the host suffix (`.gov`, `.gov.in`, `.gov.uk`, `.mil`, ...) as well as on the classifier's judgement, because a language model can be wrong and the rule does not depend on its opinion |
| Login-walled content | Barred by rule 6. **Nothing in this project attempts to authenticate, bypass a login, or reuse a session cookie.** A source behind a login is refused, not worked around |
| Paywalled content | Barred by rule 6 |
| Pages about private individuals | Out of scope regardless of the rules |
| Anything that is not an article listing | A single article or a homepage is not a source |

**An HTTP 403 is explicitly NOT a rejection.**

`crowe.com` and `marcumllp.com` both refuse a plain request and both work correctly through
Bright Data's unblocking layer, which is the reason to route through an unblocker in the
first place. Rejecting a candidate on status code would have silently discarded two working
sources. `gate()` therefore never sees the HTTP status, and a test asserts it never will.

The distinction matters and is easy to blur: **being blocked as a bot is a transport
problem that Bright Data solves. Being behind a login is a permission boundary, and we
stop there.**

**On the data itself:** public listing pages only. Author bylines are excluded at extraction
time, the contract fails the run if one ever appears, and `scripts/publish.py` strips them
again before anything reaches the published site.

## Layout

| Path | Purpose |
|---|---|
| `scripts/` | create, run, validate, heal, publish |
| `tests/` | contract tests, no network required |
| `results/` | per-run logs, JSONL rows, summary JSON |
| `docs/` | the deployed site: dashboard, control page, published data |
| `hackathon/` | rules, tips, resources, coding-agent prompts |

## AI assistance disclosure

Required by rule 11. This project was built with Claude Code (Claude Opus 5) acting as a pair
programmer: it wrote the pipeline scripts, contract validator, dashboard and CI workflow, and
drove the Bright Data CLI. Target selection, architecture and every scope decision were made by
the author, who reviewed all code before it was committed. Several of the agent's initial
proposals were rejected on the author's direction, including an Indian government procurement
target that turned out to be barred by rule 7.

## Repository layout

| Path | What it is |
|---|---|
| `scripts/collectors.json` | the fleet registry: one collector per newsroom |
| `scripts/create_collector.sh` | build a collector and register it |
| `scripts/onboard.py` | self-serve: classify a proposed URL, gate it, build, register |
| `scripts/run_fleet.sh` | run every collector, merge, validate |
| `scripts/validate.py` | the output contract, and the diagnosis heal is given |
| `scripts/heal_loop.sh` | run, repair what broke, re-run, verify |
| `scripts/broken_sources.py` | which sources are genuinely heal-worthy |
| `scripts/classify_topics.py` | LLM topic taxonomy and assignment |
| `scripts/signals.py` | rank subjects by independent cross-firm coverage |
| `scripts/publish.py` | publish rows, contract report and repair log to the site |
| `api/check-source.mjs` | the in-browser eligibility check |
| `docs/` | the deployed site and its committed data |
| `tests/` | contract and gate tests, no network required |

Run artifacts under `results/` are gitignored: they are large and reproducible. What is
committed is the published dataset in `docs/data/` and the latest contract report.
