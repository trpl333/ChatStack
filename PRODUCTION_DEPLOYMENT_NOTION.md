# Production Deployment - Notion CRM Integration

## 🚀 Quick Deployment (DigitalOcean)

**Run these commands on your production server at `/opt/ChatStack/`:**

```bash
# 1. Pull latest code (if using Git)
git pull origin main

# 2. Install Node.js dependencies
npm install --production

# 3. Deploy Notion service
bash deploy-notion.sh
```

The script will:
- ✅ Build Docker image
- ✅ Start Notion service (port 8200)
- ✅ Create 6 Notion databases
- ✅ Restart phone system
- ✅ Run health checks
- ✅ Test integration

---

## 📋 Manual Deployment Steps

### **Step 1: Build Notion Service**

```bash
cd /opt/ChatStack

# Build Docker image
docker build -f Dockerfile.notion -t chatstack-notion:latest .

# Start service
docker-compose -f docker-compose-notion.yml up -d

# Verify
docker ps | grep notion
```

### **Step 2: Health Check**

```bash
# Check service health
curl http://localhost:8200/health

# Expected: {"status":"ok","notion_ready":true,"databases":6}

# View databases
curl http://localhost:8200/notion/databases | jq
```

### **Step 3: Restart Phone System**

```bash
# Restart FastAPI to load Notion client
docker-compose restart orchestrator-worker

# Verify integration loaded
docker logs chatstack-orchestrator-worker-1 | grep -i notion
```

---

## 🧪 Testing

### **Test 1: Manual Customer Creation**

```bash
curl -X POST http://localhost:8200/notion/customer \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+19999999999",
    "name": "Test Customer",
    "email": "test@example.com",
    "spouse": "Test Spouse"
  }'
```

**Expected:** `{"success":true,"customer_id":"..."}`

### **Test 2: Live Call Test**

1. Call your Twilio number: `+1 (949) 556-5377`
2. Have a conversation with Samantha
3. Mention family members (e.g., "My wife Kelly...")
4. End the call
5. **Check Notion:**
   - Open Notion → Search "Peterson Insurance CRM"
   - Go to "Insurance Customers" → Find your profile
   - Go to "Call Logs" → See transcript

### **Test 3: Verify Logs**

```bash
# Check Notion service logs
docker logs chatstack-notion-service-1 --tail 50

# Check phone system logs
docker logs chatstack-orchestrator-worker-1 --tail 50 | grep -E "Notion|Customer"
```

---

## 📊 Notion Workspace Setup

### **Access Your CRM**

1. Open Notion
2. Search for **"Peterson Insurance CRM"**
3. Pin to sidebar for quick access

### **Databases Created**

1. **Insurance Customers** - Customer profiles with family info
2. **Call Logs** - Full transcripts of every call
3. **Insurance Policies** - Policy tracking
4. **Tasks & Follow-ups** - Auto-generated from calls
5. **Appointments & Callbacks** - Scheduling
6. **Communications Log** - All customer touchpoints

---

## 🔧 Troubleshooting

### **Issue: Service Not Starting**

```bash
# Check logs
docker logs chatstack-notion-service-1

# Common issues:
# 1. Port 8200 in use → Change NOTION_API_PORT in docker-compose
# 2. OAuth token expired → Re-authorize in Replit
# 3. AI-Memory unreachable → Check network: curl http://172.17.0.1:8100/health
```

### **Issue: Databases Not Created**

```bash
# Manually trigger initialization
curl -X POST http://localhost:8200/notion/init

# Check parent page exists
# Open Notion → Search "Peterson Insurance CRM"
```

### **Issue: Calls Not Logging**

```bash
# Verify phone system can reach Notion service
docker exec chatstack-orchestrator-worker-1 curl http://notion-service:8200/health

# Check for errors
docker logs chatstack-orchestrator-worker-1 | grep -i "notion\|error"
```

---

## 🔄 Updating the Integration

### **Code Changes**

```bash
# 1. Pull latest code
git pull origin main

# 2. Rebuild Notion service
docker-compose -f docker-compose-notion.yml down
docker build -f Dockerfile.notion -t chatstack-notion:latest --no-cache .
docker-compose -f docker-compose-notion.yml up -d

# 3. Restart phone system
docker-compose restart orchestrator-worker
```

### **Schema Changes**

If you modify database schemas in `services/notion-sync.js`:

```bash
# 1. Update code
# 2. Rebuild: docker build -f Dockerfile.notion -t chatstack-notion:latest .
# 3. Restart: docker-compose -f docker-compose-notion.yml up -d
# 4. MANUALLY update existing Notion databases (API doesn't support schema migration)
```

---

## 📈 Monitoring

### **Service Health**

```bash
# Check all services
docker-compose ps

# Notion service metrics
curl http://localhost:8200/health

# Database count
curl http://localhost:8200/notion/databases | jq '.databases | length'
```

### **Call Logging Stats**

Check Notion "Call Logs" database:
- Filter by date
- Group by customer
- Track transfer patterns

---

## 🔐 Security

- ✅ OAuth tokens managed by Replit (auto-refresh)
- ✅ No secrets in code
- ✅ TLS encryption for Notion API
- ✅ Docker network isolation
- ✅ Environment variables for config

---

## 📚 Documentation

- **User Guide:** `NOTION_INTEGRATION_GUIDE.md`
- **Architecture:** `replit.md` (lines 121-146)
- **API Docs:** `NOTION_INTEGRATION_GUIDE.md` → API Reference section
- **Deployment:** This file

---

## ✅ Deployment Checklist

- [ ] Notion OAuth connected via Replit
- [ ] Node.js dependencies installed (`npm install`)
- [ ] Docker image built (`docker build -f Dockerfile.notion`)
- [ ] Service running (`docker-compose -f docker-compose-notion.yml up -d`)
- [ ] Health check passes (`curl http://localhost:8200/health`)
- [ ] 6 databases created (verified in Notion)
- [ ] Phone system restarted (`docker-compose restart orchestrator-worker`)
- [ ] Test call completed and logged to Notion
- [ ] Team has access to Notion workspace

---

## 🎯 Next Steps

1. ✅ **Integration Complete** - All calls now log to Notion
2. 📝 **Add Historical Data** - Import existing customers/policies
3. 📊 **Create Dashboards** - Build Notion views (e.g., "This Week's Calls")
4. 🔄 **Enable Calendar Sync** - Connect Google Calendar (future)
5. 📧 **Email Logging** - Add email communication tracking (future)

---

**Need Help?**

- Check logs: `docker logs chatstack-notion-service-1`
- Review guide: `NOTION_INTEGRATION_GUIDE.md`
- Test API: `curl http://localhost:8200/health`
