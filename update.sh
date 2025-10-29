#!/bin/bash
set -e

echo "🚀 NeuroSphere Voice - Quick Update"
echo "===================================="

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
git pull origin main

# Rebuild orchestrator-worker (FastAPI backend - phone calls)
echo "🔨 Rebuilding orchestrator-worker (FastAPI backend)..."
docker-compose build --no-cache orchestrator-worker

# Rebuild web (Flask admin panel)
echo "🔨 Rebuilding web (Flask admin panel)..."
docker-compose build --no-cache web

# Restart both services
echo "🔄 Restarting services..."
docker-compose up -d orchestrator-worker web

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 5

# Show status
echo ""
echo "✅ Update complete! Service status:"
docker-compose ps

# Show recent logs for both services
echo ""
echo "📋 Recent logs (orchestrator-worker - phone system):"
docker-compose logs --tail=20 orchestrator-worker

echo ""
echo "📋 Recent logs (web - admin panel):"
docker-compose logs --tail=20 web

echo ""
echo "✅ All done! Services are running."
echo "💡 To watch live logs:"
echo "   Orchestrator: docker-compose logs -f orchestrator-worker"
echo "   Admin Panel:  docker-compose logs -f web"
