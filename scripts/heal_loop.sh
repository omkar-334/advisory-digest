#!/usr/bin/env bash
# Run the fleet, and repair it in place if the output contract breaks.
#
# The heal prompt is never hand-written: it is scripts/validate.py's own diagnosis of
# what broke. That is what makes this loop unattended rather than a staged demo.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

COLLECTOR="${COLLECTOR_ID:-c_mt5sgta91r4gozaifs}"
INPUT_FILE="${INPUT_FILE:-scripts/firms.txt}"
MAX_ATTEMPTS="${MAX_HEAL_ATTEMPTS:-2}"
OUT=results/heal_loop
mkdir -p "$OUT" results/run_scraper results/validate
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$OUT/heal-$STAMP.log"

log() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

run_once() {
  local raw="results/run_scraper/run-$STAMP-$1.json"
  ./node_modules/.bin/bdata scraper run "$COLLECTOR" \
    --input-file "$INPUT_FILE" --timeout 1800 --json --pretty -o "$raw" >>"$LOG" 2>&1
  if [ ! -s "$raw" ]; then
    log "run produced no output (see $LOG)"
    return 1
  fi
  python3 scripts/validate.py "$raw" results/validate
}

log "collector=$COLLECTOR input=$INPUT_FILE max_attempts=$MAX_ATTEMPTS"

DIAGNOSIS=$(run_once initial 2>>"$LOG")
RC=$?
if [ "$RC" -eq 0 ]; then
  log "contract satisfied on the first run; nothing to heal"
  exit 0
fi
if [ "$RC" -ne 2 ]; then
  log "hard failure (rc=$RC); not something heal can repair"
  exit 1
fi

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  log "attempt $attempt/$MAX_ATTEMPTS - contract violated, healing in place"
  log "heal prompt: $DIAGNOSIS"

  ./node_modules/.bin/bdata scraper heal "$COLLECTOR" "$DIAGNOSIS" \
    --auto-approve --auto-save --timeout 900 \
    --json --pretty -o "$OUT/heal-$STAMP-attempt$attempt.json" >>"$LOG" 2>&1
  HEAL_RC=$?
  log "heal exit=$HEAL_RC"
  [ "$HEAL_RC" -ne 0 ] && { log "heal call failed; aborting"; exit 1; }

  NEXT=$(run_once "attempt$attempt" 2>>"$LOG")
  RC=$?

  python3 - "$STAMP" "$DIAGNOSIS" "$COLLECTOR" "$RC" <<'PY'
import json, sys, pathlib
stamp, diagnosis, collector, rc = sys.argv[1:5]
pathlib.Path("results/heal_loop").mkdir(parents=True, exist_ok=True)
pathlib.Path("results/heal_loop/last-event.json").write_text(json.dumps({
    "stamp": stamp,
    "diagnosis": diagnosis,
    "collector": collector,
    "resolved": rc == "0",
}, indent=1))
PY

  if [ "$RC" -eq 0 ]; then
    log "HEALED after $attempt attempt(s). Collector ID unchanged, nothing downstream touched."
    exit 0
  fi
  log "still violating after heal: $NEXT"
  DIAGNOSIS="$NEXT"
  attempt=$(( attempt + 1 ))
done

log "exhausted $MAX_ATTEMPTS heal attempts; escalating"
exit 2
