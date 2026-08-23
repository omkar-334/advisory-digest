# YouTube script — 2:50

The form allows 3 minutes and asks for: what the project does, tech stack and architecture,
a demo, and optionally what you learned. This covers all four.

## Before you hit record

**Recording.** macOS `Cmd+Shift+5` → Record Selected Portion, or QuickTime → New Screen
Recording. Record system audio if you narrate live; otherwise record silent and voice over
it afterwards. 1080p is plenty.

**Layout.** Terminal on the left half, https://advisory-digest.vercel.app on the right.
Browser at ~90% zoom so the whole coverage matrix fits without scrolling.

**Never on screen:** the `.env` file, the Bright Data or OpenAI key, the Vercel environment
page. If you open an editor, close the `.env` tab first.

## Setup commands (run these before recording, not during)

```bash
cd ~/personal/mine/scrape

# 1. Make sure the fleet is healthy, so the Pipeline tab is green when you start.
./scripts/run_fleet.sh; echo "exit=$?"        # want 0

# 2. If anything is broken, repair it now rather than on camera.
./scripts/heal_loop.sh

# 3. Refresh the published site so the dashboard matches what you are about to say.
python3 scripts/classify_topics.py            # needs OPENAI_API_KEY
python3 scripts/signals.py
python3 scripts/publish.py
git add -A && git commit -m "data: refresh before recording" && git push

# 4. Reset the control page to v1 so you can break it live.
git checkout docs/control/insights.html
grep -c story-panel docs/control/insights.html   # want a non-zero count

# 5. Clear the terminal and load the environment.
set -a && . ./.env && set +a && clear
```

Wait for Vercel to finish deploying (~30s) and hard-refresh the dashboard before recording.

Timings below are spoken duration. Read at a normal pace, not a rush.

---

## [0:00 – 0:20] The problem
**Screen:** github.com/omkar-334/Financial-News-Scrapers — scroll the file list slowly.

> Last year I wrote fourteen web scrapers, one for each of the big accounting firms.
> Fourteen files, fourteen sets of CSS selectors. This one hardcodes a JSON endpoint six
> containers deep in an enterprise CMS.
>
> Every one of these is a scraper waiting to break. And when they break, they don't throw an
> error — they just quietly return nothing.

**Screen:** cut to the live dashboard, Consensus tab.

> This is the same coverage, rebuilt on Bright Data Scraper Studio, and it repairs itself.

---

## [0:20 – 0:45] What it does
**Screen:** the coverage matrix. Let it sit. Point at the top rows.

> Twelve accounting firm newsrooms in one place. But a feed of articles is just a
> newsreader, so it isn't the product.
>
> This is. Subjects down the side, firms across the top, a mark where a firm covered that
> subject. Business tax compliance — six firms, independently. AI in auditing — five.
>
> One firm publishing five times is marketing. Five firms publishing once each, in the same
> fortnight, means something actually changed. That signal doesn't exist on any single
> firm's website. It only appears when you read all twelve at once.
>
> If you're a CFO or a controller, that's the difference between hearing about a rule change
> now, and hearing about it from your auditor in March.

---

## [0:45 – 1:10] Tech stack and architecture
**Screen:** `scripts/collectors.json`, then `scripts/validate.py`.

> Thirteen Bright Data collectors, one per newsroom layout, all built from the terminal with
> `bdata scraper create` — a URL and a sentence of English, no selectors written by hand.
>
> Everything hangs off one file: the output contract. It defines what healthy data looks
> like, per source, and it runs after every scrape.
>
> That contract does something I think is the important idea here. It tells the difference
> between a scraper that broke and a run that failed. Those look identical — both give you
> empty output — but only one of them should be repaired. Healing a scraper that actually
> works is the most expensive mistake this system can make.

---

## [1:10 – 2:05] Demo: break it, watch it fix itself
**Screen:** terminal.

> So let's break something. This is a newsroom page I host in the repo, so I can change it
> for real instead of faking a demo.

```bash
sed -i '' 's/story-panel/article-block/g' docs/control/insights.html
git commit -am "control: newsroom redesign" && git push
```

> Renamed the CSS classes and nested the headline a level deeper. That's a redesign, the
> same thing a real firm does without telling you.

```bash
./scripts/run_fleet.sh; echo "exit=$?"
```

**Wait for exit 2. Point at the diagnosis on screen.**

