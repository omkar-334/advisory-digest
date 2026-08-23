#!/usr/bin/env bash
# Build a Scraper Studio collector from a natural-language description.
# Usage: create_collector.sh <name> <url> <description>
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
NAME="$1"; URL="$2"; DESC="$3"
OUT="results/create_collector"
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
echo "[$STAMP] create name=$NAME url=$URL" | tee -a "$OUT/run.log"
./node_modules/.bin/bdata scraper create "$URL" "$DESC" \
  --name "$NAME" --json --pretty -o "$OUT/$NAME-$STAMP.json" 2>&1 | tee -a "$OUT/run.log"
echo "[$(date -u +%Y%m%dT%H%M%SZ)] done name=$NAME file=$OUT/$NAME-$STAMP.json" | tee -a "$OUT/run.log"
