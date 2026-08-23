# Changelog

## 2026-08-23

### Added
- Bright Data CLI pinned locally (`@brightdata/cli@0.3.5`), driven entirely from the terminal.
- `scripts/create_collector.sh`, `scripts/run_scraper.sh`, `scripts/heal_loop.sh`.
- `scripts/validate.py`: the output contract. Its diagnosis is fed back as the heal prompt,
  which is what makes the heal loop unattended.
- `docs/control/tenders.html`: a page we control, used to prove self-healing against a real
  markup change rather than a staged schema extension.

### Security
- Moved the Bright Data API key out of a plaintext `api.txt` into a gitignored `.env`.
  `api.txt` deleted, `.env.example` committed in its place.

### Findings
- Bright Data rejects `.gov.in` domains with `Domain not allowed` (HTTP 400) before AI
  generation starts. `eprocure.gov.in` is therefore not a viable target.
- `rbi.org.in` is allowed and works, including automatic discovery of circular detail pages.
- `nseindia.com` returns 404 to a plain request and requires session cookies, so the
  NSE/BSE target set was ruled out on both blocking and terms-of-service grounds.
