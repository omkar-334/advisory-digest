# Submission answers

Copy-paste into the form. Live demo: https://advisory-digest.vercel.app
Repository: https://github.com/omkar-334/advisory-digest

---

## What does your project do?

Advisory Digest reads twelve accounting and advisory firm newsrooms at once and ranks
subjects by how many firms covered each one independently.

A single firm's newsroom tells you what that firm thinks. Twelve tell you what the
profession is reacting to. One firm publishing five times about a topic is marketing; five
firms publishing once each in the same fortnight means something changed — a rule moved, a
deadline shifted, an audit position hardened. That signal does not exist on any single site,
which is the entire reason to collect twelve.

The dashboard leads with a coverage matrix: subjects down the side, firms across the top, a
mark where a firm covered a subject. Reading a row shows how broad the agreement is; reading
a column shows what one firm is pushing. The gaps are as informative as the marks.

Underneath, thirteen Bright Data collectors run every twelve hours, are checked against one
output contract, and repair themselves when a firm rebuilds its site.

---

## What problem does your project solve, and who is it for?

**For:** finance leads, controllers, and founders at mid-market companies, plus the
accountants advising them.

**The surface problem:** staying current on tax, audit and compliance guidance means
checking a dozen firm newsrooms by hand. Nobody does that, so guidance gets found late,
usually by an auditor.

**The real problem, and the one this project is actually about:** scrapers rot. This project
began as a repository of fourteen hand-written Python scrapers, one per firm, each with its
own selectors, a Playwright launcher carrying thirty Chrome flags, and a BeautifulSoup
heuristic for stripping navigation. RSM's alone hardcodes an AEM endpoint six containers
deep at `/insights/_jcr_content/root/container/container/container_copy/cardlist.list.json`.
Fourteen files, fourteen independent failure modes, and each one breaks silently.

Here that is one collector per site plus one shared contract. When a site changes, the
contract catches it and Scraper Studio repairs the scraper in place. Adding a firm is one
command instead of one more file to maintain forever.

---

## How did you use Scraper Studio in your project?

**What we scrape:** the public insights and newsroom listing pages of twelve accounting and
advisory firms — RSM, BDO, PwC, Grant Thornton, Crowe, Baker Tilly, CLA, CohnReznick,
EisnerAmper, Marcum, Plante Moran and Withum — extracting title, summary, publication date,
article URL and topic tags. Public pages only, and author bylines are excluded at extraction
time.

**Why Scraper Studio is unavoidable here.** Bright Data ships 800+ pre-built scrapers and
none covers mid-market accounting newsrooms, so there is nothing off the shelf to fall back
on. Two of the twelve (`crowe.com`, `marcumllp.com`) return HTTP 403 to a plain request and
work correctly through the unblocking layer, so that layer is load-bearing rather than
decorative.

**How it fits, end to end.** Everything is driven from the terminal by a coding agent; the
dashboard is only for reading the output.

1. `bdata scraper create <url> "<description>"` builds a collector per newsroom layout. A
   self-serve path (`scripts/onboard.py`, and an equivalent endpoint behind the dashboard's
   *Add a source* tab) classifies any proposed URL with an LLM and refuses government sites,
   login walls and paywalls **before** a credit is spent generating anything.
2. `bdata scraper run` executes the fleet; output is merged and checked against one contract
   in `scripts/validate.py`.
3. When the contract breaks, its own diagnosis becomes the prompt for
   `bdata scraper heal` — no human writes the fix. `REVIEW=1` stops at the approval gate so
   a proposed fix can be accepted with `bdata scraper approve` or discarded with `--reject`;
   CI runs unattended.
4. The structured output powers the product: an LLM assigns topics, then subjects are ranked
   by how many distinct firms covered them.

**What it did when a site changed under it.** Three repairs are logged publicly on the
dashboard, and they are deliberately not all successes:

- **Control page** — we host a newsroom page in the repository, renamed its CSS classes and
  nested the headline one level deeper, and pushed. The collector went from 6 articles to 0,
  the contract failed with exit 2, heal repaired it unattended, and it returned 6 again.
  Same collector ID throughout.
- **Baker Tilly** — an organic break nobody staged. The contract found `article_url` and
  `published_date` both empty on 20 of 20 articles. After healing, both were at 100%.
- **BDO** — heal ran, reported `status: done`, and changed nothing. Investigating showed the
  scraper was fine: BDO's listing mixes dated articles with evergreen podcast hubs and
  eBooks that carry no date, and our contract had wrongly assumed every item is dated. We
  fixed the contract, not the scraper.

