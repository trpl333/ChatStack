# JWT Authentication Setup - Week 1 Coordination

## 🔐 **Shared Secret Key**

**Generated Secret Key:**
```
JWT_SECRET_KEY=-TTihAAqGnhNo2j1SRzYlKVUfQPBllLwrKLtZUpYDUc
```

**IMPORTANT:** This secret must be added to BOTH services:

---

## 📋 **Chad (ChatStack) Setup**

### **1. Add to Environment Variables**

On production server (209.38.143.71):
```bash
cd /opt/ChatStack

# Add to .env file
echo 'JWT_SECRET_KEY=-TTihAAqGnhNo2j1SRzYlKVUfQPBllLwrKLtZUpYDUc' >> .env

# Verify it's there
grep JWT_SECRET_KEY .env
```

On Replit (for development):
```bash
# In Replit Secrets panel:
# Key: JWT_SECRET_KEY
# Value: -TTihAAqGnhNo2j1SRzYlKVUfQPBllLwrKLtZUpYDUc
```

### **2. Chad's Implementation**

✅ **COMPLETE:** Created `app/jwt_utils.py`

**Functions:**
- `generate_memory_token(customer_id)` - Generates JWT for Alice API calls
- `verify_token(token)` - Test token validation

**Usage Example:**
```python
from app.jwt_utils import generate_memory_token

# When calling Alice
customer_id = 1  # Peterson Insurance
token = generate_memory_token(customer_id)

# Add to API request
response = requests.post(
    "http://209.38.143.71:8100/v2/context/enriched",
    headers={"Authorization": f"Bearer {token}"},
    json={"user_id": "+15551234567"}
)
```

---

## 📋 **Alice (AI-Memory) Setup**

### **1. Add to Environment Variables**

On production server (209.38.143.71):
```bash
cd /opt/ai-memory

# Add to .env file
echo 'JWT_SECRET_KEY=-TTihAAqGnhNo2j1SRzYlKVUfQPBllLwrKLtZUpYDUc' >> .env

# Verify it's there
grep JWT_SECRET_KEY .env
```

### **2. Alice's Implementation Needed**

**Create:** `app/jwt_middleware.py`

```python
import jwt
import os
from fastapi import HTTPException, Request

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"

async def get_customer_id_from_token(request: Request) -> int:
    """Extract and validate customer_id from JWT"""
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    token = auth_header.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        customer_id = payload.get("customer_id")
        
        if not customer_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing customer_id")
        
        return customer_id
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

**Update Endpoint Example:**
```python
from app.jwt_middleware import get_customer_id_from_token

@app.post("/v2/context/enriched")
async def get_context(request: Request, user_id: str):
    # Extract customer_id from JWT (validated!)
    customer_id = await get_customer_id_from_token(request)
    
    # Use customer_id in queries
    memories = db.query(Memory).filter(
        Memory.customer_id == customer_id,
        Memory.user_id == user_id
    ).all()
    
    return {"memories": memories}
```

---

## 🧪 **Testing the JWT Flow**

### **Chad Test:**
```python
# Test token generation
from app.jwt_utils import generate_memory_token, verify_token

token = generate_memory_token(customer_id=1)
print(f"Generated token: {token[:50]}...")

# Verify it locally
payload = verify_token(token)
print(f"Verified payload: {payload}")
```

### **Alice Test:**
```bash
# Test endpoint with JWT
curl -X POST http://localhost:8100/v2/context/enriched \
  -H "Authorization: Bearer <TOKEN_HERE>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "+15551234567"}'

# Expected: 200 OK with data
# Without token: 401 Unauthorized
```

---

## ✅ **Week 1 Success Criteria**

- [ ] **Chad:** JWT_SECRET_KEY in environment variables
- [ ] **Alice:** JWT_SECRET_KEY in environment variables (same value)
- [ ] **Chad:** Can generate valid JWT tokens
- [ ] **Alice:** Can validate JWT tokens and extract customer_id
- [ ] **Both:** Test 1 endpoint end-to-end (Chad generates → Alice validates)

---

## 📞 **Coordination Checkpoint**

**End of Week 1:**
- Chad sends test token to Alice
- Alice verifies it works
- Both confirm: JWT authentication is working

**If Issues:**
- Check both services have exact same JWT_SECRET_KEY
- Check token format: `Bearer <token>` in Authorization header
- Check logs for specific error messages

---

**Created by:** Chad (ChatStack)  
**Date:** October 28, 2025  
**Status:** Week 1 - Ready for Alice coordination
