#!/bin/sh
# Waits for Mirth Connect to be ready, then imports and deploys all channels
# via the REST API using HTTP Basic Auth + per-channel deploy.
# Safe to re-run: Mirth upserts channels by XML channel ID.

set -e

MIRTH_URL="https://mirth-connect:8443/api"
MIRTH_USER="${MIRTH_USER:-admin}"
MIRTH_PASS="${MIRTH_PASS:-admin}"
CHANNELS_DIR="/channels"

CURL="curl -sk --max-time 10 -u ${MIRTH_USER}:${MIRTH_PASS} -H X-Requested-With:OpenAPI"

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
# 2. Import + deploy each channel
# ---------------------------------------------------------------------------
find "$CHANNELS_DIR" -name "*.xml" | sort | while read -r xml; do
  name=$(basename "$xml")

  # Extract channel ID from the XML file itself
  channel_id=$(grep -o '<id>[^<]*</id>' "$xml" | head -1 | sed 's/<[^>]*>//g')
  echo "[init] Importing: $name (id=$channel_id)"

  code=$($CURL -o /tmp/mirth-resp.txt -w "%{http_code}" \
    -X POST "$MIRTH_URL/channels" \
    -H "Content-Type: application/xml" \
    --data-binary "@$xml")

  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    echo "[init] Imported OK ($code): $name"
  else
    echo "[init] Import WARN ($code): $name — $(cat /tmp/mirth-resp.txt)"
  fi

  # Deploy this channel individually
  echo "[init] Deploying: $name"
  code=$($CURL -o /tmp/mirth-deploy.txt -w "%{http_code}" \
    -X POST "$MIRTH_URL/channels/$channel_id/_deploy")

  if [ "$code" = "200" ] || [ "$code" = "204" ]; then
    echo "[init] Deployed OK ($code): $name"
  else
    echo "[init] Deploy WARN ($code): $name — $(cat /tmp/mirth-deploy.txt)"
  fi
done

echo "[init] Done."
