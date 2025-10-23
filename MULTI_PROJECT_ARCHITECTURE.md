# NeuroSphere Multi-Project Architecture
**Last Updated:** October 23, 2025  
**Version:** 1.0.0

> **⚠️ IMPORTANT**: This file is shared across ChatStack, AI-Memory, LeadLow, and SentText projects.  
> When making changes, update the version number and commit to GitHub so all projects can sync.

---

## 🏗️ System Overview

NeuroSphere is a multi-service AI phone system platform with 4 interconnected services:

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌─────────────┐
│  ChatStack  │─────▶│  AI-Memory   │      │   LeadLow   │      │  SentText   │
│  (Phone AI) │      │  (Storage)   │      │  (CRM/Leads)│      │    (SMS)    │
└─────────────┘      └──────────────┘      └─────────────┘      └─────────────┘
     │                      ▲                      │                    │
     │                      │                      │                    │
     └──────────────────────┴──────────────────────┴────────────────────┘
                      All services share AI-Memory
```

---

## 📡 Service Details

### 1. ChatStack (AI Phone System)
**Repository:** `chatstack`  
**Production:** DigitalOcean (209.38.143.71)  
**Ports:**
- 5000: Flask Admin Panel (Web UI)
- 8001: FastAPI Orchestrator (Phone WebSocket handler)

**Key Responsibilities:**
- Twilio voice call handling
- OpenAI Realtime API integration
- Call recording & transcription
- Admin configuration interface
- Real-time conversation management

**Dependencies:**
- AI-Memory (port 8100) - Memory storage & retrieval
- OpenAI API - LLM responses
- Twilio - Voice calls
- ElevenLabs - Text-to-Speech

---

### 2. AI-Memory (Memory Service)
**Repository:** `ai-memory`  
**Production:** DigitalOcean (209.38.143.71:8100)  
**Port:** 8100

**API Endpoints:**
```
GET  /                      - Service info
GET  /health                - Health check
GET  /v1/memories           - Retrieve memories (user_id, limit, memory_type params)
POST /v1/memories           - Store new memory
POST /v1/memories/user      - Store user-specific memory
DELETE /v1/memories/{id}    - Delete memory by ID
GET  /caller/profile/{phone}        - [V2] Get enriched caller profile
GET  /personality/averages/{phone}  - [V2] Get personality metrics
POST /call/summary                  - [V2] Save call summary
```

**Data Models:**
- Memories (key-value with semantic search)
- Caller Profiles (V2 enriched data)
- Call Summaries (structured summaries)
- Personality Metrics (Big 5 + communication style)

**Database:** PostgreSQL with pgvector for semantic search

**Used By:**
- ChatStack (primary consumer)
- LeadLow (lead enrichment)
- SentText (personalization data)

---

### 3. LeadLow (CRM/Lead Management)
**Repository:** `leadlow`  
**Production:** TBD  
**Port:** TBD

**Key Responsibilities:**
- Lead capture and management
- CRM integration (Notion, HubSpot, etc.)
- Lead scoring and qualification
- Pipeline tracking

**Dependencies:**
- AI-Memory - Lead enrichment and history
- TBD

**API Endpoints:**
```
# TODO: Add LeadLow endpoints
```

---

### 4. SentText (SMS Service)
**Repository:** `senttext`  
**Production:** TBD  
**Port:** TBD

**Key Responsibilities:**
- SMS campaign management
- Automated text messaging
- SMS template management
- Delivery tracking

**Dependencies:**
- Twilio - SMS delivery
- AI-Memory - Personalization data
- TBD

**API Endpoints:**
```
# TODO: Add SentText endpoints
```

---

## 🔄 Integration Patterns

### ChatStack ↔ AI-Memory
**Connection:** HTTP REST API  
**Endpoint:** `http://209.38.143.71:8100`

**Usage:**
```python
# ChatStack retrieves memories
GET http://209.38.143.71:8100/v1/memories?user_id={phone}&limit=500

# ChatStack stores memories
POST http://209.38.143.71:8100/v1/memories
{
  "user_id": "{phone}",
  "type": "fact",
  "key": "caller_name",
  "value": {"name": "John Smith"},
  "scope": "user"
}
```

**Memory V2 API:**
```python
# Get enriched caller profile (fast, pre-processed)
GET http://209.38.143.71:8100/caller/profile/{phone}

# Returns: caller_name, total_calls, enriched_context
```

### LeadLow ↔ AI-Memory
**Connection:** TBD  
**Usage:** TBD

### SentText ↔ AI-Memory
**Connection:** TBD  
**Usage:** TBD

---

## 🚀 Deployment Locations

| Service    | Environment | Location              | Port | Status  |
|------------|-------------|-----------------------|------|---------|
| ChatStack  | Production  | DO: 209.38.143.71    | 5000 | Running |
| ChatStack  | Production  | DO: 209.38.143.71    | 8001 | Running |
| AI-Memory  | Production  | DO: 209.38.143.71    | 8100 | Running |
| LeadLow    | Production  | TBD                  | TBD  | TBD     |
| SentText   | Production  | TBD                  | TBD  | TBD     |

---

## 📝 Update Protocol

**When you make changes to your service:**

1. **Update this file** with the change (endpoints, ports, data models)
2. **Increment the version number** at the top
3. **Commit and push to GitHub**
4. **Notify other projects** (or they pull periodically)

**Example commit message:**
```bash
git commit -m "AI-Memory: Added /v2/caller/profile endpoint - v1.1.0"
```

---

## 🔧 Environment Variables

### ChatStack
```bash
DATABASE_URL=postgresql://...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
SESSION_SECRET=...
LLM_BASE_URL=https://api.openai.com/v1
```

### AI-Memory
```bash
DATABASE_URL=postgresql://...
# Add AI-Memory specific vars
```

### LeadLow
```bash
# TODO: Add LeadLow environment variables
```

### SentText
```bash
# TODO: Add SentText environment variables
```

---

## 📚 Key Learnings

### API Endpoint Mismatches (Oct 23, 2025)
**Issue:** ChatStack was calling wrong AI-Memory endpoints:
- ❌ `POST /memory/retrieve` (404)
- ❌ `POST /memory/store` (404)

**Fix:** Updated to correct endpoints:
- ✅ `GET /v1/memories`
- ✅ `POST /v1/memories`

**Lesson:** Always check this file before integrating. Keep endpoint specs up-to-date!

---

## 🎯 Future Enhancements

- [ ] Complete LeadLow and SentText sections
- [ ] Add webhook specifications
- [ ] Document error codes and handling
- [ ] Add sequence diagrams for complex flows
- [ ] Create OpenAPI specs for each service

---

**Maintained by:** NeuroSphere Development Team  
**Questions?** Check individual project READMEs or update this file with clarifications.
