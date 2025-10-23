#!/bin/bash
set -e

echo "🚀 NeuroSphere Voice - Quick Update"
echo "===================================="

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
git pull origin main

# Rebuild and restart all services
echo "🔨 Rebuilding all services..."
docker-compose down
docker-compose up -d --build

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 5

# Show status
echo ""
echo "✅ Update complete! Service status:"
docker-compose ps

# Show recent logs
echo ""
echo "📋 Recent logs (orchestrator-worker):"
docker-compose logs --tail=20 orchestrator-worker

echo ""
echo "✅ All done! Services are running."
echo "💡 To watch live logs: docker-compose logs -f orchestrator-worker"