That third one is why the loop re-runs and re-validates instead of trusting a `done` status,
and why it separates a **failed run** from a **broken selector**. A rate-limited run returns
a handful of rows and looks identical to a scraper that stopped iterating — BDO once
returned 1 usable row out of 17 envelopes, 16 of which were errors. Healing a scraper that
works is the most expensive mistake this system can make, so run failures exit 1 and are
re-run, never healed.

---

# Feedback for the Bright Data team

## How was the CLI to work with?  **4 / 5**

## How easy was it to get your first scrape running?  **5 / 5**

From `npx` to a working collector returning clean structured JSON took about four minutes,
with no dashboard visit and no config file. `bdata scraper create <url> "<what I want>"` is
genuinely the shortest path from an idea to structured data we have used.

## What was the most frustrating thing you hit while building with Scraper Studio or the CLI?

**A 600-second client-side poll timeout is reported as a failure when the build actually
succeeded.** `scraper create` returned `poll_failed` with
`Timeout after 600 seconds waiting for AI generation` for Grant Thornton and Plante Moran.
Grant Thornton's collector was complete server-side and returns 20 clean rows — we nearly
threw away a working collector because the CLI told us it had failed. Plante Moran's really
was dead. Nothing in the output distinguishes the two.

Suggestions: make the envelope say the collector may still be generating and offer a
`scraper status <id>`; or have `create` resume polling an existing collector rather than
only reporting failure.

**The 3-job AI-Flow cap leaves undeletable debris.** Exceeding it fails the create *after*
the template is allocated, leaving a half-built collector that the CLI itself says can only
be removed in the web UI. We accumulated three of these. A `scraper delete` command, or
automatic cleanup of a collector that never began generating, would fix it.

## Where did you get stuck for the longest, and what got you unstuck?

**Forty minutes on a heal that could never have worked.** We assumed one collector could
cover twelve firm layouts and that `heal` would generalise it — the prompt asked it to
"rewrite the extraction to find article cards generically across all of them". It ran for
forty minutes through `code_fixer` and returned `status: error`.

What got us unstuck was reading the demo repository's own advice more carefully: a hundred
pages "collapse into roughly four layout families". Scraper Studio generates extraction code
against a *specific* site, and heal repairs a collector against *its own* target. The fix
was architectural — one collector per layout, sharing one contract and one repair loop.

Two things would have saved that time. First, documentation stating plainly that a collector
is bound to the layout it was created against and that heal will not port it to unrelated
domains. Second, and more useful: **reject an out-of-scope heal prompt in seconds rather
than failing after forty minutes.** The planner clearly understood the request; it could
have said "this asks the collector to handle domains it was not built for" immediately.

Credit where due: the collector was left completely untouched by the failed heal. Discovering
that heal is non-destructive made us far more willing to run it unattended in CI.

## How was the overall developer experience? What would you change?

The core loop — create, run, heal, approve — is the best version of this we have used, and
`--auto-approve` made a genuinely unattended CI job straightforward. Notes, roughly in order
of how much they cost us:

1. **Distinguish a run failure from an empty extraction in the output.** Under concurrency,
   runs returned envelopes shaped `{input, error, error_code}` mixed in with real data. To a
   naive consumer that is indistinguishable from a scraper extracting nothing, and we had to
   teach our contract the difference to stop it dispatching heals against healthy collectors.
   A top-level `status` and `error_count` on the run envelope would make this obvious.

2. **Document the crawler rate limit separately from the AI-Flow cap.** We knew about the
   3-job generation cap and assumed `run` was unaffected. At concurrency 5, seven of thirteen
   sources came back with `Crawler error: Navigation failed ... too many`. The two limits are
   different and only one is documented.

3. **`heal` returning `done` is not a guarantee of repair.** BDO's heal completed the full
   chain including `user_approval` and `save_new_template` and changed nothing measurable.
   We now always re-run and re-validate, which is correct practice anyway — but a
   `changed: true/false`, or a diff of what the fix altered, would make that verifiable
   rather than inferred.

4. **Output shape is not stable across heals.** One collector returned rows nested under a
   generated key and, after healing, returned them as a flat array. Anything consuming the
   output has to normalise defensively. A documented envelope contract would help.

5. **The `.gov` block is right but silent.** `Domain not allowed` with HTTP 400 is correct
   policy, but it arrives after the template is created and does not say *why* the domain is
   disallowed. One sentence in the error would have saved a confused ten minutes.

Best thing about the product: `create` from one sentence of natural language genuinely works,
across a dozen different enterprise CMSs, without a single selector being written by hand.
That is the part that felt like the future.
