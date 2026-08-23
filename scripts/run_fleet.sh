#!/usr/bin/env bash
# Run every collector in the fleet, merge the output, and validate it against the contract.
#
# Resumable: a collector whose output for this run already exists is skipped, so a run
# interrupted part-way can be finished by invoking this again with the same RUN_ID. Thirteen
# collectors take longer than most shells will sit still for, and re-scraping the ones that
# already succeeded wastes both time and credits.
#
# Concurrency is 2. Running a collector does not consume an AI-Flow generation slot, so it
# is not bound by the 3-job cap that applies to `create` and `heal` -- but it IS rate limited
# at the crawler. At 5, seven of thirteen sources returned
# "Crawler error: Navigation failed ... too many" and no data.
#
# Exit 0 = contract satisfied, 2 = a real break (heal-worthy), 1 = a run failed.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

CONCURRENCY="${FLEET_CONCURRENCY:-2}"
OUT=results/run_fleet
mkdir -p "$OUT" results/validate
STAMP="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
COMBINED="$OUT/fleet-$STAMP.json"
EXPECTED="$OUT/expected-$STAMP.txt"
LIST="$OUT/fleet-$STAMP.list"

python3 -c "
import json
for c in json.load(open('scripts/collectors.json'))['collectors']:
    if c.get('collector_id'):
        print(c['collector_id'], c['url'])
" > "$LIST"

if [ ! -s "$LIST" ]; then
  echo "no collectors with an id in scripts/collectors.json" >&2
  exit 1
fi

: > "$EXPECTED"
running=0
while read -r cid url; do
  [ -z "$cid" ] && continue
  echo "$url" >> "$EXPECTED"
  part="$OUT/part-$STAMP-$cid.json"
  if [ -s "$part" ]; then
    echo "[$STAMP] $cid -> already collected, skipping" | tee -a "$OUT/run.log"
    continue
  fi
  echo "[$STAMP] $cid -> $url" | tee -a "$OUT/run.log"
  (
    ./node_modules/.bin/bdata scraper run "$cid" "$url" \
      --timeout 900 --json --pretty -o "$part" </dev/null >>"$OUT/run.log" 2>&1
    rc=$?
    # Record the exit status beside the output. A collector that dies part-way still leaves
    # a non-empty file, and without this the contract sees a thin but error-free result and
    # calls it a broken selector -- so heal gets sent after a scraper that works.
    echo "$rc" > "$part.rc"
    [ -s "$part" ] || echo "  no output for $cid (exit $rc)" >> "$OUT/run.log"
  ) &
  running=$(( running + 1 ))
  if [ "$running" -ge "$CONCURRENCY" ]; then
    if wait -n 2>/dev/null; then
      running=$(( running - 1 ))
    else
      # bash before 4.3 has no `wait -n` at all (macOS ships 3.2), and on a shell that does
      # have it a reaped job that exited non-zero lands here too. Either way the fallback is
      # to drain every job, so the counter has to be reset rather than decremented by one.
      wait
      running=0
    fi
  fi
done < "$LIST"
wait

PARTS=()
for part in "$OUT"/part-"$STAMP"-*.json; do
  [ -s "$part" ] && PARTS+=("$part")
done

if [ "${#PARTS[@]}" -eq 0 ]; then
  echo "no collector produced any output" >&2
  exit 1
fi

python3 scripts/merge_parts.py "$COMBINED" "${PARTS[@]}"
python3 scripts/validate.py "$COMBINED" results/validate "$EXPECTED"
