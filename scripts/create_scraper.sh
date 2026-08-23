#!/usr/bin/env bash
# Build the Zed releases scraper via Bright Data Scraper Studio AI.
# Logs the full envelope to results/create_scraper/.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
OUT=results/create_scraper
mkdir -p "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
URL="https://zed.dev/releases"
DESC="Extract every release listed on the page. For each release return: version (e.g. 0.219.3), channel (stable or preview), release_date as ISO 8601, release_url (permalink to that release), and changelog_items as an array of the individual bullet-point strings under that release."
echo "[$STAMP] create url=$URL" | tee -a "$OUT/run.log"
./node_modules/.bin/bdata scraper create "$URL" "$DESC" \
  --name "zed-releases-scraper" --json --pretty \
  -o "$OUT/create-$STAMP.json" 2>&1 | tee -a "$OUT/run.log"
echo "[$(date -u +%Y%m%dT%H%M%SZ)] create exit=$? out=$OUT/create-$STAMP.json" | tee -a "$OUT/run.log"
