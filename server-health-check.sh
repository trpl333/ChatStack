#!/bin/bash
# NeuroSphere Voice - Production Server Health Check
# Run this on your DigitalOcean server to verify all services

echo "=================================================="
echo "🏥 NeuroSphere Voice - Server Health Check"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check Docker Services
echo "📦 1. DOCKER SERVICES"
echo "-----------------------------------"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✅ Docker installed${NC}"
    
    # Check docker-compose
    if docker-compose ps &> /dev/null; then
        echo -e "${GREEN}✅ Docker Compose available${NC}"
        echo ""
        echo "Running containers:"
        docker-compose ps
    else
        echo -e "${RED}❌ Docker Compose not found or not in /opt/ChatStack${NC}"
    fi
else
    echo -e "${RED}❌ Docker not installed${NC}"
fi
echo ""

# 2. Check Orchestrator (FastAPI - Port 8001)
echo "🤖 2. ORCHESTRATOR SERVICE (FastAPI)"
echo "-----------------------------------"
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Orchestrator running on port 8001${NC}"
    curl -s http://localhost:8001/health | python3 -m json.tool 2>/dev/null || echo "Response received"
else
    echo -e "${RED}❌ Orchestrator not responding on port 8001${NC}"
fi
echo ""

# 3. Check Web Service (Flask - Port 5000)
echo "🌐 3. WEB SERVICE (Flask)"
echo "-----------------------------------"
if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Web service running on port 5000${NC}"
else
    echo -e "${RED}❌ Web service not responding on port 5000${NC}"
fi
echo ""

# 4. Check Notion API Server (Port 8200)
echo "📊 4. NOTION API SERVER"
echo "-----------------------------------"
if lsof -i :8200 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Process listening on port 8200${NC}"
    lsof -i :8200 | grep LISTEN
    
    # Test health endpoint
    if curl -s http://localhost:8200/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Notion API responding${NC}"
    else
        echo -e "${YELLOW}⚠️  Port open but health check failed${NC}"
    fi
else
    echo -e "${RED}❌ Nothing listening on port 8200${NC}"
    echo "💡 Start with: cd /opt/ChatStack/.notion_backup_replit && node notion-api-server.js"
fi
echo ""

# 5. Check SMS Service (Port 3000)
echo "📱 5. SMS SERVICE"
echo "-----------------------------------"
if lsof -i :3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Process listening on port 3000${NC}"
    lsof -i :3000 | grep LISTEN
else
    echo -e "${RED}❌ Nothing listening on port 3000${NC}"
    echo "💡 Check tmux session: tmux attach -t sendtext"
fi
echo ""

# 6. Check AI-Memory Service Connection
echo "🧠 6. AI-MEMORY SERVICE"
echo "-----------------------------------"
if curl -s http://209.38.143.71:8100/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ AI-Memory service reachable${NC}"
else
    echo -e "${RED}❌ Cannot reach AI-Memory service at 209.38.143.71:8100${NC}"
fi
echo ""

# 7. Check Database
echo "💾 7. DATABASE"
echo "-----------------------------------"
if command -v psql &> /dev/null; then
    if psql -U "$PGUSER" -d "$PGDATABASE" -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL connected${NC}"
    else
        echo -e "${YELLOW}⚠️  PostgreSQL installed but connection failed${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  psql not installed (database may still work via app)${NC}"
fi
echo ""

# 8. Check Environment Variables
echo "🔐 8. ENVIRONMENT VARIABLES"
echo "-----------------------------------"
ENV_FILE="/opt/ChatStack/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}✅ .env file exists${NC}"
    
    # Check critical variables (without showing values)
    vars=("OPENAI_API_KEY" "TWILIO_ACCOUNT_SID" "TWILIO_AUTH_TOKEN" "NOTION_TOKEN" "DATABASE_URL")
    for var in "${vars[@]}"; do
        if grep -q "^${var}=" "$ENV_FILE"; then
            echo -e "${GREEN}  ✓ $var${NC}"
        else
            echo -e "${RED}  ✗ $var missing${NC}"
        fi
    done
else
    echo -e "${RED}❌ .env file not found at $ENV_FILE${NC}"
fi
echo ""

# 9. Check Nginx
echo "🌍 9. NGINX (Web Server)"
echo "-----------------------------------"
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✅ Nginx running${NC}"
    
    # Check SSL certificates
    if [ -f "/etc/letsencrypt/live/voice.theinsurancedoctors.com/fullchain.pem" ]; then
        echo -e "${GREEN}✅ SSL certificate exists${NC}"
    else
        echo -e "${YELLOW}⚠️  SSL certificate not found${NC}"
    fi
else
    echo -e "${RED}❌ Nginx not running${NC}"
fi
echo ""

# 10. Check Disk Space
echo "💿 10. DISK SPACE"
echo "-----------------------------------"
df -h / | tail -n 1 | awk '{
    use = substr($5, 1, length($5)-1);
    if (use > 90) 
        print "\033[0;31m❌ Disk usage: "$5" - CRITICAL\033[0m";
    else if (use > 75)
        print "\033[1;33m⚠️  Disk usage: "$5" - Warning\033[0m";
    else
        print "\033[0;32m✅ Disk usage: "$5"\033[0m";
}'
echo ""

# 11. Recent Logs Check
echo "📋 11. RECENT LOGS"
echo "-----------------------------------"
if [ -d "/opt/ChatStack" ]; then
    echo "Last 5 orchestrator logs:"
    docker-compose logs --tail=5 orchestrator-worker 2>/dev/null || echo "Cannot access logs"
else
    echo -e "${RED}❌ /opt/ChatStack directory not found${NC}"
fi
echo ""

# Summary
echo "=================================================="
echo "✅ HEALTH CHECK COMPLETE"
echo "=================================================="
echo ""
echo "Quick Commands:"
echo "  View logs:    docker-compose logs -f orchestrator-worker"
echo "  Restart:      docker-compose up -d --build orchestrator-worker"
echo "  Notion logs:  pm2 logs notion-api-server"
echo "  SMS logs:     tmux attach -t sendtext"
echo ""
