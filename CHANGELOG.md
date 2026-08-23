# Changelog

## 2026-08-23

### Added
- `Advisory Digest`: one feed of tax, audit and compliance guidance from twelve accounting
  and advisory firm newsrooms. Live at https://advisory-digest.vercel.app
- Bright Data CLI pinned locally (`@brightdata/cli@0.3.5`); the whole pipeline is driven
  from the terminal.
- `scripts/validate.py`: the output contract. Evaluated per firm, and fed the list of URLs
  the run was asked to cover so a source that returns nothing is still judged. Its diagnosis
  is handed verbatim to `bdata scraper heal`, which is what makes the loop unattended.
- `scripts/heal_loop.sh`: run, validate, heal, re-run, re-validate, record the event.
- `scripts/publish.py`: publishes rows, contract report and heal history to the site.
  Strips byline-shaped fields and deduplicates on canonical article URL.
- Dashboard with a Feed view and a Pipeline health view showing per-firm contract status
  and the self-healing timeline.
- `docs/control/insights.html`: a newsroom page we control, so the heal can be demonstrated
  against a real markup change rather than a staged schema extension.
- `.github/workflows/scrape.yml`: daily cron, plus a trigger on any change to the control page.
- `tests/test_contract.py`: seven tests, no network required.

### Fixed
- The contract could not see a source that returned no envelope at all: it produced no rows,
  so it created no entry and vanished from the report. Silent disappearance is the most
  dangerous failure mode a scraper has. The validator now takes the expected URL list.
- Deduplicated published rows. A discovery-style collector reaches the same article by
  several paths, which produced 36 duplicates in 73 rows.
- `gh` was creating repositories under the work account from any non-interactive context.
  The `gh()` zsh function in `~/.zshrc` routes by directory correctly, but it is only a shell
  function, so `rtk`'s command rewriting, scripts and cron bypassed it and hit the default
  config (`user: omkar-334k`). Replaced with an executable shim at `~/.local/bin/gh` that
  performs the same check, and prepended that directory to `PATH`.

### Security
- Moved the Bright Data API key out of a plaintext `api.txt` into a gitignored `.env`,
  and deleted `api.txt`. `.env.example` committed in its place.

### Findings
- Bright Data rejects `.gov.in` domains with `Domain not allowed` (HTTP 400) before AI
  generation starts. Hackathon rule 7 bars government targets outright, so `eprocure.gov.in`
  and similar were never viable.
- `rbi.org.in` is allowed and works well, including automatic discovery of circular detail
  pages, but government-adjacent targets were dropped on the same rule.
- `nseindia.com` returns 404 to a plain request and needs session cookies, so the NSE/BSE
  target set was ruled out on blocking and terms-of-service grounds.
- `crowe.com` and `marcumllp.com` return HTTP 403 to a plain request, which is what the
  Bright Data unblocking layer is for.
- A collector created against one firm does not generalise to eleven other layouts on its
  own. That is the gap the heal loop exists to close, and it is the honest finding of the day.
- RTK's command filtering must never be redirected into a file: `head file > out` wrote RTK's
  own truncation marker into `out`, corrupting a URL list.
