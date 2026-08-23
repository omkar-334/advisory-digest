# Changelog

## 2026-08-23

Built for Into the Scrape-Verse. Live at https://advisory-digest.vercel.app

### The pipeline
- **Discover** `scripts/onboard.py` and `api/check-source.mjs`: classify a proposed URL,
  gate it, build and register a collector. Government sites, login walls and paywalls are
  refused in code; a 403 is explicitly not a refusal.
- **Scrape** `scripts/run_fleet.sh` over `scripts/collectors.json`: one collector per
  newsroom layout, thirteen in total.
- **Validate** `scripts/validate.py`: one output contract, evaluated per source.
- **Detect** run failures separated from broken selectors, because only one is repairable.
- **Heal** `scripts/heal_loop.sh`: the contract's own diagnosis becomes the heal prompt.
  Unattended by default, `REVIEW=1` to stop at the approval gate.
- **Understand** `scripts/classify_topics.py` and `scripts/signals.py`: LLM topic taxonomy,
  then ranking by independent cross-firm coverage.
- **Product** a dashboard leading with a coverage matrix, refreshed every 12 hours by CI.

### Verified repairs
- Control page: staged markup change, 0 → 6 articles, collector unchanged.
- Baker Tilly: organic break found on a routine run, `article_url` and `published_date`
  both 0% → 100%, collector unchanged.
- BDO: heal ran, reported `done`, and correctly changed nothing. The contract was wrong,
  not the scraper. Recorded rather than hidden.

### Corrections made along the way
- One collector cannot cover twelve layouts. A heal asked to generalise ran for forty
  minutes and returned `status: error`. The collector was untouched: heal is non-destructive.
- A source returning no envelope was invisible to the contract. It now takes the list of
  URLs the run was asked to cover.
- Partial field coverage is not always a defect: BDO's listing mixes dated articles with
  evergreen podcast hubs and eBooks. Below 25% is a break; partial coverage is content.
- Running collectors concurrently is rate limited at the crawler, not just at generation.
  At concurrency 5, seven of thirteen sources failed. Now 2.
- `publish.py` refused nothing: a failed CI scrape published zero rows over a good dataset.
  It now refuses to overwrite a non-empty dataset with an empty one.
- A 600s CLI poll timeout is not a failed collector. Grant Thornton reported `poll_failed`
  and returns 20 clean rows. Run it before rebuilding.

### Security and hygiene
- API key moved out of a plaintext `api.txt` into a gitignored `.env`.
- Run artifacts untracked: 26,309 lines of reproducible output removed from git.
- 28 tests, no network required, covering the contract and the eligibility gate.

### Environment notes
- Bright Data rejects `.gov.in` with `Domain not allowed`; hackathon rule 7 bars government
  targets outright.
- `crowe.com` and `marcumllp.com` return 403 to a plain request and work through Bright
  Data's unblocking layer.
- Bright Data caps AI-Flow at 3 concurrent generation jobs; exceeding it leaves half-built
  collectors that can only be deleted in the web UI.
