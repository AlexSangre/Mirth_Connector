#!/bin/sh
# Mirth Connect full diagnostic + import test
# Run from Mirth_Connector directory:
#   sh mirth/diagnose.sh

BASE="https://localhost:8443/api"
AUTH="admin:admin"
HDR="X-Requested-With:OpenAPI"
CURL="curl -sk -u $AUTH -H $HDR"
CHANNEL_XML="mirth/channels/healthcare/VitalsMonitorToHL7.xml"
TEST_ID="test0001-0000-0000-0000-000000000001"
REAL_ID="d1e2f3a4-b5c6-7890-defa-112233445566"

sep() { echo; echo "=== $1 ==="; }

sep "MIRTH VERSION"
$CURL "$BASE/server/version"

sep "EXTENSIONS LOADED"
$CURL "$BASE/extensions" | grep -o '"name":"[^"]*"' | sort || \
$CURL "$BASE/extensions" | grep -o '<name>[^<]*</name>' | sort

sep "CHANNELS IN DB"
$CURL "$BASE/channels" | grep -E "<name>|<transportName>|<description>"

sep "CLI CHECK"
docker exec mirth-connect find /opt/connect -name "*.sh" -o -name "*.jar" 2>/dev/null | grep -iE "cli|command" | head -10

sep "TEST: DELETE EXISTING TEST CHANNEL"
$CURL -X DELETE "$BASE/channels/$TEST_ID"

sep "TEST: POST MINIMAL FILE READER CHANNEL"
$CURL -X POST "$BASE/channels" \
  -H "Content-Type: application/xml" \
  -d '<channel version="4.4.1">
  <id>test0001-0000-0000-0000-000000000001</id>
  <name>TestMinimal</name>
  <enabled>true</enabled>
  <sourceConnector version="4.4.1">
    <metaDataId>0</metaDataId>
    <name>sourceConnector</name>
    <properties class="com.mirth.connect.connectors.file.FileReceiverProperties" version="4.4.1">
      <scheme>FILE</scheme>
      <host>/tmp</host>
      <fileFilter>*.json</fileFilter>
      <afterProcessingAction>NONE</afterProcessingAction>
      <binary>false</binary>
      <charsetEncoding>UTF-8</charsetEncoding>
    </properties>
    <transformer version="4.4.1"><elements/></transformer>
    <filter version="4.4.1"><elements/></filter>
    <transportName>File Reader</transportName>
    <mode>SOURCE</mode>
    <enabled>true</enabled>
    <waitForPrevious>true</waitForPrevious>
  </sourceConnector>
  <destinationConnectors/>
  <preprocessingScript>return message;</preprocessingScript>
  <postprocessingScript>return;</postprocessingScript>
  <deployScript>return;</deployScript>
  <undeployScript>return;</undeployScript>
  <properties class="com.mirth.connect.donkey.model.channel.ChannelProperties" version="4.4.1">
    <clearGlobalChannelMap>true</clearGlobalChannelMap>
    <messageStorageMode>DEVELOPMENT</messageStorageMode>
    <initialState>STARTED</initialState>
    <resourceIds class="linked-hash-map">
      <entry><string>Default Resource</string><string>[Default Resource]</string></entry>
    </resourceIds>
  </properties>
</channel>'

sep "TEST: GET MINIMAL CHANNEL (should show transportName + scheme)"
$CURL "$BASE/channels/$TEST_ID" | grep -E "<transportName>|<scheme>|<description>|<host>"

sep "TEST: PUT REAL CHANNEL WITH override=true (stripped XML)"
sed '/^<?xml/d; /^<!--/,/^-->/d' "$CHANNEL_XML" > /tmp/channel-clean.xml
$CURL -X PUT "$BASE/channels/$REAL_ID?override=true" \
  -H "Content-Type: application/xml" \
  --data-binary @/tmp/channel-clean.xml

sep "GET REAL CHANNEL AFTER PUT"
$CURL "$BASE/channels/$REAL_ID" | grep -E "<transportName>|<scheme>|<description>|<host>"

sep "MIRTH SERVER LOG TAIL"
docker exec mirth-connect find /opt/connect -name "*.log" 2>/dev/null | head -5
docker logs mirth-connect 2>&1 | tail -20

echo
echo "=== DONE ==="
