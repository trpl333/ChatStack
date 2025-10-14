#!/bin/bash
# Pacific Time Tool Deployment Script
# Run this on your DigitalOcean server

cd /opt/ChatStack

echo "🕐 Installing Pacific Time Tool..."

# Backup
cp app/tools.py app/tools.py.backup.$(date +%s)

# Download from GitHub (once pushed)
echo "📥 Pulling from GitHub..."
git pull origin main

# Restart
echo "🔄 Restarting orchestrator..."
docker-compose restart orchestrator-worker

# Wait
sleep 5

# Test
echo "🧪 Testing tool..."
curl -X POST http://localhost:8001/v1/tools/get_current_time \
  -H "Content-Type: application/json" \
  -d '{"format": "12-hour"}' | jq '.'

echo ""
echo "✅ If you see time data above, it's working!"
echo "📞 Call your Twilio number and ask 'What time is it?'"
