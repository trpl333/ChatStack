# NeuroSphere AI - Phase 1 Implementation Plan
**Approach:** Compromise (MVP in 4 weeks, Security hardening before external sales)  
**Based on:** ChatGPT-5 Review + Chad & Alice Alignment  
**Date:** October 28, 2025  
**Status:** APPROVED - Ready to Execute

---

## 🎯 Phase 1: MVP (4 Weeks) - Sellable to Peterson Insurance

**Goal:** Multi-tenant foundation with basic security, sellable to internal test customers

**Included (ChatGPT-5 Critical):**
- ✅ `customer_id` in all Alice tables
- ✅ JWT authentication (Chad ↔ Alice)
- ✅ Multi-tenant isolation tests
- ✅ Remove hardcoded references

**Deferred to Phase 2 (Before External Sales):**
- ⏭️ PostgreSQL Row-Level Security (RLS)
- ⏭️ Prometheus/Grafana monitoring
- ⏭️ Rate limiting middleware
- ⏭️ GDPR export/delete endpoints

---

## 👥 Service Coordination

**Chad (ChatStack):**
- GitHub: https://github.com/trpl333/ChatStack
- Server: 209.38.143.71:/opt/ChatStack/
- Owner: Chad implementation team

**Alice (AI-Memory):**
- GitHub: https://github.com/trpl333/ai-memory
- Server: 209.38.143.71:/opt/ai-memory/
- Owner: Alice implementation team

---

## 🔐 JWT Authentication Specification

### **Shared Configuration**

Both Chad and Alice must have this environment variable:

```bash
# /opt/ChatStack/.env (Chad)
JWT_SECRET_KEY=<generate-secure-random-key>

# /opt/ai-memory/.env (Alice)
JWT_SECRET_KEY=<same-secure-random-key>
```

**Generate Secret Key:**
```python
import secrets
secret = secrets.token_urlsafe(32)
print(secret)  # Use this value for JWT_SECRET_KEY
```

### **JWT Token Structure**

```python
{
  "customer_id": 1,                    # Tenant identifier (INTEGER)
  "scope": "memory:read:write",        # Permissions
  "iat": 1698765432,                   # Issued at (Unix timestamp)
  "exp": 1698769032                    # Expires (1 hour from iat)
}
```

### **Chad Implementation (Token Generation)**

```python
import jwt
import os
from datetime import datetime, timedelta

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

def generate_memory_token(customer_id: int) -> str:
    """Generate JWT token for Alice API calls"""
    payload = {
        "customer_id": customer_id,
        "scope": "memory:read:write",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token

# Usage in Chad's code
customer_id = 1  # Looked up from customers table
token = generate_memory_token(customer_id)

# Call Alice with JWT
response = requests.post(
    "http://209.38.143.71:8100/v2/context/enriched",
    headers={"Authorization": f"Bearer {token}"},
    json={"user_id": "+15551234567"}
)
```

### **Alice Implementation (Token Validation)**

```python
import jwt
import os
from fastapi import HTTPException, Request

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

async def get_customer_id_from_token(request: Request) -> int:
    """Extract and validate customer_id from JWT"""
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    token = auth_header.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        customer_id = payload.get("customer_id")
        
        if not customer_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing customer_id")
        
        return customer_id
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Usage in Alice's endpoints
@app.post("/v2/context/enriched")
async def get_context(request: Request, user_id: str):
    customer_id = await get_customer_id_from_token(request)  # ✅ Verified!
    
    # Now use customer_id in queries
    memories = db.query(Memory).filter(
        Memory.customer_id == customer_id,
        Memory.user_id == user_id
    ).all()
    
    return {"memories": memories}
```

---

## 📅 Week-by-Week Breakdown

### **Week 1: Alice Database + JWT Foundation**

**Alice's Tasks:**
- [ ] Add `customer_id INTEGER NOT NULL` to all 5 tables
- [ ] Create migration SQL scripts
- [ ] Migrate existing data to `customer_id = 1` (Peterson)
- [ ] Add composite indexes: `(customer_id, user_id)`
- [ ] Add foreign key constraints
- [ ] Install PyJWT: `pip install pyjwt`
- [ ] Implement `get_customer_id_from_token()` middleware
- [ ] Update 1 endpoint as proof-of-concept: `/v2/context/enriched`
- [ ] Test JWT validation works

