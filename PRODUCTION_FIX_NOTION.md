# Notion CRM - Production Fix (FINAL)

## ❌ Problem
The `getAccessToken()` function in `notion-sync.js` is broken, causing "ReferenceError: getAccessToken is not defined"

## ✅ Solution
Copy these exact commands to your DigitalOcean server terminal:

### Step 1: Fix the authentication code

```bash
cd /opt/ChatStack

# Backup current file
cp services/notion-sync.js services/notion-sync.js.broken

# Create the fixed authentication block
cat > /tmp/notion-auth-fix.js << 'AUTHFIX'
// Notion OAuth client (handles token refresh automatically)
let connectionSettings = null;

async function getAccessToken() {
  // Priority 1: Use direct NOTION_TOKEN if available (production mode)
  if (process.env.NOTION_TOKEN) {
    const token = process.env.NOTION_TOKEN.trim();
    console.log('✅ Using direct NOTION_TOKEN for authentication');
    return token;
  }
  
  // Priority 2: Use Replit OAuth connector (development mode)
  // Check if cached token is still valid
  if (connectionSettings?.settings?.expires_at) {
    const expiryTime = new Date(connectionSettings.settings.expires_at).getTime();
    if (expiryTime > Date.now()) {
      return connectionSettings.settings.access_token;
    }
  }
  
  // Try to fetch new token from Replit connector
  const hostname = process.env.REPLIT_CONNECTORS_HOSTNAME;
  const xReplitToken = process.env.REPL_IDENTITY 
    ? 'repl ' + process.env.REPL_IDENTITY 
    : process.env.WEB_REPL_RENEWAL 
    ? 'depl ' + process.env.WEB_REPL_RENEWAL 
    : null;

  if (!xReplitToken) {
    console.warn('⚠️ No NOTION_TOKEN or Replit OAuth credentials found');
    return null;
  }

  try {
    const response = await fetch(
      'https://' + hostname + '/api/v2/connection?include_secrets=true&connector_names=notion',
      {
        headers: {
          'Accept': 'application/json',
          'X_REPLIT_TOKEN': xReplitToken
        }
      }
    );
    
    const data = await response.json();
    connectionSettings = data.items?.[0];

    const accessToken = connectionSettings?.settings?.access_token || 
                       connectionSettings?.settings?.oauth?.credentials?.access_token;

    if (accessToken) {
      return accessToken;
    }
  } catch (error) {
    console.error('Failed to fetch Replit OAuth token:', error);
  }
  
  return null;
}

async function getNotionClient() {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    throw new Error('❌ No Notion authentication token available. Set NOTION_TOKEN in environment.');
  }
  return new Client({ auth: accessToken });
}
AUTHFIX

# Replace lines 25-90 in notion-sync.js with the fixed code
sed -i '25,90d' services/notion-sync.js
sed -i '24r /tmp/notion-auth-fix.js' services/notion-sync.js

# Verify the fix
grep -n "async function getAccessToken" services/notion-sync.js
```

### Step 2: Verify .env has required variables

```bash
# Check for NOTION_TOKEN
grep NOTION_TOKEN .env

# Check for NOTION_PARENT_PAGE_ID (should be: 28815c5368f980ce994cd9ee55ab6c49)
grep NOTION_PARENT_PAGE_ID .env

# If NOTION_PARENT_PAGE_ID is missing or wrong, add it:
# echo "NOTION_PARENT_PAGE_ID=28815c5368f980ce994cd9ee55ab6c49" >> .env
```

### Step 3: Deploy with NO CACHE (critical!)

```bash
cd /opt/ChatStack

# Stop current service
docker-compose -f docker-compose-notion.yml down

# Remove old images
docker image rm -f chatstack-notion:latest 2>/dev/null || true
docker image rm -f chatstack-notion-service 2>/dev/null || true

# Build with NO CACHE
docker build -f Dockerfile.notion -t chatstack-notion:latest --no-cache .

# Start service
docker-compose -f docker-compose-notion.yml up -d

# Wait for startup
sleep 5

# Check logs
docker logs chatstack-notion-service-1 --tail 30
```

### Step 4: Verify Success

```bash
# Health check
curl http://localhost:8200/health
```

**Expected output:**
```json
{"status":"ok","notion_ready":true,"databases":6}
```

**Expected in logs:**
```
✅ Using direct NOTION_TOKEN for authentication
✅ Connected to Notion API
✅ Created database: Insurance Customers
✅ Created database: Call Logs
...
📊 Databases initialized: 6
```

### Step 5: Restart Orchestrator

```bash
docker-compose restart orchestrator-worker
```

---

## Troubleshooting

### If you still see "getAccessToken is not defined":
```bash
# Manually inject the fixed file into running container
docker cp /opt/ChatStack/services/notion-sync.js chatstack-notion-service-1:/app/services/notion-sync.js
docker restart chatstack-notion-service-1
```

### If "notion_ready": false:
```bash
# Check if token is valid
docker exec chatstack-notion-service-1 env | grep NOTION

# Should show:
# NOTION_TOKEN=ntn_xxx...
# NOTION_PARENT_PAGE_ID=28815c5368f980ce994cd9ee55ab6c49
```

### If still failing:
```bash
# View full error
docker logs chatstack-notion-service-1 | grep -A 20 "Failed to initialize"
```

---

## ✅ Success Checklist

- [ ] `getAccessToken` function defined (no ReferenceError)
- [ ] NOTION_TOKEN in .env
- [ ] NOTION_PARENT_PAGE_ID=28815c5368f980ce994cd9ee55ab6c49 in .env
- [ ] Built with --no-cache
- [ ] Health check returns `notion_ready: true`
- [ ] 6 databases created in Notion under "NeuroSphere CRM Home"
- [ ] Orchestrator restarted

Once all checked, make a test call and verify it logs to Notion!
