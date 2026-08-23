# Regulatory Radar

A self-healing data pipeline for Indian financial regulation, built on Bright Data
Scraper Studio for the Into the Scrape-Verse hackathon.

RBI issues a circular. The large accounting and advisory firms publish their
interpretation of it days later. Those two streams live on completely different sites,
in completely different shapes, and nobody correlates them. This does.

## Why this target

Bright Data ships 800+ pre-built scrapers. None of them covers `rbi.org.in` or the
newsrooms of mid-market accounting firms, so Scraper Studio is doing real work here
rather than duplicating something off the shelf.

Every page scraped is public, requires no login, sits behind no paywall, and carries no
personal data. Author names are explicitly excluded at extraction time.

## The self-healing loop

`scripts/validate.py` is the single definition of healthy output. CI runs it after every
scrape. When the contract breaks, the validator's own diagnosis becomes the prompt handed
to `bdata scraper heal`, so no human writes the fix:

```
run -> validate -> (violation) -> heal --auto-approve -> re-run -> validate -> commit
```

The Collector ID never changes, so nothing downstream is touched by a repair.

## Proving it is not staged

Target sites rarely redesign themselves during a hackathon, which makes most self-healing
demos a staged schema extension. `docs/control/tenders.html` is a page in this repo,
served from GitHub Pages. We scrape it, rename its CSS classes in a commit, and let CI
detect the break and repair it unattended.

## Layout

- `scripts/` executable pipeline steps
- `tests/` contract tests
- `results/` per-run logs, JSONL rows, and summary JSON (heavy outputs gitignored)
- `docs/` the GitHub Pages site: dashboard plus the control page
