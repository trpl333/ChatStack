#!/bin/bash
# Deployment script for OpenAI Realtime API integration to DigitalOcean server
# Usage: ./deploy_realtime_to_do.sh [server_ip] [ssh_user]

set -e  # Exit on error

# Configuration
SERVER_IP="${1:-209.38.143.71}"
SSH_USER="${2:-root}"
REMOTE_PATH="/opt/ChatStack"
LOCAL_FILES=(
    "main.py"
    "app/realtime_bridge.py"
)

echo "🚀 Starting deployment to DO server at $SSH_USER@$SERVER_IP:$REMOTE_PATH"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Backup current code on server
echo ""
echo "📦 Step 1: Creating backup of current code..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack
# Create backup with timestamp
BACKUP_DIR="/opt/ChatStack_backup_$(date +%Y%m%d_%H%M%S)"
echo "Creating backup at: $BACKUP_DIR"
cp -r /opt/ChatStack "$BACKUP_DIR"
echo "✅ Backup created successfully"
ENDSSH

# Step 2: Upload new files
echo ""
echo "📤 Step 2: Uploading updated files..."
for file in "${LOCAL_FILES[@]}"; do
    echo "  → Uploading $file"
    scp "$file" "$SSH_USER@$SERVER_IP:$REMOTE_PATH/$file"
done
echo "✅ Files uploaded successfully"

# Step 3: Install dependencies on server
echo ""
echo "📥 Step 3: Installing Python dependencies..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack
# Install flask-sock and ensure all dependencies are up to date
docker-compose exec web pip install flask-sock websockets python-socketio openai>=1.58.1 || \
    echo "⚠️  Could not install via docker-compose exec, will install on container restart"
echo "✅ Dependencies prepared"
ENDSSH

# Step 4: Update Twilio webhook URL (optional - manual step)
echo ""
echo "📞 Step 4: Twilio webhook configuration"
echo "⚠️  MANUAL STEP REQUIRED:"
echo ""
echo "To test the Realtime API integration, you need to update your Twilio phone number webhook:"
echo ""
echo "  1. Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming"
echo "  2. Click on your phone number"
echo "  3. Update 'A CALL COMES IN' webhook to:"
echo "     https://voice.theinsurancedoctors.com/phone/incoming-realtime"
echo ""
echo "  OR keep using /phone/incoming for the old system (both will work)"
echo ""
read -p "Press Enter when ready to continue..."

# Step 5: Restart Docker containers
echo ""
echo "🔄 Step 5: Restarting Docker containers..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack
echo "Restarting containers..."
docker-compose restart web
echo "✅ Containers restarted"

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10
ENDSSH

# Step 6: Verify deployment
echo ""
echo "✅ Step 6: Verifying deployment..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack

# Check if containers are running
echo "Checking Docker container status:"
docker-compose ps

# Check Flask logs for errors
echo ""
echo "Recent Flask logs (last 20 lines):"
docker-compose logs --tail=20 web

# Test endpoints
echo ""
echo "Testing endpoint availability:"
curl -s -o /dev/null -w "  /phone/incoming-realtime: %{http_code}\n" \
    -X POST https://voice.theinsurancedoctors.com/phone/incoming-realtime \
    -d "From=%2B1234567890&CallSid=test123" || echo "  ⚠️ Endpoint test failed"

echo ""
echo "✅ Deployment verification complete"
ENDSSH

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. ✅ Code deployed to $REMOTE_PATH"
echo "2. ✅ Docker containers restarted"
echo "3. ⚠️  Update Twilio webhook to use /phone/incoming-realtime"
echo "4. 📞 Test by calling your Twilio number"
echo "5. 📊 Monitor logs: ssh $SSH_USER@$SERVER_IP 'docker-compose -f $REMOTE_PATH/docker-compose.yml logs -f web'"
echo ""
echo "🔧 Rollback if needed:"
echo "   ssh $SSH_USER@$SERVER_IP 'ls -la /opt/ChatStack_backup_*'"
echo "   ssh $SSH_USER@$SERVER_IP 'cp -r /opt/ChatStack_backup_TIMESTAMP/* /opt/ChatStack/ && cd /opt/ChatStack && docker-compose restart'"
echo ""
echo "📖 Endpoint URLs:"
echo "   Old system: https://voice.theinsurancedoctors.com/phone/incoming"
echo "   New Realtime API: https://voice.theinsurancedoctors.com/phone/incoming-realtime"
echo ""
