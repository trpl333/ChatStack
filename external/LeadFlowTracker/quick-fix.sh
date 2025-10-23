#!/bin/bash

# Quick fix script for DigitalOcean deployment

echo "🔧 Fixing deployment issues..."

cd /opt/LeadFlowTracker

# Step 1: Test database connectivity
echo ""
echo "📡 Testing database connection..."
echo "Attempting to resolve hostname..."
nslookup db-memory-do-user-17481003-0.c.db.ondigitalocean.com || echo "⚠️  DNS resolution failed"

echo ""
echo "Testing connection to database..."
timeout 5 bash -c 'cat < /dev/null > /dev/tcp/db-memory-do-user-17481003-0.c.db.ondigitalocean.com/25061' 2>/dev/null && echo "✅ Port 25061 is reachable" || echo "❌ Port 25061 is NOT reachable"

# Step 2: Check if database is VPC-only
echo ""
echo "📋 Database Connection Info:"
echo "This database might be VPC-only (accessible only from within DigitalOcean's private network)"
echo "Current server IP: $(curl -s ifconfig.me)"
echo ""

# Step 3: Check DigitalOcean database settings
echo "⚠️  IMPORTANT: Check your DigitalOcean database settings:"
echo "   1. Go to: https://cloud.digitalocean.com/databases"
echo "   2. Click on: db-memory"
echo "   3. Go to: Settings → Trusted Sources"
echo "   4. Check if your droplet IP ($(curl -s ifconfig.me)) is allowed"
echo ""
echo "   OR add this droplet to the database's VPC network:"
echo "   1. Go to database Settings"
echo "   2. Under 'Networking', check if VPC is enabled"
echo "   3. Add this droplet to the same VPC"
echo ""

read -p "Press Enter after you've verified database access settings..."

# Step 4: Try database push again
echo ""
echo "🗄️  Attempting database schema push..."
npm run db:push --force

# Step 5: Start with PM2 using .cjs file
echo ""
echo "🚀 Starting application with PM2..."
pm2 start ecosystem.config.cjs
pm2 save

# Step 6: Check status
echo ""
echo "================================"
echo "✅ Current Status:"
echo "================================"
pm2 status

echo ""
echo "Testing local connection..."
curl -s http://localhost:5001/api/leads | head -20 || echo "❌ App not responding yet"

echo ""
echo "================================"
echo "📝 Next Steps:"
echo "================================"
echo "1. If database connection still fails, you need to:"
echo "   - Add this droplet's IP to database trusted sources, OR"
echo "   - Add this droplet to the database's VPC network"
echo ""
echo "2. Once app is running, get SSL certificate:"
echo "   certbot --nginx -d leads.theinsurancedoctors.com"
echo ""
echo "3. Check logs:"
echo "   pm2 logs leadflow-tracker"
echo "================================"
