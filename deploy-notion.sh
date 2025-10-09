#!/bin/bash
# Deploy Notion Integration to Production

set -e

echo "🚀 Deploying Notion Integration to Peterson Insurance Phone System"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running on production server
if [[ $(hostname) != "chatbot-server" ]]; then
    echo -e "${RED}⚠️  This script must run on the production server (chatbot-server)${NC}"
    echo "Run this on DigitalOcean at /opt/ChatStack/"
    exit 1
fi

echo -e "${BLUE}📋 Step 1: Verify Notion Connection${NC}"
# Check if Notion connector is configured
if [ -z "$REPLIT_CONNECTORS_HOSTNAME" ]; then
    echo -e "${RED}❌ REPLIT_CONNECTORS_HOSTNAME not set${NC}"
    echo "Notion connector must be set up via Replit UI first"
    exit 1
fi
echo -e "${GREEN}✅ Notion connector environment configured${NC}"
echo ""

echo -e "${BLUE}📦 Step 2: Install Node.js Dependencies${NC}"
npm install --production
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

echo -e "${BLUE}🐳 Step 3: Build Notion Service Docker Image${NC}"
docker build -f Dockerfile.notion -t chatstack-notion:latest .
echo -e "${GREEN}✅ Docker image built${NC}"
echo ""

echo -e "${BLUE}🔄 Step 4: Start Notion Service${NC}"
docker-compose -f docker-compose-notion.yml up -d
echo -e "${GREEN}✅ Notion service started${NC}"
echo ""

echo -e "${BLUE}⏳ Step 5: Wait for Service Initialization (30s)${NC}"
sleep 30

echo -e "${BLUE}🏥 Step 6: Health Check${NC}"
HEALTH_STATUS=$(curl -s http://localhost:8200/health | jq -r '.status' 2>/dev/null || echo "error")
if [ "$HEALTH_STATUS" = "ok" ]; then
    echo -e "${GREEN}✅ Notion service is healthy${NC}"
else
    echo -e "${RED}❌ Notion service health check failed${NC}"
    echo "Check logs: docker logs chatstack-notion-service-1"
    exit 1
fi
echo ""

echo -e "${BLUE}📊 Step 7: Verify Databases Created${NC}"
DB_COUNT=$(curl -s http://localhost:8200/notion/databases | jq -r '.databases | length' 2>/dev/null || echo "0")
if [ "$DB_COUNT" -eq "6" ]; then
    echo -e "${GREEN}✅ All 6 Notion databases created successfully${NC}"
    curl -s http://localhost:8200/notion/databases | jq '.databases'
else
    echo -e "${RED}❌ Expected 6 databases, found $DB_COUNT${NC}"
    echo "Check logs: docker logs chatstack-notion-service-1"
fi
echo ""

echo -e "${BLUE}🔄 Step 8: Restart Phone System to Load Integration${NC}"
docker-compose restart orchestrator-worker
sleep 10
echo -e "${GREEN}✅ Phone system restarted${NC}"
echo ""

echo -e "${BLUE}🧪 Step 9: Test Integration${NC}"
# Test customer creation
TEST_RESPONSE=$(curl -s -X POST http://localhost:8200/notion/customer \
  -H "Content-Type: application/json" \
  -d '{"phone":"+19999999999","name":"Test User","spouse":"Test Spouse"}')

if echo "$TEST_RESPONSE" | jq -e '.success' >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Customer creation test passed${NC}"
else
    echo -e "${RED}❌ Customer creation test failed${NC}"
    echo "Response: $TEST_RESPONSE"
fi
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 Notion Integration Deployed Successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "📋 Next Steps:"
echo "1. Open Notion and search for 'Peterson Insurance CRM'"
echo "2. Pin the page to your sidebar for quick access"
echo "3. Make a test call to verify auto-logging"
echo "4. Check the databases to see customer data and call logs"
echo ""
echo "📚 Documentation: /opt/ChatStack/NOTION_INTEGRATION_GUIDE.md"
echo "🔍 Service logs: docker logs chatstack-notion-service-1"
echo "🏥 Health check: curl http://localhost:8200/health"
echo ""
