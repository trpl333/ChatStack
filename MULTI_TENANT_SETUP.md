# Multi-Tenant AI Phone System - Setup Guide

## ✅ What's Been Built

Your AI phone system now supports **multiple customers**, each with their own:
- 🎭 Custom AI personality (30 personality sliders)
- 🎤 Custom greeting messages  
- 🗣️ Custom voice selection (OpenAI voices)
- 📱 Dedicated Twilio phone number
- 💾 Isolated conversation memory (customer-namespaced)

## 🏗️ Architecture Overview

### How It Works:

1. **Customer Onboarding** → Customer completes onboarding at neurospherevoice.com
2. **Phone Number Assignment** → Each customer gets a Twilio number assigned to them
3. **Call Routing** → When someone calls a Twilio number:
   - Twilio sends `To` field (the number that was called)
   - Flask webhook looks up customer by `To` number
   - Loads customer-specific settings (agent name, greeting, personality)
   - Passes customer context to orchestrator via WebSocket parameters
4. **Memory Isolation** → Conversations stored as `customer_{id}_user_{phone}`
5. **AI Response** → Orchestrator uses customer-specific settings to respond

### Key Files Modified:

**Flask Webhook** (`main.py`):
- `handle_incoming_call_realtime()` - Multi-tenant phone webhook
  - Extracts `To` number (which Twilio number was called)
  - Queries `customers` table by `twilio_phone_number`
  - Passes customer settings to orchestrator

**FastAPI Orchestrator** (`app/main.py`):
- `media_stream_endpoint()` - WebSocket handler
  - Receives customer context via custom parameters
  - Creates customer-namespaced thread_id
  - Uses customer-specific settings (or falls back to admin defaults)

**Database** (`customer_models.py`):
- `customers` table with per-customer AI config
- `customer_configurations` for history tracking

## 🚀 Deployment Steps

### 1. Deploy Updated Code to DigitalOcean

```bash
# From your local machine, run the deployment script:
./deploy_to_digitalocean.sh

# OR manually:
ssh root@209.38.143.71
cd /opt/ChatStack
git pull origin main
docker-compose down
docker-compose build --no-cache web orchestrator-worker
docker-compose up -d
```

### 2. Assign Phone Number to Test Customer

You need to manually assign your Twilio number to a customer in the database:

```bash
# SSH to server
ssh root@209.38.143.71

# Connect to PostgreSQL
docker exec -it chatstack-web-1 psql $DATABASE_URL

# Check existing customers
SELECT id, business_name, email, twilio_phone_number FROM customers;

# Assign phone number to a customer (replace CUSTOMER_ID)
UPDATE customers 
SET twilio_phone_number = '+18052654625' 
WHERE id = 1;  -- Use the actual customer ID

# Verify
SELECT id, business_name, agent_name, openai_voice, twilio_phone_number FROM customers WHERE id = 1;

# Exit
\q
```

### 3. Configure Twilio Webhook

1. Go to https://console.twilio.com/
2. Click **Phone Numbers** → **Active Numbers** → **(805) 265-4625**
3. Under **Voice Configuration**:
   - **A CALL COMES IN**: `https://voice.theinsurancedoctors.com/phone/incoming-realtime`
   - **HTTP Method**: `POST`
4. Click **Save**

## 🧪 Testing Multi-Tenancy

### Test 1: Customer-Specific Greeting
```bash
# 1. Update customer greeting in database
UPDATE customers 
SET greeting_template = 'Hi! This is Sarah from Acme Corp. How can I help you today?' 
WHERE id = 1;

# 2. Call the number: (805) 265-4625
# 3. You should hear: "Hi! This is Sarah from Acme Corp..."
```

### Test 2: Customer-Specific Voice
```bash
# Update OpenAI voice
UPDATE customers 
SET openai_voice = 'nova'  -- Options: alloy, echo, fable, onyx, nova, shimmer
WHERE id = 1;

# Call again - you should hear a different voice
```

### Test 3: Customer-Specific Personality
```bash
# Set friendly personality
UPDATE customers 
SET personality_sliders = '{"warmth": 90, "empathy": 85, "directness": 40}'::json
WHERE id = 1;

# Call again - AI should be warmer and more empathetic
```

### Test 4: Multiple Customers
```bash
# Create a second customer
INSERT INTO customers (email, business_name, contact_name, phone, package_tier, agent_name, openai_voice, greeting_template, twilio_phone_number)
VALUES ('customer2@test.com', 'Tech Solutions Inc', 'John Smith', '555-0002', 'professional', 
        'Alex', 'shimmer', 'Hello! This is Alex from Tech Solutions. What can I do for you?', 
        '+15551234567');  -- Use a different Twilio number

# Configure Twilio webhook for second number to same endpoint
# Each will route to correct customer automatically!
```

## 🔍 Debugging

### View Logs
```bash
# Flask logs (webhook)
docker logs chatstack-web-1 --tail 100 -f

# Orchestrator logs (AI)
docker logs chatstack-orchestrator-worker-1 --tail 100 -f

# Look for these log lines:
# ✅ Found customer X: Business Name
# 🏢 Multi-tenant mode: Customer X
# 👤 Customer Context: ID=X, Agent=Name, Voice=voice
```

### Check Customer Lookup
```bash
# Test customer lookup
curl http://localhost:5000/phone/incoming-realtime \
  -X POST \
  -d "From=%2B15551234567&To=%2B18052654625&CallSid=TEST123"

# Should return TwiML with customer-specific parameters
```

### Verify Memory Namespacing
```bash
# After a call, check AI-Memory for namespaced storage
curl http://209.38.143.71:8100/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{"user_id": "customer_1_5551234567"}'

# Should return memories for that specific customer's caller
```

## 📊 Current Limitations

1. **No Twilio Number Provisioning** - Phone numbers must be manually assigned in database
2. **No Customer Login** - Dashboard not yet protected by authentication
3. **No Customer Self-Service** - Customers can't update their own settings yet
4. **No Usage Tracking** - Call metrics not yet implemented

## 🎯 Next Steps

### Phase 1: Customer Portal (Required for Production)
- [ ] Build login page (`/login.html`)
- [ ] Add session-based authentication
- [ ] Protect dashboard with auth middleware
- [ ] Load customer-specific data in dashboard

### Phase 2: Self-Service Management
- [ ] Let customers update their greetings
- [ ] Let customers adjust personality sliders
- [ ] Let customers change AI voice
- [ ] Show call history and transcripts

### Phase 3: Automated Provisioning
- [ ] Auto-provision Twilio numbers during onboarding
- [ ] Auto-configure webhooks via Twilio API
- [ ] Email customer with their phone number
- [ ] Handle number porting requests

## 🔐 Security Considerations

**CRITICAL:** Before production launch:
1. Add authentication to `/api/customers/*` endpoints
2. Add authorization checks (customers can only access their own data)
3. Implement rate limiting
4. Add input validation and sanitization
5. Enable HTTPS only
6. Add audit logging

## 💡 Tips

- Use `voice.theinsurancedoctors.com` for AI system (has WebSocket configured)
- Use `neurospherevoice.com` for customer portal
- Both domains point to same server (209.38.143.71)
- Customer settings override admin settings, admin settings are fallback
- Memory is namespaced: `customer_{id}_user_{phone}` prevents cross-contamination
