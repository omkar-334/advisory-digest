# Scraper Studio Coding Agent Prompts
Source: https://docs.brightdata.com/datasets/scraper-studio/coding-agent-prompts
Saved: 2026-08-23

Full docs index: https://docs.brightdata.com/llms.txt

## Prerequisites
- Active Bright Data account (free signup, no card required)
- Coding agent with terminal access (Claude Code, Cursor, Codex)
- No prior CLI install needed; commands run through `npx`

## Quick build prompt

Replace `<TARGET_URL>` and `<FIELDS TO EXTRACT>` before executing:

```text
Build and run a Bright Data scraper. Run every Bright Data CLI command
through `npx -p @brightdata/cli` so nothing is installed globally.
Replace <TARGET_URL> and <FIELDS TO EXTRACT>, then do each step in
order and stop if a step fails:

1. Authenticate by running `npx -p @brightdata/cli bdata login`.
2. Create a Bright Data scraper for <TARGET_URL> that extracts:
   <FIELDS TO EXTRACT>. Report the Collector ID.
3. Run that scraper on the same URL and pretty-print the result.
```

Expected output: Collector ID (format `c_alphanumeric`) and a JSON array with the fields.

## Full build-run-heal-approve prompt

```text
Build, run, heal and verify a Bright Data scraper end to end. Run every
Bright Data CLI command through `npx -p @brightdata/cli` so nothing is
installed globally. Do every step in order and stop if a step fails:

1. Authenticate by running `npx -p @brightdata/cli bdata login`.
2. Create a Bright Data scraper for https://shopalto.xyz/product/aurora-wireless-headphones
   that extracts two fields: product name and price. Report the Collector ID.
3. Run that scraper on the same URL and pretty-print the result.
4. Heal the scraper in place to also capture description, image url and
   rating alongside existing name and price. Keep the same Collector ID,
   anchor the heal on the same URL and show the approval envelope.
5. When preview shows all five fields, approve the fix anchored on the same URL.
6. Run the scraper on the same URL again and confirm all five fields:
   name, price, description, image_url and rating.
```

Expected output: unchanged Collector ID throughout; final JSON with five fields per row.

## Key concepts

| Concept | Meaning |
|---|---|
| Collector ID | Unique id (`c_[alphanumeric]`) identifying a reusable scraper |
| Self-healing | Extend or repair an existing scraper in place, without rebuilding |
| Approval gate | Preview the proposed fix before approving it |
| Auto-approve | `--auto-approve` on heal, for unattended workflows |
