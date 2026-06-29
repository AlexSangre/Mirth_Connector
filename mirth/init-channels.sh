#!/bin/sh
# Imports and deploys all channels via Mirth REST API.
# Uses PUT /api/channels/{id} to push the full channel XML.
# Safe to re-run: PUT upserts by channel ID.

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
# 1b. Wait until extensions are installed in the DB (not just files on disk)
#     /api/extensions returns non-empty only after Derby has activated them.
# ---------------------------------------------------------------------------
echo "[init] Waiting for extensions to activate..."
until {
  size=$($CURL -o /dev/null -w "%{size_download}" "$MIRTH_URL/extensions")
  echo "[init] Extensions response size: $size bytes"
  [ "$size" -gt 50 ]
}; do
  echo "[init] Extensions not active yet, retrying in 10s..."
  sleep 10
done
echo "[init] Extensions activated."

# ---------------------------------------------------------------------------
# 2. Import each channel via PUT with retry (server may still be initialising)
# ---------------------------------------------------------------------------
find "$CHANNELS_DIR" -name "*.xml" | sort | while read -r xml; do
  name=$(basename "$xml")
  channel_id=$(grep -o '<id>[^<]*</id>' "$xml" | head -1 | sed 's/<[^>]*>//g')
  echo "[init] Importing: $name (id=$channel_id)"

  # Strip XML declaration and comment block — Mirth REST API chokes on them
  sed '/^<?xml/d; /^<!--/,/^-->/d' "$xml" > /tmp/channel-clean.xml

  imported=0
  for attempt in 1 2 3 4 5; do
    code=$($CURL -o /tmp/mirth-resp.txt -w "%{http_code}" \
      -X PUT "$MIRTH_URL/channels/$channel_id?override=true" \
      -H "Content-Type: application/xml" \
      --data-binary "@/tmp/channel-clean.xml")
    body=$(cat /tmp/mirth-resp.txt)
    if [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "204" ]; then
      echo "[init] Import OK ($code): $name"
      imported=1
      break
    elif [ "$code" = "503" ]; then
      echo "[init] Server not ready (attempt $attempt/5), retrying in 10s..."
      sleep 10
    else
      echo "[init] Import FAIL ($code): $name"
      echo "[init] Response: $body"
      break
    fi
  done
  if [ "$imported" = "0" ]; then
    echo "[init] Import FAILED after retries: $name"
  fi
done

# ---------------------------------------------------------------------------
# 3. Deploy each channel by ID
# ---------------------------------------------------------------------------
find "$CHANNELS_DIR" -name "*.xml" | sort | while read -r xml; do
  name=$(basename "$xml")
  channel_id=$(grep -o '<id>[^<]*</id>' "$xml" | head -1 | sed 's/<[^>]*>//g')
  echo "[init] Deploying: $name"

  code=$($CURL -o /tmp/mirth-deploy.txt -w "%{http_code}" \
    -X POST "$MIRTH_URL/channels/$channel_id/_deploy")

  body=$(cat /tmp/mirth-deploy.txt)
  if [ "$code" = "200" ] || [ "$code" = "204" ]; then
    echo "[init] Deploy OK ($code): $name"
  else
    echo "[init] Deploy FAIL ($code): $name"
    echo "[init] Response: $body"
  fi
done

echo "[init] Done."
