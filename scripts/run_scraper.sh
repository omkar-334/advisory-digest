#!/usr/bin/env bash
# Run the collector across every newsroom and validate the result against the contract.
# Exit 0 = healthy, 2 = contract violated (heal-worthy), 1 = hard failure.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

COLLECTOR="${COLLECTOR_ID:-c_mt5sgta91r4gozaifs}"
INPUT_FILE="${INPUT_FILE:-scripts/firms.txt}"
OUT=results/run_scraper
mkdir -p "$OUT" results/validate
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RAW="$OUT/run-$STAMP.json"

echo "[$STAMP] run collector=$COLLECTOR input=$INPUT_FILE" | tee -a "$OUT/run.log"
START=$(date +%s)
./node_modules/.bin/bdata scraper run "$COLLECTOR" \
  --input-file "$INPUT_FILE" --timeout 1800 --json --pretty -o "$RAW" >>"$OUT/run.log" 2>&1
RUN_RC=$?
echo "[$STAMP] run exit=$RUN_RC elapsed=$(( $(date +%s) - START ))s raw=$RAW" | tee -a "$OUT/run.log"

if [ "$RUN_RC" -ne 0 ] || [ ! -s "$RAW" ]; then
  echo "run failed; see $OUT/run.log" >&2
  exit 1
fi

# The expected-URL list is passed so that a site returning nothing at all is still judged,
# rather than vanishing from the report entirely.
python3 scripts/validate.py "$RAW" results/validate "$INPUT_FILE"
