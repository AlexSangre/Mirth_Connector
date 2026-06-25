#!/bin/sh
# Waits for Mirth Connect to be ready, then imports and deploys all channels
# via the REST API. Safe to re-run: Mirth upserts channels by XML channel ID.

set -e

MIRTH_URL="https://mirth-connect:8443/api"
MIRTH_USER="${MIRTH_USER:-admin}"
MIRTH_PASS="${MIRTH_PASS:-admin}"
CHANNELS_DIR="/channels"
COOKIES="/tmp/mirth-cookies.txt"

# ---------------------------------------------------------------------------
# 1. Wait until Mirth is accepting logins
# ---------------------------------------------------------------------------
echo "[init] Waiting for Mirth Connect..."
until {
  code=$(curl -sk --max-time 5 \
    -c "$COOKIES" \
    -o /dev/null -w "%{http_code}" \
    -X POST "$MIRTH_URL/users/_login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${MIRTH_USER}&password=${MIRTH_PASS}")
  echo "[init] Login response: $code"
  case "$code" in 2*) true ;; *) false ;; esac
}; do
  echo "[init] Not ready yet, retrying in 5s..."
  sleep 5
done
echo "[init] Mirth Connect is ready."

# ---------------------------------------------------------------------------
# 2. Import every XML file (root + healthcare/ sub-folder)
# ---------------------------------------------------------------------------
find "$CHANNELS_DIR" -name "*.xml" | sort | while read -r xml; do
  name=$(basename "$xml")
  echo "[init] Importing channel: $name"
  http_code=$(curl -sk --max-time 10 \
    -b "$COOKIES" -c "$COOKIES" \
    -o /tmp/mirth-resp.txt -w "%{http_code}" \
    -X POST "$MIRTH_URL/channels" \
    -H "Content-Type: application/xml" \
    -H "Accept: application/xml" \
    --data-binary "@$xml")

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    echo "[init] OK ($http_code): $name"
  else
    echo "[init] WARN ($http_code): $name — $(cat /tmp/mirth-resp.txt)"
  fi
done

# ---------------------------------------------------------------------------
# 3. Deploy all channels
# ---------------------------------------------------------------------------
echo "[init] Deploying all channels..."
http_code=$(curl -sk --max-time 15 \
  -b "$COOKIES" -c "$COOKIES" \
  -o /tmp/mirth-deploy.txt -w "%{http_code}" \
  -X POST "$MIRTH_URL/channels/deploy" \
  -H "Content-Type: application/xml" \
  -H "Accept: application/xml" \
  -d "<set/>")

if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
  echo "[init] All channels deployed successfully."
else
  echo "[init] Deploy returned HTTP $http_code: $(cat /tmp/mirth-deploy.txt)"
  exit 1
fi
