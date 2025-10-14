#!/bin/bash
# Deploy ChatStack to DigitalOcean and Rebuild Docker Containers
# This script pushes code updates and rebuilds the Docker containers

set -e

SERVER="root@209.38.143.71"
PROJECT_DIR="/opt/ChatStack"

echo "🚀 Deploying ChatStack Updates to DigitalOcean..."
echo ""

# Step 1: Push latest code to GitHub (if using Git)
echo "📤 Pushing latest code to repository..."
git add .
git commit -m "Deploy: Updated customer API routes and onboarding system" || echo "No changes to commit"
git push origin main || echo "Push failed - continuing anyway"

echo ""
echo "📥 Pulling latest code on DigitalOcean server..."

# Step 2: SSH to server and pull latest code
ssh $SERVER << 'ENDSSH'
    cd /opt/ChatStack
    
    # Pull latest code
    git pull origin main || echo "Git pull failed"
    
    # Stop containers
    echo "🛑 Stopping Docker containers..."
    docker-compose down
    
    # Rebuild Flask web container with no cache
    echo "🔨 Rebuilding Flask web container..."
    docker-compose build --no-cache web
    
    # Start containers
    echo "🚀 Starting Docker containers..."
    docker-compose up -d
    
    # Wait for services to start
    echo "⏳ Waiting for services to start..."
    sleep 15
    
    # Check if containers are running
    echo "✅ Container status:"
    docker-compose ps
    
    echo ""
    echo "🧪 Testing customer API endpoint..."
    curl -s http://localhost:5000/api/customers/onboard \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{"business_name":"Test","contact_name":"John","email":"test@test.com","phone":"555","package_tier":"starter","agent_name":"AI","greeting_template":"Hi","openai_voice":"alloy","personality_preset":"professional"}' \
        | head -20
    
    echo ""
    echo "✅ Deployment complete!"
ENDSSH

echo ""
echo "🎉 Deployment finished!"
echo ""
echo "🧪 Test the API from the web:"
echo "curl https://neurospherevoice.com/api/customers/onboard -X POST -H 'Content-Type: application/json' -d '{\"business_name\":\"Test\"}'"
