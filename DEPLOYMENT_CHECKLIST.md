# Multi-Tenant AI Phone System - Deployment Checklist

## 🚀 Production Deployment Guide

This checklist walks through deploying the security-hardened multi-tenant AI phone system to DigitalOcean.

---

## ✅ Pre-Deployment Security Verification

### 1. Verify SESSION_SECRET is Strong

**Critical**: SESSION_SECRET is used for both Flask sessions AND internal API authentication.

```bash
# On DigitalOcean server (209.38.143.71)
ssh root@209.38.143.71
cd /opt/ChatStack

# Check SESSION_SECRET exists and is strong (32+ chars)
grep SESSION_SECRET .env

# If not set or weak, generate a strong one:
openssl rand -hex 32

# Update .env file with the new secret
nano .env
# Set: SESSION_SECRET=<generated-value>
```

**Important**: Both Flask and FastAPI containers must use the **same** SESSION_SECRET.

### 2. Verify Twilio Credentials

```bash
# Check Twilio credentials are set
grep TWILIO .env
# Should see:
# TWILIO_ACCOUNT_SID=ACxxxxxxx
# TWILIO_AUTH_TOKEN=xxxxxxx
```

### 3. Check config.json

```bash
# Verify Twilio credentials in config.json
cat config.json | grep -A2 twilio
```

---

## 🏗️ Deployment Steps

### Step 1: Deploy Code to Server

```bash
# Option A: Use deployment script (from local machine)
./deploy_to_digitalocean.sh

# Option B: Manual deployment
ssh root@209.38.143.71
cd /opt/ChatStack
git pull origin main

# Rebuild containers with no cache (ensures latest code)
docker-compose down
docker-compose build --no-cache web orchestrator-worker
docker-compose up -d

# Verify containers are running
docker ps
```

### Step 2: Verify Security Layers

**Test 1: Twilio Signature Validation**
```bash
# Attempt to spoof webhook (should be rejected)
curl https://voice.theinsurancedoctors.com/phone/incoming-realtime \
  -X POST \
  -d "From=%2B15551234567&To=%2B18052654625&CallSid=FAKE123"

# Expected: 403 Forbidden
# Log should show: "❌ SECURITY: Invalid Twilio signature"
```

**Test 2: Internal API Protection**
```bash
# Attempt to access internal API without secret
curl http://209.38.143.71:5000/api/internal/customer-context/TEST123

# Expected: 403 Forbidden
# Log should show: "❌ SECURITY: Unauthorized access attempt"
```

**Test 3: Shared Secret Validation**
```bash
# Access internal API with wrong secret
curl http://209.38.143.71:5000/api/internal/customer-context/TEST123 \
  -H "X-Internal-Secret: wrong-secret"

# Expected: 403 Forbidden
```

### Step 3: Database Setup

**Create test customer:**
```bash
# SSH to server
ssh root@209.38.143.71

# Connect to database
docker exec -it chatstack-web-1 psql $DATABASE_URL

# Create customer (or update existing)
INSERT INTO customers (
    email, 
    business_name, 
    contact_name, 
    phone, 
    package_tier, 
    agent_name, 
    openai_voice, 
    greeting_template, 
    twilio_phone_number
) VALUES (
    'test@example.com',
    'Test Business',
    'John Doe',
    '555-0001',
    'professional',
    'Samantha',
    'nova',
    'Hi! This is Samantha from Test Business. How can I help you today?',
    '+18052654625'
);

# Verify customer created
SELECT id, business_name, agent_name, twilio_phone_number FROM customers;

# Exit
\q
```

### Step 4: Configure Twilio Webhook

1. **Go to Twilio Console**: https://console.twilio.com/
2. **Navigate to**: Phone Numbers → Active Numbers → (805) 265-4625
3. **Configure Voice Webhook**:
   - **A CALL COMES IN**: `https://voice.theinsurancedoctors.com/phone/incoming-realtime`
   - **HTTP Method**: `POST`
4. **Save Configuration**

---

## 🧪 End-to-End Testing

### Test 1: Basic Call Flow

```bash
# 1. Call the number: (805) 265-4625
# 2. Expected flow:
#    - Twilio validates and sends webhook
#    - Flask validates Twilio signature ✓
#    - Flask looks up customer by phone number ✓
#    - Flask stores session with call_sid ✓
#    - WebSocket connects to orchestrator ✓
#    - Orchestrator requests customer context ✓
#    - Flask validates shared secret ✓
#    - Customer-specific greeting plays ✓
```

### Test 2: Customer-Specific Settings

```bash
# Update customer voice
docker exec -it chatstack-web-1 psql $DATABASE_URL
UPDATE customers SET openai_voice = 'shimmer' WHERE id = 1;
\q

# Call again - should hear new voice
```

### Test 3: Memory Isolation

```bash
# After making calls, verify namespaced memory
curl http://209.38.143.71:8100/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{"user_id": "customer_1_user_18052654625"}'

# Should return conversation for customer 1 only
```

### Test 4: Multi-Tenant Isolation