**Chad's Tasks:**
- [ ] Install PyJWT: `pip install pyjwt`
- [ ] Generate shared `JWT_SECRET_KEY`
- [ ] Implement `generate_memory_token()` function
- [ ] Update 1 API call as proof-of-concept: `/v2/context/enriched`
- [ ] Test end-to-end: Chad generates token → Alice validates

**Coordination:**
- [ ] Both teams sync on JWT_SECRET_KEY value
- [ ] Test proof-of-concept endpoint together

---

### **Week 2: Full API Migration + Hardcoded References**

**Alice's Tasks:**
- [ ] Update ALL endpoints to require JWT authentication
- [ ] Update ALL queries to filter by `customer_id`
- [ ] Update backward compatibility endpoints (`/memory/store`, `/memory/retrieve`)
- [ ] Add validation: reject requests without valid JWT
- [ ] Remove any hardcoded customer references

**Chad's Tasks:**
- [ ] Update ALL API calls to Alice to include JWT token
- [ ] Remove hardcoded "Peterson Family Insurance" from `app/prompts/system_sam.txt`
- [ ] Make system prompts load from `customers.greeting_template`
- [ ] Remove hardcoded phone numbers from code
- [ ] Create Customer #2 in database: "Smith Insurance Agency"

**Coordination:**
- [ ] Deploy Alice changes to production first
- [ ] Then deploy Chad changes
- [ ] Verify all API calls still work

---

### **Week 3: Multi-Tenant Testing**

**Alice's Tasks:**
- [ ] Write automated tenant isolation tests
  ```python
  def test_peterson_cannot_see_smith_data()
  def test_smith_cannot_see_peterson_data()
  def test_invalid_jwt_rejected()
  def test_expired_jwt_rejected()
  ```
- [ ] Create test data for customer_id=2 (Smith)
- [ ] Run isolation tests
- [ ] Fix any data leakage bugs found

**Chad's Tasks:**
- [ ] Write end-to-end integration tests
  ```python
  def test_peterson_call_flow()
  def test_smith_call_flow()
  def test_parallel_calls_isolated()
  ```
- [ ] Make test calls as Peterson Insurance
- [ ] Make test calls as Smith Insurance Agency
- [ ] Verify call logs separated correctly

**Coordination:**
- [ ] Run tests together
- [ ] Document any issues found
- [ ] Fix critical bugs before Week 4

---

### **Week 4: Documentation + Production Readiness**

**Alice's Tasks:**
- [ ] Update API documentation with JWT requirements
- [ ] Document migration procedures
- [ ] Add logging with `customer_id` in every log message
- [ ] Performance testing (simulate 10 concurrent tenants)

**Chad's Tasks:**
- [ ] Update MULTI_PROJECT_ARCHITECTURE.md v2.0
- [ ] Create CUSTOMER_ONBOARDING_GUIDE.md
- [ ] Build tenant admin UI (basic version)
- [ ] Test onboarding flow with "Smith Agency"

**Both Teams:**
- [ ] Final security review
- [ ] Load testing
- [ ] Deploy to production
- [ ] Mark Phase 1 COMPLETE

---

## 🧪 Testing Specifications

### **Test Tenant Setup**

```sql
-- Chad's database: Create test tenant #2
INSERT INTO customers (id, business_name, agent_name, greeting_template, twilio_phone_number)
VALUES (
  2,
  'Smith Insurance Agency',
  'Sarah',
  'Hey, you''ve reached Smith Insurance...',
  '+18005551234'
);
```

### **Isolation Test Cases**

**Test 1: Data Isolation**
```python
# Store memory for Peterson (customer_id=1)
store_memory(customer_id=1, user_id="+15551111111", content="Peterson client John")

# Store memory for Smith (customer_id=2)
store_memory(customer_id=2, user_id="+15551111111", content="Smith client Jane")

# Verify Peterson sees only their data
peterson_memories = get_memories(customer_id=1, user_id="+15551111111")
assert "John" in peterson_memories
assert "Jane" not in peterson_memories  # ✅ Must pass

# Verify Smith sees only their data
smith_memories = get_memories(customer_id=2, user_id="+15551111111")
assert "Jane" in smith_memories
assert "John" not in smith_memories  # ✅ Must pass
```

