#!/bin/bash

echo "🔧 Fixing nginx configuration conflicts..."

# 1. Deploy fixed neurosphere-llms config (no voice.theinsurancedoctors.com conflict)
echo "📝 Deploying fixed neurosphere-llms config (keeps a100/a40, removes voice conflict)..."
sudo cp /opt/ChatStack/deploy/nginx/neurosphere-llms-fixed.conf /etc/nginx/sites-enabled/neurosphere-llms.conf

# 2. Deploy canonical voice config (complete with /phone/ and /static/ proxies)
echo "📝 Deploying canonical voice-theinsurancedoctors-com config..."
sudo cp /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf /etc/nginx/sites-enabled/

# 3. Remove any default configs that might interfere
if [ -f /etc/nginx/sites-enabled/default ]; then
    echo "🗑️ Removing default nginx config..."
    sudo rm /etc/nginx/sites-enabled/default
fi

# 4. Test nginx configuration
echo "🔍 Testing nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    # 5. Reload nginx if test passes
    echo "✅ Configuration valid, reloading nginx..."
    sudo systemctl reload nginx
    
    echo "🎯 nginx conflict resolution complete!"
    echo ""
    echo "📋 Active configurations:"
    ls -la /etc/nginx/sites-enabled/
    echo ""
    echo "🧪 Testing static file access..."
    curl -I https://voice.theinsurancedoctors.com/static/audio/
    echo ""
    echo "🧪 Testing phone endpoint..."
    curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "From=+test&To=+19497071290" | grep -o 'https://[^<]*'
    echo ""
    echo "🎵 If static files return 200 OK and phone endpoint shows HTTPS URLs, call +19497071290 to test!"
    
else
    echo "❌ nginx configuration test failed. Please check the errors above."
    exit 1
fi