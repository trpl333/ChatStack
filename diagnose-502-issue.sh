#!/bin/bash
echo "=========================================="
echo "🔍 Diagnosing 502 Bad Gateway Issue"
echo "=========================================="
echo ""

echo "1️⃣  CHECKING WEB CONTAINER STATUS"
echo "-----------------------------------"
docker ps | grep chatstack-web
echo ""

echo "2️⃣  RECENT WEB CONTAINER LOGS"
echo "-----------------------------------"
docker logs chatstack-web-1 --tail=30
echo ""

echo "3️⃣  NGINX PROXY CONFIGURATION"
echo "-----------------------------------"
grep -R "proxy_pass" /etc/nginx/sites-enabled/voice.theinsurancedoctors.com
echo ""

echo "4️⃣  TESTING FLASK APP DIRECTLY (bypassing nginx)"
echo "-----------------------------------"
echo "Testing: curl http://localhost:5000/phone/incoming-realtime"
curl -s -X POST http://localhost:5000/phone/incoming-realtime \
  -d "From=+19495565377&To=+19497071290&CallSid=TEST123" \
  -w "\nHTTP Status: %{http_code}\n" 2>&1 | head -20
echo ""

echo "5️⃣  CHECKING IF ROUTE EXISTS IN CODE"
echo "-----------------------------------"
docker exec chatstack-web-1 grep -r "incoming-realtime" /app 2>&1 | head -10
echo ""

echo "6️⃣  CHECKING NGINX ERROR LOGS"
echo "-----------------------------------"
tail -20 /var/log/nginx/error.log
echo ""

echo "7️⃣  TESTING ORCHESTRATOR (8001)"
echo "-----------------------------------"
curl -s http://localhost:8001/health 2>&1
echo ""
echo ""

echo "=========================================="
echo "✅ DIAGNOSTIC COMPLETE"
echo "=========================================="
echo ""
echo "📋 WHAT TO LOOK FOR:"
echo "  ✅ Web container should be 'Up' and listening on port 5000"
echo "  ✅ Nginx proxy_pass should point to http://127.0.0.1:5000"
echo "  ✅ Direct curl to localhost:5000 should return TwiML XML"
echo "  ✅ Route 'incoming-realtime' should exist in Flask code"
echo ""
