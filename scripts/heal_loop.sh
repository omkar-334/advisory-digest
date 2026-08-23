#!/usr/bin/env bash
# Run the fleet, and repair in place any collector whose contract broke.
#
# One collector per newsroom, so repair is per collector: heal fixes a scraper against its
# own target. The heal prompt is never hand-written -- it is scripts/validate.py's own
# diagnosis of what broke, which is what makes this loop unattended.
#
# A failed RUN is never healed. Rate limits and navigation timeouts produce empty output
# that looks exactly like a broken selector, and healing a working scraper spends credits
# and can leave it worse. validate.py exits 1 for that case and 2 only for a real break.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

MAX_ATTEMPTS="${MAX_HEAL_ATTEMPTS:-2}"
# Unattended by default. Set REVIEW=1 to stop at Bright Data's approval gate instead, so a
# proposed fix can be inspected and then accepted with `bdata scraper approve <id>` or
# discarded with `--reject`. CI runs unattended; a human debugging a stubborn source does not.
REVIEW="${REVIEW:-0}"
if [ "$REVIEW" = "1" ]; then APPROVAL=(); else APPROVAL=(--auto-approve --auto-save); fi
OUT=results/heal_loop
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$OUT/heal-$STAMP.log"
log(){ echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

log "running fleet"
./scripts/run_fleet.sh >>"$LOG" 2>&1
RC=$?

case "$RC" in
  0) log "contract satisfied across the fleet; nothing to heal"; exit 0 ;;
  1) log "one or more runs failed. Not heal-worthy: re-run instead."; exit 1 ;;
  2) : ;;
  *) log "unexpected exit $RC"; exit 1 ;;
esac

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  # Only firms the contract named are repaired, each through its own collector.
  # A firm whose run failed never appears in this list.
  # A crash here writes an empty file, which is indistinguishable from "nothing to heal"
  # unless the exit status is checked. Reporting success while the fleet is still broken
  # is the one thing this loop must never do.
  if ! python3 scripts/broken_sources.py > "$OUT/broken-$STAMP.tsv" 2>>"$LOG"; then
    log "broken_sources.py failed; cannot tell what is heal-worthy"; exit 2
  fi
  if [ ! -s "$OUT/broken-$STAMP.tsv" ]; then
    log "nothing heal-worthy remains"; exit 0
  fi

  log "attempt $attempt/$MAX_ATTEMPTS on $(wc -l < "$OUT/broken-$STAMP.tsv" | tr -d ' ') source(s)"
  while IFS=$'\t' read -r cid url firm problems; do
    [ -z "$cid" ] && continue
    log "healing $firm ($cid)"
    log "  prompt: $problems"
    # ${APPROVAL[@]+...} because REVIEW=1 leaves the array empty, and expanding an empty
    # array under `set -u` is an error on bash before 4.4 (macOS ships 3.2).
    # </dev/null so the CLI cannot swallow the TSV this loop is reading from stdin.
    ./node_modules/.bin/bdata scraper heal "$cid" "$problems" \
      --url "$url" ${APPROVAL[@]+"${APPROVAL[@]}"} --timeout 900 \
      --json --pretty -o "$OUT/heal-$STAMP-$firm.json" </dev/null >>"$LOG" 2>&1
    log "  heal exit=$?. A 'done' status is not proof of repair; the re-run below decides."
    if [ "$REVIEW" = "1" ]; then
      log "  awaiting review: bdata scraper approve $cid   (or --reject)"
    fi
  done < "$OUT/broken-$STAMP.tsv"

  if [ "$REVIEW" = "1" ]; then
    log "stopping at the approval gate. Approve or reject, then re-run this script."
    exit 3
  fi

  log "re-running fleet to verify"
  ./scripts/run_fleet.sh >>"$LOG" 2>&1
  RC=$?
  python3 scripts/record_heal.py "$STAMP" "$RC" >>"$LOG" 2>&1

  if [ "$RC" -eq 0 ]; then
    log "HEALED after $attempt attempt(s). Collector IDs unchanged, nothing downstream touched."
    exit 0
  fi
  if [ "$RC" -eq 1 ]; then
    log "runs failing; stopping rather than healing blind"; exit 1
  fi
  if [ "$RC" -ne 2 ]; then
    # Same rule as the first run: only a 2 means "a real break", so any other code must not
    # send us round the loop to heal again off a summary that may be stale.
    log "unexpected exit $RC"; exit 1
  fi
  attempt=$(( attempt + 1 ))
done

log "exhausted $MAX_ATTEMPTS attempts; escalating"
exit 2
