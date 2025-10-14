#!/bin/bash
# Configure Nginx for neurospherevoice.com
# Run with sudo on DigitalOcean

set -e

echo "🔧 Configuring Nginx for neurospherevoice.com..."

# Get server IP
SERVER_IP=$(curl -s ifconfig.me)
echo "📍 Server IP: $SERVER_IP"

# Create Nginx config
cat > /etc/nginx/sites-available/neurospherevoice-com << 'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name neurospherevoice.com www.neurospherevoice.com;

    # Serve static customer site files
    root /var/www/neurospherevoice;
    index index.html pricing.html;

    # Static files
    location / {
        try_files $uri $uri/ =404;
    }

    # Proxy API requests to Flask backend
    location /api/ {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Proxy admin panel (optional - keep on main domain)
    location /admin.html {
        proxy_pass http://localhost:5000/admin.html;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# Enable site
ln -sf /etc/nginx/sites-available/neurospherevoice-com /etc/nginx/sites-enabled/

# Test Nginx config
nginx -t

# Reload Nginx
systemctl reload nginx

echo "✅ Nginx configured for neurospherevoice.com"
echo ""
echo "📋 Next Steps:"
echo "1. Update DNS on Bluehost:"
echo "   - Go to Bluehost DNS management for neurospherevoice.com"
echo "   - Add/Update A record: @ → $SERVER_IP"
echo "   - Add/Update A record: www → $SERVER_IP"
echo ""
echo "2. Wait for DNS propagation (5-30 minutes)"
echo ""
echo "3. Install SSL certificate:"
echo "   sudo certbot --nginx -d neurospherevoice.com -d www.neurospherevoice.com"
echo ""
echo "4. Test: http://neurospherevoice.com/pricing.html"
