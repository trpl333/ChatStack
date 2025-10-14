#!/bin/bash
echo "🧹 Cleaning Notion from Replit codebase..."

# Create backup directory
mkdir -p .notion_backup_replit

# Backup then remove Notion code files
mv app/notion_client.py .notion_backup_replit/ 2>/dev/null || true
mv services/notion-sync.js .notion_backup_replit/ 2>/dev/null || true
mv services/notion-api-server.js .notion_backup_replit/ 2>/dev/null || true
mv services/start-notion-service.sh .notion_backup_replit/ 2>/dev/null || true

# Remove Notion documentation
rm -f NOTION_INTEGRATION_GUIDE.md
rm -f PRODUCTION_DEPLOYMENT_NOTION.md
rm -f PRODUCTION_FIX_NOTION.md
rm -f DEPLOY_NOTION_NOW.md
rm -f NOTION_CUSTOMER_DATABASE.md

# Remove Notion deployment scripts
rm -f deploy-notion.sh
rm -f deploy-notion-fixed.sh
rm -f deploy_notion_customer_db.sh

# Remove Notion Docker files
rm -f Dockerfile.notion
rm -f docker-compose-notion.yml

echo "✅ Notion files backed up to .notion_backup_replit/"
echo "✅ All Notion code removed from Replit"
