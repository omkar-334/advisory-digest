#!/usr/bin/env bash
# The hero loop: run -> validate -> heal -> approve -> re-run -> re-validate.
#
# The heal prompt is not hand-written. It is the contract validator's own
# diagnosis of what broke, so the loop needs no human in it.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

COLLECTOR="${COLLECTOR_ID:?COLLECTOR_ID not set}"
TARGET_URL="${TARGET_URL:-https://zed.dev/releases}"
MAX_ATTEMPTS="${MAX_HEAL_ATTEMPTS:-2}"
OUT=results/heal_loop
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$OUT/heal-$STAMP.log"

log() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

log "collector=$COLLECTOR url=$TARGET_URL max_attempts=$MAX_ATTEMPTS"

DIAGNOSIS=$(./scripts/run_scraper.sh 2>>"$LOG")
RC=$?
if [ "$RC" -eq 0 ]; then
  log "healthy on first run, nothing to heal"
  exit 0
fi
if [ "$RC" -ne 2 ]; then
  log "hard failure (rc=$RC) - not heal-worthy, escalating"
  exit 1
fi

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  log "attempt $attempt/$MAX_ATTEMPTS - contract violated, healing"
  log "heal prompt: $DIAGNOSIS"

  ./node_modules/.bin/bdata scraper heal "$COLLECTOR" "$DIAGNOSIS" \
    --url "$TARGET_URL" --auto-approve --auto-save \
    --json --pretty -o "$OUT/heal-$STAMP-attempt$attempt.json" >>"$LOG" 2>&1
  HEAL_RC=$?
  log "heal exit=$HEAL_RC"

  if [ "$HEAL_RC" -ne 0 ]; then
    log "heal call failed, aborting"
    exit 1
  fi

  DIAGNOSIS=$(./scripts/run_scraper.sh 2>>"$LOG")
  RC=$?
  if [ "$RC" -eq 0 ]; then
    log "HEALED after $attempt attempt(s) - same collector id, no downstream change"
    exit 0
  fi
  log "still violating after heal: $DIAGNOSIS"
  attempt=$(( attempt + 1 ))
done

log "exhausted $MAX_ATTEMPTS heal attempts, escalating to a human"
exit 2
