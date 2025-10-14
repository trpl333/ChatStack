#!/bin/bash

echo "🚀 Deploying Notion Customer Database Integration..."
echo ""

# 1. Pull latest code
echo "📥 Pulling latest code..."
git pull origin main

# 2. Restart Notion service to pick up new schema
echo "🔄 Restarting Notion service..."
docker-compose restart notion-service

# Wait for service to be ready
sleep 5

# 3. Check if Notion service is healthy
echo "🏥 Checking Notion service health..."
curl -s http://localhost:8200/health | jq '.'

# 4. Check database count (should see platform_customers)
echo ""
echo "📊 Checking Notion databases..."
curl -s http://localhost:8200/notion/databases | jq '.'

# 5. Restart Flask web service
echo ""
echo "🔄 Restarting Flask web service..."
docker-compose restart web

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Go to Notion and you should see a new database: 'NeuroSphere Voice Customers'"
echo "2. Test onboarding at: https://neurospherevoice.com/onboarding.html"
echo "3. New customers will automatically save to both PostgreSQL and Notion"
echo ""
echo "🔍 To view customer data:"
echo "   - Notion: Open 'NeuroSphere Voice Customers' database"
echo "   - PostgreSQL: docker exec -it chatstack-web-1 psql \$DATABASE_URL -c 'SELECT * FROM customers;'"
