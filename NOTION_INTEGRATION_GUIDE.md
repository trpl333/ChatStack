# Notion Integration Guide - Peterson Insurance AI Phone System

## 📋 Overview

This integration connects your AI phone system with Notion, creating a complete CRM/knowledge base where **all customer data, calls, policies, and communications are automatically logged and accessible to Samantha (your AI agent)**.

### What This Provides

✅ **Automatic Call Logging** - Every call is saved with full transcript  
✅ **Customer Profiles** - Auto-created/updated with family info, preferences  
✅ **AI Memory Enhancement** - Samantha reads from Notion during calls  
✅ **Complete CRM** - Policies, tasks, calendar, communications tracking  
✅ **Bi-directional Sync** - Notion ↔ AI-Memory ↔ Phone System  

---

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Twilio     │ ───> │  FastAPI     │ ───> │  Notion API     │
│  Phone Call │      │  Phone System│      │  Server (8200)  │
└─────────────┘      └──────────────┘      └─────────────────┘
                            │                        │
                            ▼                        ▼
                     ┌──────────────┐      ┌─────────────────┐
                     │  AI-Memory   │ <─── │  Notion CRM     │
                     │  Service     │      │  Databases      │
                     └──────────────┘      └─────────────────┘
```

### Flow:
1. **Call starts** → AI loads customer data from AI-Memory
2. **AI-Memory** pulls latest from Notion databases
3. **Conversation happens** → AI knows family names, policies, history
4. **Call ends** → System logs to both AI-Memory AND Notion
5. **Notion updated** → Customer profile, call log, tasks created

---

## 📊 Notion Databases Created

The system automatically creates these databases in your Notion workspace:

### 1. **Insurance Customers**
- Customer Name, Phone, Email, Address
- Family Members (Spouse, Children)
- Related Policies
- Last Call Date, Total Calls
- Status (Active/Inactive/VIP)
- Notes & Tags

### 2. **Call Logs**
- Call Date & Duration
- Customer (relation)
- Full Transcript
- AI Summary
- Transfer Information
- Call Type (Inbound/Outbound/Callback)
- Status (Completed/Transferred/Voicemail)

### 3. **Insurance Policies**
- Policy Number & Type (Auto/Home/Life/Business)
- Customer (relation)
- Premium, Start/Renewal Dates
- Coverage Details
- Status (Active/Expired/Pending)

### 4. **Tasks & Follow-ups**
- Task Description
- Customer (relation)
- Created From Call (relation)
- Assigned To (John/Milissa/Colin/Samantha AI)
- Due Date & Priority
- Status (To Do/In Progress/Done)

### 5. **Appointments & Callbacks**
- Title & Customer (relation)
- Date & Time
- Type (Appointment/Callback/Renewal Reminder)
- With (John/Milissa/Colin)
- Status (Scheduled/Completed/Cancelled)

### 6. **Communications Log**
- Subject & Customer (relation)
- Date & Type (Email/SMS/Call/Letter)
- Direction (Inbound/Outbound)
- Content & Attachments

---

## 🚀 Deployment

### **Step 1: Verify Notion Connection**

The Notion connector is already set up via Replit OAuth. Verify it's working:

```bash
# Check connection status
curl http://localhost:8200/health

# Expected response:
# {"status":"ok","notion_ready":true,"databases":6}
```

### **Step 2: Start Notion API Server**

**Option A: Standalone (Development)**

```bash
# Install dependencies (already done)
npm install

# Start the service
node services/notion-api-server.js
```

**Option B: Docker (Production)**

Add to your `docker-compose.yml`:

```yaml
services:
  # ... existing services ...

  notion-service:
    build: .
    command: node services/notion-api-server.js
    ports:
      - "8200:8200"
    environment:
      - AI_MEMORY_URL=http://172.17.0.1:8100
      - NOTION_API_PORT=8200
      - REPLIT_CONNECTORS_HOSTNAME=${REPLIT_CONNECTORS_HOSTNAME}
      - REPL_IDENTITY=${REPL_IDENTITY}
      - WEB_REPL_RENEWAL=${WEB_REPL_RENEWAL}
    networks:
      - chatstack_network
    restart: unless-stopped
```

Then deploy:

```bash
cd /opt/ChatStack

# Rebuild with Notion service
docker-compose up -d --build notion-service

# Verify it's running
docker logs chatstack-notion-service-1

# Check databases were created
curl http://localhost:8200/notion/databases
```

### **Step 3: Configure Production Environment**

Update `.env` file (or use existing secrets):

```bash
# Notion service URL (from Docker network)
NOTION_API_URL=http://notion-service:8200

# AI-Memory URL (existing)
AI_MEMORY_URL=http://172.17.0.1:8100
```

### **Step 4: Restart Phone System**

```bash
# Restart FastAPI to load Notion client
docker-compose restart orchestrator-worker

# Verify integration
docker logs chatstack-orchestrator-worker-1 | grep -i notion
```

---

## 🧪 Testing

### **Test 1: Database Creation**

```bash
curl http://localhost:8200/notion/databases
```

**Expected:** JSON with 6 database IDs (customers, calls, policies, tasks, calendar, communications)

### **Test 2: Customer Creation**

```bash
curl -X POST http://localhost:8200/notion/customer \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+19495565377",
    "name": "John Smith",
    "email": "john@example.com",
    "spouse": "Kelly"
  }'
```

**Expected:** `{"success":true,"customer_id":"..."}`

**Verify in Notion:** Check "Insurance Customers" database for new entry

### **Test 3: Call Logging**

```bash
curl -X POST http://localhost:8200/notion/call-log \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+19495565377",
    "transcript": "Customer: Hi, I need help\nSamantha: Of course! How can I help you?",
    "summary": "Customer called for general assistance",
    "transfer_to": "John"
  }'