```bash
# Create second customer with different number
docker exec -it chatstack-web-1 psql $DATABASE_URL

INSERT INTO customers (
    email, business_name, agent_name, 
    openai_voice, greeting_template, twilio_phone_number
) VALUES (
    'customer2@test.com', 'Business 2', 'Alex',
    'alloy', 'Hello! This is Alex from Business 2.',
    '+15551234567'
);

# Configure second Twilio number to same webhook
# Each should get their own agent name, voice, and memory
```

---

## 📊 Monitoring

### Check Logs

```bash
# Flask webhook logs
docker logs chatstack-web-1 --tail 100 -f

# Look for:
# ✅ SECURITY: Twilio signature validated
# ✅ Found customer X: Business Name
# 🔐 Stored customer session for call_sid=...

# Orchestrator logs
docker logs chatstack-orchestrator-worker-1 --tail 100 -f

# Look for:
# 🔐 Retrieved customer session for call_sid=...
# 🏢 Multi-tenant mode: Customer X
# 👤 Customer Context: ID=X, Agent=Name
```

### Monitor Session Cleanup

```bash
# Session cleanup happens when call_sessions > 100
# Look for log: "🧹 Cleaned up expired session: CAXXXXXX"

# Manual trigger (via Python in container):
docker exec -it chatstack-web-1 python3 -c "
from main import cleanup_old_sessions
print(f'Cleaned up {cleanup_old_sessions()} sessions')
"
```

---

## 🔒 Security Validation

### Verify All Security Layers

**✅ Layer 1: Twilio Signature Validation**
- [x] Invalid signatures rejected with 403
- [x] Only authentic Twilio requests accepted
- [x] Logs show signature validation

**✅ Layer 2: Server-Side Customer Lookup**
- [x] Customer determined by `to_number` (Twilio field)
- [x] No client-supplied customer_id trusted
- [x] Database lookup succeeds

**✅ Layer 3: Shared Secret Authentication**
- [x] Internal API requires X-Internal-Secret header
- [x] Wrong/missing secrets rejected with 403
- [x] Orchestrator sends correct secret

**✅ Layer 4: Session Isolation**
- [x] Sessions keyed by call_sid
- [x] Timestamps added to sessions
- [x] Cleanup runs periodically

**✅ Layer 5: Memory Namespace Isolation**
- [x] Thread IDs prefixed with customer_id
- [x] Conversations stored separately
- [x] No cross-tenant data leakage

---

## 🚨 Troubleshooting

### Issue: Calls fail immediately
```bash
# Check Twilio webhook logs
docker logs chatstack-web-1 --tail 50

# Look for:
# - ❌ SECURITY: Invalid Twilio signature
# - Check config.json has correct twilio_auth_token
```

### Issue: "Session not found" in orchestrator
```bash
# Verify shared secret matches in both containers
docker exec chatstack-web-1 env | grep SESSION_SECRET
docker exec chatstack-orchestrator-worker-1 env | grep SESSION_SECRET

# Should be identical
```

### Issue: Wrong customer settings used
```bash
# Check customer has twilio_phone_number set
docker exec -it chatstack-web-1 psql $DATABASE_URL
SELECT id, business_name, twilio_phone_number FROM customers;

# Verify phone number matches Twilio's "To" field format (+1XXXXXXXXXX)
```

### Issue: Memory leak / high memory usage
```bash
# Check session count
docker exec -it chatstack-web-1 python3 -c "
from main import call_sessions
print(f'Active sessions: {len(call_sessions)}')
"

# Force cleanup
docker exec -it chatstack-web-1 python3 -c "
from main import cleanup_old_sessions
print(f'Cleaned: {cleanup_old_sessions()}')
"
```

---

## ✅ Post-Deployment Checklist

- [ ] All containers running (`docker ps`)
- [ ] Twilio webhook configured
- [ ] Test customer created in database
- [ ] Twilio signature validation working
- [ ] Internal API protected by shared secret
- [ ] Customer-specific greeting plays on call
- [ ] Customer-specific voice used
- [ ] Memory namespacing confirmed
- [ ] Session cleanup verified
- [ ] No security errors in logs

---

## 🎯 Next Steps

### Immediate (Production Readiness):
1. Set up automated session cleanup (cron job or background task)
2. Add monitoring/alerting for security events
3. Document SESSION_SECRET rotation procedure
4. Set up database backups

### Short-Term (Customer Experience):
1. Build customer login portal
2. Add self-service configuration UI
3. Show call history and transcripts
4. Add usage analytics

### Long-Term (Scale):
1. Auto-provision Twilio numbers via API
2. Implement rate limiting
3. Add multi-region support
4. Build customer billing integration

---

## 📝 Important Notes

1. **SESSION_SECRET Rotation**:
   - Generate new secret: `openssl rand -hex 32`
   - Update `.env` in /opt/ChatStack/
   - Restart both containers: `docker-compose restart`

2. **Twilio Auth Token Rotation**:
   - Rotate in Twilio console
   - Update `config.json` on server
   - Restart Flask: `docker-compose restart web`

3. **Database Backups**:
   - Customer data stored in PostgreSQL
   - Set up automated backups via DigitalOcean
   - Test restore procedure

4. **Firewall Rules**:
   - Port 5000 should NOT be accessible externally
   - Only Nginx (port 443/80) should be public
   - Verify: `sudo ufw status`
