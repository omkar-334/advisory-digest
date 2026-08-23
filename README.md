# Advisory Digest

One feed of tax, audit and compliance guidance from accounting and advisory firm newsrooms,
collected by a fleet of Bright Data Scraper Studio collectors that repair themselves when a
firm rebuilds its site.

**Live demo:** https://advisory-digest.vercel.app
**Collectors:** [`scripts/collectors.json`](scripts/collectors.json) (RSM: `c_mt5sgta91r4gozaifs`)

Built for Into the Scrape-Verse (WeMakeDevs x Bright Data), 17-23 August 2026.

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

We established this the expensive way. An early heal was asked to generalise the RSM collector
across eleven unseen layouts; it ran for forty minutes and returned `status: error`. The
collector was left untouched, which is worth knowing on its own: heal is non-destructive.

So the fleet is one collector per newsroom layout, registered in `scripts/collectors.json`.
What is shared across the fleet is the contract and the repair loop, which is where the
leverage actually is.

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

## Running it

```bash
npm install
cp .env.example .env          # add your Bright Data API key
./scripts/run_scraper.sh      # run + validate
./scripts/heal_loop.sh        # run, and repair in place if the contract breaks
uv run --with pytest pytest tests/
```

## Data ethics

Public listing pages only. No login, no paywall, no government sites (barred by rule 7 and
blocked by Scraper Studio). Author bylines are excluded at extraction time, the contract fails
the run if they ever appear, and `scripts/publish.py` strips them again before anything reaches
the published site.

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
