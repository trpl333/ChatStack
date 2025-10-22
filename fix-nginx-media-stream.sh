#!/bin/bash
echo "=========================================="
echo "🔧 Fixing nginx media-stream routing"
echo "=========================================="
echo ""

NGINX_CONFIG="/etc/nginx/sites-enabled/voice.theinsurancedoctors.com"

echo "Step 1: Backup nginx config"
sudo cp "$NGINX_CONFIG" "${NGINX_CONFIG}.backup-$(date +%s)"
echo "✅ Backup created"
echo ""

echo "Step 2: Update media-stream proxy target"
echo "Changing: port 8001 → port 9100"
echo ""

# Replace the media-stream location block
sudo sed -i '/location \/phone\/media-stream {/,/}/c\
    location /phone/media-stream {\
        proxy_pass http://127.0.0.1:9100;\
        proxy_http_version 1.1;\
        proxy_set_header Upgrade $http_upgrade;\
        proxy_set_header Connection "Upgrade";\
        proxy_set_header Host $host;\
        proxy_read_timeout 3600;\
        proxy_send_timeout 3600;\
    }' "$NGINX_CONFIG"

echo "✅ Updated nginx config"
echo ""

echo "Step 3: Verify new configuration"
grep -A 8 "location /phone/media-stream" "$NGINX_CONFIG"
echo ""

echo "Step 4: Test nginx syntax"
sudo nginx -t
echo ""

echo "Step 5: Reload nginx"
sudo systemctl reload nginx
echo "✅ Nginx reloaded"
echo ""

echo "Step 6: Test VoiceBridge endpoint"
curl -s http://127.0.0.1:9100/health 2>&1 || echo "VoiceBridge not responding on 9100"
echo ""

echo "=========================================="
echo "✅ FIX COMPLETE"
echo "=========================================="
echo ""
echo "📞 NOW TEST A CALL - IT SHOULD WORK!"
echo ""
echo "To monitor in real-time:"
echo "  sudo journalctl -u voice-bridge -f"
echo ""
