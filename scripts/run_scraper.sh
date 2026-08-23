#!/usr/bin/env bash
# Run the collector once and validate its output against the contract.
# Exit 0 = healthy, 2 = contract violated (heal-worthy), 1 = hard failure.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

COLLECTOR="${COLLECTOR_ID:?COLLECTOR_ID not set (see .env or scraper.json)}"
TARGET_URL="${TARGET_URL:-https://zed.dev/releases}"
OUT=results/run_scraper
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RAW="$OUT/run-$STAMP.json"

echo "[$STAMP] run collector=$COLLECTOR url=$TARGET_URL" | tee -a "$OUT/run.log"
START=$(date +%s)
./node_modules/.bin/bdata scraper run "$COLLECTOR" "$TARGET_URL" \
  --json --pretty -o "$RAW" >>"$OUT/run.log" 2>&1
RUN_RC=$?
ELAPSED=$(( $(date +%s) - START ))
echo "[$STAMP] run exit=$RUN_RC elapsed=${ELAPSED}s raw=$RAW" | tee -a "$OUT/run.log"

if [ "$RUN_RC" -ne 0 ] || [ ! -s "$RAW" ]; then
  echo "run failed; see $OUT/run.log" >&2
  exit 1
fi

python3 scripts/validate.py "$RAW" results/validate
exit $?
