#!/usr/bin/env bash
# Run every collector in the fleet and validate the combined result against the contract.
#
# Scraper Studio generates extraction code against a specific site, so one collector does
# not cover unrelated layouts. The fleet is one collector per newsroom; what is shared is
# the contract (scripts/validate.py) and the repair loop.
#
# Exit 0 = healthy, 2 = contract violated (heal-worthy), 1 = hard failure.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

OUT=results/run_fleet
mkdir -p "$OUT" results/validate
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COMBINED="$OUT/fleet-$STAMP.json"
EXPECTED="$OUT/expected-$STAMP.txt"
: > "$EXPECTED"

# Portable across bash 3.2 (macOS default), which has no mapfile.
python3 -c "
import json
for c in json.load(open('scripts/collectors.json'))['collectors']:
    if c.get('collector_id'):
        print(c['collector_id'], c['url'])
" > "$OUT/fleet-$STAMP.list"

if [ ! -s "$OUT/fleet-$STAMP.list" ]; then
  echo "no collectors with an id in scripts/collectors.json" >&2
  exit 1
fi

# Run collectors concurrently. Running a collector does not consume an AI-Flow generation
# slot, so this is not bound by the 3-job cap that applies to `scraper create` and `heal`.
# Sequential runs of a 13-collector fleet took roughly 40 minutes, which is too slow for CI.
CONCURRENCY="${FLEET_CONCURRENCY:-4}"
running=0
while read -r cid url; do
  [ -z "$cid" ] && continue
  echo "$url" >> "$EXPECTED"
  part="$OUT/part-$STAMP-$cid.json"
  echo "[$STAMP] $cid -> $url" | tee -a "$OUT/run.log"
  (
    ./node_modules/.bin/bdata scraper run "$cid" "$url" \
      --timeout 900 --json --pretty -o "$part" >>"$OUT/run.log" 2>&1
    [ -s "$part" ] || echo "  no output for $cid" >> "$OUT/run.log"
  ) &
  running=$(( running + 1 ))
  if [ "$running" -ge "$CONCURRENCY" ]; then wait -n 2>/dev/null || wait; running=$(( running - 1 )); fi
done < "$OUT/fleet-$STAMP.list"
wait

PARTS=()
for part in "$OUT"/part-"$STAMP"-*.json; do
  [ -s "$part" ] && PARTS+=("$part")
done

# Merge every collector's envelopes into one payload so the contract sees the whole fleet.
python3 - "$COMBINED" "${PARTS[@]}" <<'PY'
import json, sys
out, merged = sys.argv[1], []
for path in sys.argv[2:]:
    try:
        data = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        continue
    merged.extend(data if isinstance(data, list) else [data])
json.dump(merged, open(out, "w"), ensure_ascii=False, indent=1)
print(f"merged {len(merged)} envelopes from {len(sys.argv) - 2} collector(s)")
PY

python3 scripts/validate.py "$COMBINED" results/validate "$EXPECTED"
