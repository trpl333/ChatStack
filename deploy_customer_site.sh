#!/bin/bash
# Deploy Customer Site to DigitalOcean
# Run this script on your DigitalOcean server

set -e

echo "🚀 Deploying Customer Purchase & Onboarding Site..."

# Create directory for customer site
sudo mkdir -p /var/www/neurospherevoice
sudo chown -R $USER:$USER /var/www/neurospherevoice

# Copy static files
echo "📁 Copying customer site files..."
cp -r static/pricing.html /var/www/neurospherevoice/
cp -r static/onboarding.html /var/www/neurospherevoice/
cp -r static/dashboard.html /var/www/neurospherevoice/

# Create index redirect
cat > /var/www/neurospherevoice/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url=/pricing.html">
    <title>Redirecting...</title>
</head>
<body>
    <p>Redirecting to pricing page...</p>
</body>
</html>
EOF

echo "✅ Files deployed to /var/www/neurospherevoice/"

# The Flask backend API routes are already in main.py on port 5000
# Nginx will proxy API requests to localhost:5000

echo ""
echo "📝 Next steps:"
echo "1. Run: sudo ./configure_nginx_neurosphere.sh"
echo "2. Update DNS: Point neurospherevoice.com A record to your DO server IP"
echo "3. Run: sudo certbot --nginx -d neurospherevoice.com -d www.neurospherevoice.com"
