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

## 🔐 Security Architecture (PRODUCTION-READY)

### ✅ Multi-Layer Security Implemented

The system uses a **defense-in-depth** approach with multiple security layers:

#### 1. **Twilio Signature Validation** (Layer 1)
- **What it protects**: Prevents fake webhook requests
- **How it works**: Validates X-Twilio-Signature header using HMAC-SHA1
- **Location**: `main.py` → `handle_incoming_call_realtime()`
- **Result**: Only authentic Twilio requests can create call sessions

```python
# Rejects requests without valid Twilio signature
validator = RequestValidator(config["twilio_auth_token"])
if not validator.validate(url, request.form, signature):
    return "Unauthorized", 403
```

#### 2. **Server-Side Customer Lookup** (Layer 2)
- **What it protects**: Prevents customer context spoofing
- **How it works**: Customer ID determined server-side by Twilio number (not from client)
- **Location**: `main.py` → webhook queries database by `to_number`
- **Result**: Attackers cannot fake customer identity

```python
# Customer lookup based on authenticated Twilio request
customer = db.session.execute(
    db.select(Customer).filter_by(twilio_phone_number=to_number)
).scalar_one_or_none()
```

#### 3. **Shared Secret Authentication** (Layer 3)
- **What it protects**: Prevents unauthorized access to internal API
- **How it works**: Requires X-Internal-Secret header matching SESSION_SECRET
- **Location**: `main.py` → `/api/internal/customer-context/<call_sid>`
- **Result**: Only orchestrator can retrieve customer context (even with ProxyFix)

```python
# Internal API protected by shared secret
secret_header = request.headers.get('X-Internal-Secret')
if secret_header != SESSION_SECRET:
    return jsonify({"error": "Forbidden"}), 403
```

#### 4. **Session Isolation** (Layer 4)
- **What it protects**: Prevents cross-tenant data leakage
- **How it works**: Call sessions keyed by call_sid with automatic cleanup
- **Location**: `main.py` → `call_sessions` dict + `cleanup_old_sessions()`
- **Result**: Customer data isolated per call, stale sessions auto-removed

```python
# Sessions cleaned up after 1 hour
call_sessions[call_sid] = {
    'customer_id': customer_id,
    'created_at': time.time(),
    # ... customer-specific config
}
```

#### 5. **Memory Namespace Isolation** (Layer 5)
- **What it protects**: Prevents conversation memory cross-contamination
- **How it works**: Thread IDs prefixed with customer_id
- **Location**: `app/main.py` → `thread_id = f"customer_{customer_id}_user_{phone}"`
- **Result**: Conversations stored separately per customer

### 🔒 Security Checklist

**✅ COMPLETED (Production-Ready):**
- [x] Twilio signature validation on webhooks
- [x] Server-side customer lookup (no client trust)
- [x] Shared secret authentication for internal APIs
- [x] Session cleanup to prevent memory leaks
- [x] Memory namespace isolation per customer
- [x] ProxyFix-safe authentication (no IP spoofing)

**⚠️ RECOMMENDED (Before Scale):**
- [ ] Rate limiting on API endpoints
- [ ] Customer authentication for self-service portal
- [ ] Audit logging for security events
- [ ] SESSION_SECRET rotation procedures documented
- [ ] End-to-end security regression tests

### 🛡️ Security Validation

**Test the security chain:**

```bash
# 1. Test Twilio signature rejection
curl https://voice.theinsurancedoctors.com/phone/incoming-realtime \
  -X POST \
  -d "From=%2B15551234567&To=%2B18052654625&CallSid=FAKE123"
# Expected: 403 Forbidden (no valid signature)

# 2. Test internal API protection
curl http://209.38.143.71:5000/api/internal/customer-context/TEST123
# Expected: 403 Forbidden (no X-Internal-Secret header)

# 3. Test with wrong secret
curl http://209.38.143.71:5000/api/internal/customer-context/TEST123 \
  -H "X-Internal-Secret: wrong-secret"
# Expected: 403 Forbidden (invalid secret)
```

### 🔑 Critical Security Notes

1. **SESSION_SECRET**: Must be a strong random value (32+ characters)
   - Used for both Flask sessions AND internal API auth
   - Same value must be set in both containers' `.env` files
   - Rotation requires coordinated restart of both services

2. **Twilio Auth Token**: Keep secure
   - Used for webhook signature validation
   - Exposed token allows webhook spoofing
   - Rotate via Twilio console if compromised

3. **Internal API**: Never expose port 5000 to internet
   - Nginx should proxy only `/phone/*` routes
   - Direct access to port 5000 bypasses shared secret check
   - Verify firewall blocks external access to 5000

## 💡 Tips

- Use `voice.theinsurancedoctors.com` for AI system (has WebSocket configured)
- Use `neurospherevoice.com` for customer portal
- Both domains point to same server (209.38.143.71)
- Customer settings override admin settings, admin settings are fallback
- Memory is namespaced: `customer_{id}_user_{phone}` prevents cross-contamination