```

**Expected:** `{"success":true}`

**Verify in Notion:** Check "Call Logs" database for new entry

### **Test 4: Live Call Test**

1. Call your Twilio number
2. Have a conversation with Samantha
3. Mention family members (e.g., "My wife Kelly...")
4. End the call
5. Check Notion:
   - "Insurance Customers" → Your profile updated with spouse name
   - "Call Logs" → Full transcript saved
   - AI-Memory service → Structured memories created

---

## 🔧 API Reference

### **POST /notion/customer**

Create or update customer profile.

**Request:**
```json
{
  "phone": "+19495565377",
  "name": "John Smith",
  "email": "john@example.com",
  "spouse": "Kelly"
}
```

**Response:**
```json
{
  "success": true,
  "customer_id": "notion-page-id",
  "message": "Customer synced to Notion"
}
```

### **POST /notion/call-log**

Log a completed call.

**Request:**
```json
{
  "phone": "+19495565377",
  "transcript": "Full conversation...",
  "summary": "Customer called about...",
  "transfer_to": "John" // optional
}
```

**Response:**
```json
{
  "success": true,
  "message": "Call logged to Notion"
}
```

### **POST /notion/sync-to-memory**

Sync customer data from Notion to AI-Memory.

**Request:**
```json
{
  "customer_id": "notion-page-id"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Customer data synced to AI-Memory"
}
```

### **GET /notion/databases**

Get all database IDs.

**Response:**
```json
{
  "success": true,
  "databases": {
    "customers": "db-id-1",
    "calls": "db-id-2",
    "policies": "db-id-3",
    "tasks": "db-id-4",
    "calendar": "db-id-5",
    "communications": "db-id-6"
  }
}
```

---

## 🔄 Data Flow Examples

### **Example 1: New Caller**

1. **Call starts** → User ID: 9495565377
2. **AI-Memory search** → No memories found (new caller)
3. **Samantha greets** → "Good afternoon! This is Samantha..."
4. **Conversation** → "My wife's name is Kelly"
5. **Memory extracted** → `spouse_name: Kelly`
6. **Call ends:**
   - **Notion Customer** → Created with name, phone, spouse
   - **Notion Call Log** → Transcript saved
   - **AI-Memory** → Structured memories stored

### **Example 2: Returning Caller**

1. **Call starts** → User ID: 9495565377
2. **AI-Memory loads** → 50 memories found
3. **Notion sync** → Latest customer data loaded
4. **Samantha greets** → "Hi, this is Samantha. Is this John?"
5. **Context aware** → "How's Kelly doing?"
6. **Call ends:**
   - **Notion Customer** → Updated with last call date
   - **Notion Call Log** → New entry with transcript
   - **Call counter** → Incremented

---

## 📈 Advanced Features

### **Calendar Integration** (Future Enhancement)

```javascript
// Create appointment from call
await notion.pages.create({
  parent: { database_id: calendarDbId },
  properties: {
    'Title': { title: [{ text: { content: 'Policy Review' } }] },
    'Date & Time': { date: { start: '2025-10-15T14:00:00' } },
    'Customer': { relation: [{ id: customerId }] }
  }
});
```

### **Email Integration** (Future Enhancement)

```javascript
// Log email communication
await notion.pages.create({
  parent: { database_id: communicationsDbId },
  properties: {
    'Subject': { title: [{ text: { content: emailSubject } }] },
    'Type': { select: { name: 'Email' } },
    'Content': { rich_text: [{ text: { content: emailBody } }] }
  }
});
```

---

## 🐛 Troubleshooting

### **Issue: Databases not created**

```bash
# Check Notion service logs
docker logs chatstack-notion-service-1

# Manually trigger initialization
curl -X POST http://localhost:8200/notion/init
```

### **Issue: Calls not logging**

```bash
# Check FastAPI logs for Notion errors
docker logs chatstack-orchestrator-worker-1 | grep -i notion

# Verify Notion service is accessible
docker exec chatstack-orchestrator-worker-1 curl http://notion-service:8200/health
```

### **Issue: Token expired**

The Replit connector automatically refreshes OAuth tokens. If issues persist:

```bash
# Re-authorize Notion connection in Replit UI
# Then restart services
docker-compose restart
```

---

## 📝 Notion Workspace Setup

### **Recommended Structure**

```
Peterson Insurance CRM (Parent Page)
├── 📋 Insurance Customers
├── 📞 Call Logs
├── 📄 Insurance Policies
├── ✅ Tasks & Follow-ups
├── 📅 Appointments & Callbacks
└── 📧 Communications Log
```

### **Access the CRM**

After deployment, find the parent page:
1. Open Notion
2. Search for "Peterson Insurance CRM"
3. Pin it to your sidebar for quick access

---

## 🎯 Next Steps

1. ✅ **Databases Created** - Verified 6 databases exist
2. ✅ **Call Logging Active** - Every call auto-logs to Notion
3. 🔄 **Manual Data Entry** - Add existing customers/policies to Notion
4. 📊 **Dashboard Views** - Create Notion views (e.g., "Calls This Week")
5. 🤖 **AI Enhancements** - Add more structured memory extraction
6. 📧 **Email Integration** - Log all communications
7. 📅 **Calendar Sync** - Sync with Google Calendar

---

## 🔐 Security Notes

- OAuth tokens managed by Replit (auto-refresh)
- No secrets stored in code
- Notion API uses TLS 1.2+ encryption
- Production: Use Docker secrets for env vars
- Access control via Notion workspace permissions

---

## 📚 Resources

- **Notion API Docs:** https://developers.notion.com/
- **Replit Connectors:** https://docs.replit.com/hosting/connect-external-services
- **Support:** Check `replit.md` for architecture details
