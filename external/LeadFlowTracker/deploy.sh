#!/bin/bash

# LeadFlowTracker Deployment Script for DigitalOcean
# Run this script on your DigitalOcean droplet after git pull

set -e  # Exit on error

echo "🚀 Deploying LeadFlowTracker..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}❌ Error: package.json not found. Run this from the project root.${NC}"
    exit 1
fi

# Install dependencies
echo -e "${BLUE}📦 Installing dependencies...${NC}"
npm install

# Build the application
echo -e "${BLUE}🔨 Building frontend...${NC}"
npm run build

# Push database schema
echo -e "${BLUE}🗄️  Updating database schema...${NC}"
npm run db:push || npm run db:push --force

# Restart PM2 process
echo -e "${BLUE}♻️  Restarting application...${NC}"
if pm2 list | grep -q "leadflow-tracker"; then
    pm2 restart leadflow-tracker
else
    echo -e "${BLUE}🆕 Starting application for the first time...${NC}"
    pm2 start ecosystem.config.js
    pm2 save
fi

# Show status
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Status:"
pm2 status leadflow-tracker

echo ""
echo -e "${GREEN}🎉 LeadFlowTracker deployed successfully!${NC}"
echo "View logs: pm2 logs leadflow-tracker"
echo "Check status: pm2 status"
echo "Stop: pm2 stop leadflow-tracker"
echo "Restart: pm2 restart leadflow-tracker"
