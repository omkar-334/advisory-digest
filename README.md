# Advisory Digest

One feed of tax, audit and compliance guidance from twelve accounting and advisory firms,
collected by a single Bright Data Scraper Studio collector that repairs itself when a firm
rebuilds its newsroom.

Built for the Into the Scrape-Verse hackathon (WeMakeDevs x Bright Data).

## The problem it solves

A finance lead who wants to stay current on guidance has to check a dozen firm newsrooms by
hand. Nobody does that, so guidance gets found late, usually by an auditor. This puts all of
it on one page, refreshed on a schedule.

The maintenance problem underneath is the interesting one. This repository started from
[Financial-News-Scrapers](https://github.com/omkar-334/Financial-News-Scrapers), fourteen
hand-written Python scrapers with per-firm selectors, a Playwright launcher carrying thirty
Chrome flags, and a BeautifulSoup heuristic for stripping navigation. Every one of those
files is a selector waiting to rot. Here that is replaced by one collector and one contract.

## Why Scraper Studio is doing real work

Bright Data ships 800+ pre-built scrapers. None covers mid-market accounting firm newsrooms,
so there is nothing off the shelf to fall back on. Two of the twelve targets
(`crowe.com`, `marcumllp.com`) return HTTP 403 to a plain request, so the unblocking layer is
load bearing rather than decorative.

Every page is public, needs no login, sits behind no paywall. Author bylines are excluded at
extraction time and the contract fails the run if they ever appear.

## The self-healing loop

`scripts/validate.py` is the single definition of healthy output, evaluated per firm. When a
firm's selectors stop matching, the validator's own diagnosis becomes the prompt handed to
`bdata scraper heal`. No human writes the fix:

```
run -> validate -> (violation) -> heal --auto-approve -> re-run -> validate -> publish
```

The Collector ID never changes, so a repair touches nothing downstream.

## Proving it is not staged

Target sites rarely redesign themselves during a hackathon, which is why most self-healing
demos are really a staged schema extension. `docs/control/insights.html` is a newsroom page
served from this repository's own GitHub Pages site. We scrape it, rename its CSS classes in
a commit, and let the scheduled job detect the break and repair it with no human in the loop.

## Running it

```bash
npm install
cp .env.example .env          # add your Bright Data API key
./scripts/run_scraper.sh      # run + validate
./scripts/heal_loop.sh        # run, and repair if the contract breaks
```

## Layout

| Path | Purpose |
|---|---|
| `scripts/` | pipeline steps: create, run, validate, heal |
| `tests/` | contract tests |
| `results/` | per-run logs, JSONL rows, summary JSON |
| `docs/` | the published site: dashboard, control page, published data |
