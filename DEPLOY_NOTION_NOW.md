# 🚀 Deploy Notion CRM - Simple 3-Step Process

## ✅ Files Fixed in Replit:
- `services/notion-sync.js` - Fixed authentication (works with NOTION_TOKEN)
- `docker-compose-notion.yml` - Correct network configuration
- `deploy-notion-fixed.sh` - Automated deployment script

---

## Step 1: Push Fixed Files to GitHub (Run in Replit Shell)

```bash
cd /home/runner/workspace

# Check what files changed
git status

# Add the fixed Notion files
git add services/notion-sync.js \
        services/notion-api-server.js \
        docker-compose-notion.yml \
        Dockerfile.notion \
        deploy-notion-fixed.sh \
        PRODUCTION_FIX_NOTION.md \
        NOTION_INTEGRATION_GUIDE.md \
        DEPLOY_NOTION_NOW.md

# Commit with clear message
git commit -m "Fix: Notion CRM authentication for production (direct NOTION_TOKEN support)"

# Push to GitHub
git push origin main
```

---

## Step 2: Pull on Production Server

**On your DigitalOcean server:**

```bash
cd /opt/ChatStack

# Discard any local changes that conflict
git reset --hard HEAD

# Pull the fixed code
git pull origin main

# Verify the fix is present
grep -n "async function getAccessToken" services/notion-sync.js | head -1
# Should show line number where function is defined

# Verify .env has required variables
echo "=== Checking Environment ==="
grep "NOTION_TOKEN=" .env
grep "NOTION_PARENT_PAGE_ID=" .env

# If NOTION_PARENT_PAGE_ID is missing, add it:
# echo "NOTION_PARENT_PAGE_ID=28815c5368f980ce994cd9ee55ab6c49" >> .env
```

---

## Step 3: Deploy with Clean Build

**On your DigitalOcean server:**

```bash
cd /opt/ChatStack

# Stop existing service
docker-compose -f docker-compose-notion.yml down

# Remove old images (force clean build)
docker image rm -f chatstack-notion:latest 2>/dev/null || true
docker image rm -f chatstack-notion-service 2>/dev/null || true

# Build with NO CACHE (critical!)
docker build -f Dockerfile.notion -t chatstack-notion:latest --no-cache .

# Start service
docker-compose -f docker-compose-notion.yml up -d

# Wait for initialization
sleep 5

# Check logs
echo "=== SERVICE LOGS ==="
docker logs chatstack-notion-service-1 --tail 25

# Health check
echo ""
echo "=== HEALTH CHECK ==="
curl http://localhost:8200/health
echo ""

# Restart orchestrator to connect
docker-compose restart orchestrator-worker
```

---

## ✅ Expected Success Output:

**Logs should show:**
```
✅ Using direct NOTION_TOKEN for authentication
🏗  Using parent page: 28815c5368f980ce994cd9ee55ab6c49
✅ Created database: Insurance Customers
✅ Created database: Call Logs
✅ Created database: Insurance Policies
✅ Created database: Tasks & Follow-ups
✅ Created database: Appointments & Callbacks
✅ Created database: Communications Log
📊 Databases initialized: 6
🚀 Notion API Server running on http://0.0.0.0:8200
```

**Health check should return:**
```json
{"status":"ok","notion_ready":true,"databases":6}
```

---

## 🔥 Troubleshooting

### If still getting "getAccessToken is not defined":

```bash
# Verify the file inside container
docker exec chatstack-notion-service-1 grep -n "async function getAccessToken" /app/services/notion-sync.js

# If not found, manually copy:
docker cp /opt/ChatStack/services/notion-sync.js chatstack-notion-service-1:/app/services/notion-sync.js
docker restart chatstack-notion-service-1
```

### If "notion_ready": false:

```bash
# Check environment variables inside container
docker exec chatstack-notion-service-1 env | grep NOTION

# Should show:
# NOTION_TOKEN=ntn_xxx...
# NOTION_PARENT_PAGE_ID=28815c5368f980ce994cd9ee55ab6c49
```

---

## 🎯 After Success:

1. **Make a test call** to your Twilio number
2. **Check Notion** - Open "NeuroSphere CRM Home" page
3. **Verify databases created** with call logged

---

**That's it! Simple 3-step deployment.** 🚀
