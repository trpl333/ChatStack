#!/bin/bash
# Debug transcript file location issue

echo "=================================================="
echo "🔍 Transcript File Location Diagnostic"
echo "=================================================="
echo ""

CALL_SID="CAe7c160e22400def1b29117b222064851"

echo "1️⃣ Checking file INSIDE Docker container:"
echo "-----------------------------------"
docker exec chatstack-orchestrator-worker-1 ls -lh /app/static/calls/${CALL_SID}.txt 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ File exists inside container"
    echo ""
    echo "First 500 chars of file:"
    docker exec chatstack-orchestrator-worker-1 head -c 500 /app/static/calls/${CALL_SID}.txt
    echo ""
    echo ""
    echo "File size:"
    docker exec chatstack-orchestrator-worker-1 wc -c /app/static/calls/${CALL_SID}.txt
else
    echo "❌ File NOT found inside container"
fi
echo ""

echo "2️⃣ Checking Docker volume mounts:"
echo "-----------------------------------"
docker inspect chatstack-orchestrator-worker-1 | grep -A 20 "Mounts"
echo ""

echo "3️⃣ Checking file on HOST filesystem:"
echo "-----------------------------------"
# Check common locations
locations=(
    "/opt/ChatStack/static/calls/${CALL_SID}.txt"
    "/opt/ChatStack/app/static/calls/${CALL_SID}.txt"
    "/var/www/calls/${CALL_SID}.txt"
    "/opt/ChatStack/calls/${CALL_SID}.txt"
)

for loc in "${locations[@]}"; do
    if [ -f "$loc" ]; then
        echo "✅ Found at: $loc"
        ls -lh "$loc"
    else
        echo "❌ Not found: $loc"
    fi
done
echo ""

echo "4️⃣ Checking Nginx configuration:"
echo "-----------------------------------"
echo "Looking for 'calls' location in nginx config:"
grep -r "location.*calls" /etc/nginx/sites-enabled/ 2>/dev/null || echo "No 'calls' location found in nginx"
echo ""

echo "5️⃣ Testing web access:"
echo "-----------------------------------"
curl -I https://voice.theinsurancedoctors.com/calls/${CALL_SID}.txt 2>/dev/null | head -5
echo ""

echo "=================================================="
echo "📋 RECOMMENDATIONS:"
echo "=================================================="
echo ""
echo "The file should be accessible at one of these locations:"
echo "  - Inside container: /app/static/calls/"
echo "  - On host (mounted): /opt/ChatStack/static/calls/"
echo "  - Nginx serving from: (check config above)"
echo ""
echo "If file is only in container, you need to add a volume mount!"
echo ""
