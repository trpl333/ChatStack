#!/bin/bash
# Notion CRM Integration - Production Deployment Script (FIXED)
# This script properly deploys the Notion service to DigitalOcean

set -e  # Exit on any error

echo "🚀 Starting Notion CRM Integration Deployment..."
echo "================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check we're in the right directory
if [ ! -f "docker-compose-notion.yml" ]; then
    echo -e "${RED}❌ Error: docker-compose-notion.yml not found${NC}"
    echo "Please run this script from /opt/ChatStack/"
    exit 1
fi

# Step 1: Verify environment variables
echo -e "\n${YELLOW}Step 1: Checking environment variables...${NC}"

if ! grep -q "NOTION_TOKEN=" .env; then
    echo -e "${RED}❌ NOTION_TOKEN not found in .env${NC}"
    echo "Please add: NOTION_TOKEN=your_token_here"
    exit 1
fi

if ! grep -q "NOTION_PARENT_PAGE_ID=" .env; then
    echo -e "${RED}❌ NOTION_PARENT_PAGE_ID not found in .env${NC}"
    echo "Please add: NOTION_PARENT_PAGE_ID=your_page_id_here"
    exit 1
fi

echo -e "${GREEN}✅ Environment variables configured${NC}"

# Step 2: Stop existing container
echo -e "\n${YELLOW}Step 2: Stopping existing container...${NC}"
docker-compose -f docker-compose-notion.yml down 2>/dev/null || true
echo -e "${GREEN}✅ Container stopped${NC}"

# Step 3: Remove old images and cache
echo -e "\n${YELLOW}Step 3: Cleaning Docker cache...${NC}"
docker image rm -f chatstack-notion:latest 2>/dev/null || true
docker image rm -f chatstack-notion-service 2>/dev/null || true
echo -e "${GREEN}✅ Cache cleared${NC}"

# Step 4: Build with NO CACHE (critical!)
echo -e "\n${YELLOW}Step 4: Building Notion service (no cache)...${NC}"
docker build -f Dockerfile.notion -t chatstack-notion:latest --no-cache .

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Build successful${NC}"

# Step 5: Start the service
echo -e "\n${YELLOW}Step 5: Starting Notion service...${NC}"
docker-compose -f docker-compose-notion.yml up -d

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to start service${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Service started${NC}"

# Step 6: Wait for service to initialize
echo -e "\n${YELLOW}Step 6: Waiting for service initialization...${NC}"
sleep 5

# Step 7: Check logs
echo -e "\n${YELLOW}Step 7: Checking service logs...${NC}"
docker logs chatstack-notion-service-1 --tail 20

# Step 8: Health check
echo -e "\n${YELLOW}Step 8: Running health check...${NC}"
HEALTH=$(curl -s http://localhost:8200/health)
echo "Response: $HEALTH"

# Check if notion_ready is true
if echo "$HEALTH" | grep -q '"notion_ready":true'; then
    echo -e "\n${GREEN}✅ SUCCESS! Notion CRM integration is fully operational!${NC}"
    echo -e "${GREEN}   - 6 databases created${NC}"
    echo -e "${GREEN}   - Service ready for call logging${NC}"
    
    # Step 9: Restart orchestrator
    echo -e "\n${YELLOW}Step 9: Restarting orchestrator to connect to Notion...${NC}"
    docker-compose restart orchestrator-worker 2>/dev/null || echo "Note: Restart orchestrator manually with: docker-compose restart orchestrator-worker"
    
    echo -e "\n${GREEN}=================================================${NC}"
    echo -e "${GREEN}🎉 Deployment Complete!${NC}"
    echo -e "${GREEN}=================================================${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Make a test call to your Twilio number"
    echo "2. Check Notion for the call log"
    echo "3. View databases: curl http://localhost:8200/notion/databases | jq"
    
elif echo "$HEALTH" | grep -q '"notion_ready":false'; then
    echo -e "\n${YELLOW}⚠️  Service started but Notion not ready${NC}"
    echo "Possible issues:"
    echo "1. Invalid NOTION_TOKEN"
    echo "2. Integration not shared with parent page"
    echo "3. Invalid NOTION_PARENT_PAGE_ID"
    echo ""
    echo "View full logs: docker logs chatstack-notion-service-1"
    exit 1
else
    echo -e "\n${RED}❌ Service health check failed${NC}"
    echo "View logs: docker logs chatstack-notion-service-1"
    exit 1
fi