**Test 2: JWT Validation**
```python
# Test invalid JWT rejected
response = call_alice(token="invalid-token")
assert response.status_code == 401

# Test expired JWT rejected
expired_token = generate_token(exp=datetime.utcnow() - timedelta(hours=2))
response = call_alice(token=expired_token)
assert response.status_code == 401

# Test missing JWT rejected
response = call_alice(headers={})  # No Authorization header
assert response.status_code == 401
```

**Test 3: Cross-Tenant Spoofing Attempt**
```python
# Try to spoof customer_id in request body (should be ignored)
token = generate_token(customer_id=1)  # Peterson's token
response = requests.post(
    "/v2/context/enriched",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "customer_id": 2,  # ← Try to access Smith's data
        "user_id": "+15552222222"
    }
)

# Should return Peterson's data (from JWT), NOT Smith's data
# JWT customer_id (1) overrides body customer_id (2)
assert response.json()["customer_id"] == 1
```

---

## 📊 Success Criteria for Phase 1

**Must Pass Before Declaring Phase 1 Complete:**

- [ ] All 5 Alice tables have `customer_id` column
- [ ] All Alice API endpoints require JWT authentication
- [ ] All Chad → Alice calls use JWT tokens
- [ ] Zero hardcoded company names in code
- [ ] Test Tenant #2 (Smith) created successfully
- [ ] Automated tests pass: Peterson ≠ Smith data isolation
- [ ] Load test: 10 concurrent tenants without errors
- [ ] Documentation updated (MPA v2.0, Onboarding Guide)

**Performance Targets:**
- Call latency: <3 seconds (same as current)
- Database queries: <100ms per query
- JWT validation overhead: <10ms

---

## ⏭️ Phase 2: Security Hardening (2 Weeks - Before External Sales)

**Deferred from ChatGPT-5 Recommendations:**

### **Week 5: PostgreSQL RLS**
- [ ] Alice: Enable Row-Level Security on all tables
- [ ] Alice: Create RLS policies for tenant isolation
- [ ] Alice: Add RLS middleware to set session variable
- [ ] Test: Verify RLS blocks cross-tenant queries even without `WHERE customer_id`

### **Week 6: Monitoring & Compliance**
- [ ] Both: Set up Prometheus + Grafana
- [ ] Alice: Add per-tenant rate limiting
- [ ] Alice: Implement GDPR export endpoint
- [ ] Alice: Implement GDPR delete endpoint
- [ ] Chad: Build Platform Admin panel
- [ ] Both: Automated backup per tenant

**Phase 2 Success Criteria:**
- [ ] RLS policies prevent data leakage even if developer forgets `customer_id`
- [ ] Monitoring dashboards show per-tenant metrics
- [ ] Can export/delete all data for a single tenant
- [ ] Ready to onboard first external customer

---

## 🚀 Deployment Process

### **Week 1-3 (Development):**
```bash
# Alice deploys first (database changes)
cd /opt/ai-memory
git pull origin main
# Run migration SQL
docker-compose restart

# Then Chad deploys (API changes)
cd /opt/ChatStack
./update.sh
```

### **Week 4 (Production Release):**
```bash
# Final production deployment
cd /opt/ai-memory
git pull origin main
docker-compose restart

cd /opt/ChatStack
./update.sh

# Verify both services healthy
curl http://localhost:8100/health
curl http://localhost:5000/health
```

---

## 📞 Communication Protocol

**Daily Standups (Async via Replit Chat):**
- What did you complete yesterday?
- What are you working on today?
- Any blockers?

**Weekly Sync (End of each week):**
- Review progress against plan
- Test integration points
- Adjust timeline if needed

**Critical Issues:**
- Immediately notify other team if blocking issue found
- Document in `ISSUES.md` file in both repos

---

## ✅ Approval Checkpoint

**This plan is APPROVED by:**
- [x] User (John)
- [x] Chad (ChatStack team)
- [x] Alice (AI-Memory team)
- [x] ChatGPT-5 (Architecture review)

**Ready to execute:** YES - No code will be written until this plan is finalized.

---

**End of Implementation Plan - Phase 1**
