#!/bin/bash
# Fix nginx to serve transcripts from the correct location

echo "🔧 Fixing nginx configuration for /calls/ path"
echo ""

# Check if nginx config exists
NGINX_SITE="/etc/nginx/sites-enabled/voice.theinsurancedoctors.com"

if [ ! -f "$NGINX_SITE" ]; then
    echo "❌ Nginx config not found at $NGINX_SITE"
    echo "Looking for nginx configs..."
    ls -la /etc/nginx/sites-enabled/
    exit 1
fi

echo "✅ Found nginx config: $NGINX_SITE"
echo ""

# Backup original
cp "$NGINX_SITE" "${NGINX_SITE}.backup.$(date +%Y%m%d_%H%M%S)"
echo "✅ Backup created"
echo ""

# Check if /calls/ location already exists
if grep -q "location /calls/" "$NGINX_SITE"; then
    echo "⚠️  /calls/ location already exists in config"
    echo "Current configuration:"
    grep -A 5 "location /calls/" "$NGINX_SITE"
    echo ""
    read -p "Replace it? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    # Remove old location block
    sed -i '/location \/calls\//,/}/d' "$NGINX_SITE"
fi

# Add or update the /calls/ location block (before the final closing brace)
# This assumes the server block ends with just a closing brace
sed -i '/^}$/i\
\    # Serve call transcripts and recordings\
\    location /calls/ {\
\        alias /opt/ChatStack/static/calls/;\
\        autoindex off;\
\        add_header Cache-Control "no-cache, no-store, must-revalidate";\
\        add_header Pragma "no-cache";\
\        add_header Expires "0";\
\    }\
' "$NGINX_SITE"

echo "✅ Added /calls/ location to nginx config"
echo ""

# Test nginx configuration
echo "Testing nginx configuration..."
if nginx -t; then
    echo "✅ Nginx config is valid"
    echo ""
    echo "Reloading nginx..."
    systemctl reload nginx
    if [ $? -eq 0 ]; then
        echo "✅ Nginx reloaded successfully"
        echo ""
        echo "📋 Updated configuration:"
        grep -A 7 "location /calls/" "$NGINX_SITE"
    else
        echo "❌ Failed to reload nginx"
        exit 1
    fi
else
    echo "❌ Nginx config has errors!"
    echo "Restoring backup..."
    mv "${NGINX_SITE}.backup."* "$NGINX_SITE"
    exit 1
fi

echo ""
echo "=================================================="
echo "✅ SETUP COMPLETE"
echo "=================================================="
echo ""
echo "Transcripts will now be served from:"
echo "  https://voice.theinsurancedoctors.com/calls/{call_sid}.txt"
echo ""
echo "Files are stored at:"
echo "  /opt/ChatStack/static/calls/"
echo ""
echo "Test with:"
echo "  curl -I https://voice.theinsurancedoctors.com/calls/CAe7c160e22400def1b29117b222064851.txt"
echo ""