> Exit 2. Six articles, now zero. And read that diagnosis — I didn't write it. The contract
> generated it, and it's exactly what gets handed to Bright Data's healing.

```bash
./scripts/heal_loop.sh
```

**While it runs:**

> No human in this loop. The contract's own finding becomes the heal prompt, Scraper Studio
> rewrites the extraction, approves it, and saves it. The collector ID never changes — so
> nothing downstream even knows a repair happened.

**When it goes green:**

> Back to six. Same collector, same ID, no code touched.

---

## [2:05 – 2:35] The part I'd want a judge to see
**Screen:** Pipeline tab, scroll to the repair log.

> Three repairs are logged here, and they're deliberately not all successes.
>
> The first is the one you just watched. The second is Baker Tilly — a real break nobody
> staged: twenty articles with zero URLs and zero dates. Healed to a hundred percent on both.
>
> The third is the interesting one. BDO. Heal ran, reported success, and changed absolutely
> nothing. Because the scraper was never broken — my contract was wrong. BDO's page mixes
> dated articles with podcast series that have no date, and I'd assumed everything was dated.
>
> So I fixed the contract, not the scraper. And that's why this loop always re-runs and
> re-checks instead of trusting a "done" status.

**Screen:** point at the cadence banner.

> Checked every twelve hours. It maintains itself.

---

## [2:35 – 2:50] Learning and growth
**Screen:** Add a source tab. Paste a `.gov` URL, click Check it, let the refusal appear.

> Last thing. Anyone can propose a source, and it gets assessed before a credit is spent.
> Government sites, logins and paywalls are refused in code — not worked around.
>
> The distinction I ended up caring most about: being blocked as a bot is a transport
> problem, and Bright Data solves it. Being behind a login is a permission boundary, and
> that's where we stop.

**Screen:** back to the matrix. Hold for two seconds.

---

## Shot list

| # | Screen | Have ready |
|---|---|---|
| 1 | Old repo file list | github.com/omkar-334/Financial-News-Scrapers |
| 2 | Consensus tab | scrolled so the top 6 matrix rows are visible |
| 3 | `collectors.json` + `validate.py` | open in the editor, no `.env` tab visible |
| 4 | Terminal | in the repo root, `.env` loaded, screen cleared |
| 5 | Pipeline tab | scrolled to the repair log |
| 6 | Add a source tab | `https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata` in the clipboard |

## If you run over 3 minutes
Cut the learning-and-growth section first (it's optional on the form), then trim the
architecture block to its last sentence. Never cut the break-and-heal demo — it is the
submission.

## Every command you run on camera, in order

```bash
# [1:10] break the control page for real
sed -i '' 's/story-panel/article-block/g' docs/control/insights.html
git commit -am "control: newsroom redesign" && git push

# wait ~30s for Vercel to redeploy, then:

# [1:25] the contract catches it
./scripts/run_fleet.sh; echo "exit=$?"        # 2 = a real break

# [1:40] repair it, unattended
./scripts/heal_loop.sh

# [1:55] confirm
./scripts/run_fleet.sh; echo "exit=$?"        # 0 = satisfied
python3 scripts/publish.py
```

Then refresh the dashboard and switch to the Pipeline tab.

## After recording: put the control page back

```bash
git checkout docs/control/insights.html
git commit -am "control: restore v1 markup" && git push
./scripts/heal_loop.sh        # heal it back to the original markup
```

## If a command is slow on camera

`run_fleet.sh` takes a few minutes across thirteen collectors and `heal_loop.sh` can take
five to fifteen. Do not sit in silence: either cut the dead time in the edit, or narrate the
architecture section over it. The `code_fixer` progress lines scrolling past are good
footage — that is Scraper Studio rewriting the extraction.

## It also runs itself

Worth one sentence on camera if you have room: the same loop runs in GitHub Actions on a
12-hour cron, and on any push that changes the control page.

```
.github/workflows/scrape.yml
```

Show the Actions tab with green checks if you have one by recording time. Run it manually
from **Actions → scrape and self-heal → Run workflow**, which also offers a *review* toggle
that stops at Bright Data's approval gate instead of auto-approving.

## Do not
- Show `.env`, the API key, or the Vercel environment page.
- Claim the fleet is fully green if it isn't at record time. Say what's passing.
- Re-record the whole thing if one command fails. Cut it and keep going — a real pipeline
  failing once on camera is more credible than a suspiciously clean take.
