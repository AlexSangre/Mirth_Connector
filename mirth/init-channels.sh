#!/bin/sh
# Waits for Mirth Connect to be ready, then imports and deploys all channels
# via the REST API using HTTP Basic Auth.
# Safe to re-run: Mirth upserts channels by XML channel ID.

set -e

MIRTH_URL="https://mirth-connect:8443/api"
MIRTH_USER="${MIRTH_USER:-admin}"
MIRTH_PASS="${MIRTH_PASS:-admin}"
CHANNELS_DIR="/channels"
AUTH="${MIRTH_USER}:${MIRTH_PASS}"

CURL="curl -sk --max-time 10 -u $AUTH -H X-Requested-With:OpenAPI"

# ---------------------------------------------------------------------------
# 1. Wait until Mirth is accepting requests
# ---------------------------------------------------------------------------
echo "[init] Waiting for Mirth Connect..."
until {
  code=$($CURL -o /dev/null -w "%{http_code}" "$MIRTH_URL/server/version")
  echo "[init] Health check: $code"
  case "$code" in 2*) true ;; *) false ;; esac
}; do
  echo "[init] Not ready yet, retrying in 5s..."
  sleep 5
done
echo "[init] Mirth Connect is ready."

# ---------------------------------------------------------------------------
# 2. Import every XML file
# ---------------------------------------------------------------------------
find "$CHANNELS_DIR" -name "*.xml" | sort | while read -r xml; do
  name=$(basename "$xml")
  echo "[init] Importing: $name"
  code=$($CURL -o /tmp/mirth-resp.txt -w "%{http_code}" \
    -X POST "$MIRTH_URL/channels" \
    -H "Content-Type: application/xml" \
    -H "Accept: application/xml" \
    --data-binary "@$xml")

  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    echo "[init] OK ($code): $name"
  else
    echo "[init] WARN ($code): $name — $(cat /tmp/mirth-resp.txt)"
  fi
done

# ---------------------------------------------------------------------------
# 3. Deploy all channels
# ---------------------------------------------------------------------------
echo "[init] Deploying all channels..."
code=$($CURL -o /tmp/mirth-deploy.txt -w "%{http_code}" \
  -X POST "$MIRTH_URL/channels/deploy" \
  -H "Content-Type: application/xml" \
  -H "Accept: application/xml" \
  -d "<set/>")

if [ "$code" = "200" ] || [ "$code" = "204" ]; then
  echo "[init] All channels deployed successfully."
else
  echo "[init] Deploy returned HTTP $code: $(cat /tmp/mirth-deploy.txt)"
  exit 1
fi
