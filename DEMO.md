# Demo runbook

Ninety seconds, terminal on the left, https://advisory-digest.vercel.app on the right.
The point to land: the scraper is not finished when it runs, it is finished when it breaks
and repairs itself.

## 0. The before (10s)

Show `Financial-News-Scrapers`: fourteen Python files, one per firm.

> "Fourteen scrapers, fourteen sets of selectors. RSM's is an AEM JSON endpoint six
> containers deep. Every one of these rots independently."

## 1. The after (15s)

Show the dashboard. Articles across firms, filterable, with a Pipeline health tab.

> "One collector. One contract. Same coverage."

```bash
echo $COLLECTOR_ID          # c_mt5sgta91r4gozaifs
```

## 2. Break something real (20s)

Do not stage a schema extension. Change the markup of a page we control.

```bash
# rename the class the scraper matches on
sed -i '' 's/insight-card/insight-panel/g; s/insight-title/headline/g' docs/control/insights.html
git commit -am "control: rename card classes" && git push
```

The push triggers `.github/workflows/scrape.yml` (it watches `docs/control/**`).

## 3. Watch the contract catch it (15s)

```bash
./scripts/run_fleet.sh; echo "exit=$?"       # 2 = heal-worthy, 1 = run failed
```

Show the diagnosis. Point out that it names the source, and that this text is not
hand-written: it is what gets sent to `heal`.

## 4. Repair, unattended (25s)

```bash
./scripts/heal_loop.sh
```

Narrate while it runs:

> "The heal prompt is the validator's own diagnosis. Nobody typed it. The Collector ID does
> not change, so nothing downstream knows a repair happened."

## 5. Green again (15s)

```bash
./scripts/run_fleet.sh; echo "exit=$?"       # 0 = contract satisfied
python3 scripts/publish.py
```

Refresh the dashboard. Pipeline health flips to passing and the heal appears on the timeline
with the diagnosis that caused it.

> "That is the whole product: a pipeline that fixes itself while you sleep, and a wall of
> green checks to prove it."

## Facts worth having on hand

| | |
|---|---|
| Collector ID | `c_mt5sgta91r4gozaifs` |
| Sources | 12 accounting and advisory firm newsrooms |
| Blocked to a naive request | `crowe.com`, `marcumllp.com` (HTTP 403) |
| Pre-built scraper available | none, this is long tail |
| Government targets | barred by rule 7, and Scraper Studio returns `Domain not allowed` |
| Personal data | none collected; contract fails the run if a byline appears |

## Do not forget

- Keep `.env` out of the recording.
- Submission needs: public repo, README, example output, demo video, Scraper Studio explanation.
- Disclose AI assistance (rule 11). It is already in the README.
