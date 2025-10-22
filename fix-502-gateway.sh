#!/bin/bash
echo "=========================================="
echo "🔧 Fixing 502 Bad Gateway Issue"
echo "=========================================="
echo ""

echo "Step 1: Restart ChatStack web container"
echo "-----------------------------------"
docker restart chatstack-web-1
echo "✅ Web container restarted"
sleep 5
echo ""

echo "Step 2: Check if web container is healthy"
echo "-----------------------------------"
if docker ps | grep -q chatstack-web-1; then
    echo "✅ Web container is running"
    docker logs chatstack-web-1 --tail=10
else
    echo "❌ Web container is NOT running!"
    echo "Trying to start it..."
    docker start chatstack-web-1
fi
echo ""

echo "Step 3: Test Flask app directly"
echo "-----------------------------------"
echo "Testing: http://localhost:5000"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000 2>&1)
if [ "$RESPONSE" = "200" ] || [ "$RESPONSE" = "404" ] || [ "$RESPONSE" = "405" ]; then
    echo "✅ Flask app is responding (HTTP $RESPONSE)"
else
    echo "❌ Flask app not responding (HTTP $RESPONSE)"
fi
echo ""

echo "Step 4: Check Nginx configuration"
echo "-----------------------------------"
NGINX_CONFIG="/etc/nginx/sites-enabled/voice.theinsurancedoctors.com"
if grep -q "proxy_pass.*5000" "$NGINX_CONFIG"; then
    echo "✅ Nginx proxy_pass configured for port 5000"
    grep "proxy_pass" "$NGINX_CONFIG"
else
    echo "⚠️  Nginx proxy_pass might not be configured correctly"
    grep "proxy_pass" "$NGINX_CONFIG" || echo "No proxy_pass found!"
fi
echo ""

echo "Step 5: Test the exact Twilio webhook endpoint"
echo "-----------------------------------"
curl -s -X POST http://localhost:5000/phone/incoming-realtime \
  -d "From=+19495565377&To=+19497071290&CallSid=TEST" 2>&1 | head -15
echo ""

echo "Step 6: Reload Nginx"
echo "-----------------------------------"
sudo nginx -t && sudo systemctl reload nginx
echo "✅ Nginx reloaded"
echo ""

echo "=========================================="
echo "✅ FIX COMPLETE - TEST A CALL NOW"
echo "=========================================="
echo ""
echo "If the call still hangs up:"
echo "1. Check nginx error log: tail -f /var/log/nginx/error.log"
echo "2. Check Flask logs: docker logs -f chatstack-web-1"
echo "3. Make sure the route exists: docker exec chatstack-web-1 grep -r 'incoming-realtime' /app"
echo ""
