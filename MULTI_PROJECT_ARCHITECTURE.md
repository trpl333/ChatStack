# NeuroSphere Multi-Project Architecture
**Last Updated:** October 23, 2025  
**Version:** 1.2.0 - Complete API specs from all 4 repos

> **⚠️ IMPORTANT**: This file is shared across ChatStack, AI-Memory, LeadFlowTracker, and NeuroSphere Send Text projects.  
> When making changes, update the version number and commit to GitHub so all projects can sync.
> 
> **GitHub Repos:**
> - ChatStack: `trpl333/ChatStack`
> - AI-Memory: `trpl333/ai-memory`
> - LeadFlowTracker: `trpl333/LeadFlowTracker`
> - NeuroSphere Send Text: `trpl333/neurosphere_send_text`

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
**Repository:** `ai-memory` (GitHub: trpl333/ai-memory)  
**Production:** DigitalOcean (209.38.143.71:8100)  
**Port:** 8100

**API Endpoints:**
```
# Core Service
GET  /                              - Service info & status
GET  /admin                         - Admin interface
GET  /health                        - Health check (DB status)

# Memory V1 API (Legacy)
GET  /v1/memories                   - Retrieve memories (params: user_id, limit, memory_type)
POST /v1/memories                   - Store new memory
POST /v1/memories/user              - Store user-specific memory
POST /v1/memories/shared            - Store shared memory
GET  /v1/memories/user/{user_id}    - Get all memories for user
GET  /v1/memories/shared            - Get shared memories
DELETE /v1/memories/{memory_id}     - Delete specific memory

# Chat & LLM
POST /v1/chat                       - Chat completion with memory context
POST /v1/chat/completions           - OpenAI-compatible chat endpoint

# Tools
GET  /v1/tools                      - List available tools
POST /v1/tools/{tool_name}          - Execute specific tool

# Memory V2 (Advanced - if implemented)
# Note: V2 endpoints for caller profiles, personality tracking, 
# and call summaries may be accessed via memory V1 with specific keys
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

### 3. LeadFlowTracker (CRM/Lead Management)
**Repository:** `LeadFlowTracker` (GitHub: trpl333/LeadFlowTracker)  
**Production:** TBD  
**Port:** TBD (likely 3001 or 5001)

**Tech Stack:** Node.js, Express, TypeScript, Drizzle ORM, PostgreSQL

**Key Responsibilities:**
- Lead capture and management
- Lead pipeline tracking with milestone system
- Google Sheets integration for data sync
- Lead status management (active/lost/reactivated)
- Notes and stage tracking

**API Endpoints:**
```
# Lead Management
GET    /api/leads              - Get all leads
GET    /api/leads/:id          - Get lead by ID
POST   /api/leads              - Create new lead
DELETE /api/leads/:id          - Delete lead

# Lead Actions
POST   /api/leads/:id/milestone       - Toggle milestone for lead
POST   /api/leads/:id/mark-lost       - Mark lead as lost
POST   /api/leads/:id/reactivate      - Reactivate lost lead
PATCH  /api/leads/:id/notes           - Update lead notes
PATCH  /api/leads/:id/stage           - Update lead stage
```

**Dependencies:**
- PostgreSQL database (Drizzle ORM)
- Google Sheets API (for data sync)
- AI-Memory (potential - for lead enrichment)

---

### 4. NeuroSphere Send Text (SMS Service)
**Repository:** `neurosphere_send_text` (GitHub: trpl333/neurosphere_send_text)  
**Production:** DigitalOcean (/root/neurosphere_send_text/)  
**Port:** 3000

**Tech Stack:** Python, Flask, Twilio SDK

**Key Responsibilities:**
- Post-call SMS notifications with summaries
- Call transcript and audio file management
- ElevenLabs webhook handler
- Multi-recipient SMS delivery
- Call index maintenance (calls.json)

**API Endpoints:**
```
POST /call-summary    - Receive ElevenLabs webhook, save transcript, send SMS
                       - Extracts: call_sid, caller, transcript summary
                       - Saves: {call_sid}.txt (transcript), {call_sid}.mp3 (audio chunks)
                       - Updates: calls.json index
                       - Sends: SMS to configured recipients with summary + links
```

**Data Flow:**
1. ElevenLabs calls POST /call-summary after call ends
2. Extracts metadata from `data.metadata.phone_call`
3. Saves transcript summary to `/opt/ChatStack/static/calls/{call_sid}.txt`
4. Appends audio chunks (base64) to `/opt/ChatStack/static/calls/{call_sid}.mp3`
5. Updates `/opt/ChatStack/static/calls/calls.json` with call record
6. Sends SMS to recipients: +19493342332, +19495565379

**SMS Recipients:**
- Primary: +19493342332
- Secondary: +19495565379

**Dependencies:**
- Twilio SMS API (from: +18633433339)
- ElevenLabs (webhook trigger)
- ChatStack filesystem (shares /opt/ChatStack/static/calls/)

**Integration:**
- Nginx forwards `/call-summary` → port 3000 (send_text.py)
- Runs in tmux session: `cd /root/neurosphere_send_text && python3 send_text.py`
- Shares call storage directory with ChatStack

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

| Service           | Environment | Location                      | Port | Status  | Notes                    |
|-------------------|-------------|-------------------------------|------|---------|--------------------------|
| ChatStack (Flask) | Production  | DO: 209.38.143.71            | 5000 | Running | Admin UI                 |
| ChatStack (FastAPI)| Production  | DO: 209.38.143.71            | 8001 | Running | Phone orchestrator       |
| AI-Memory         | Production  | DO: 209.38.143.71            | 8100 | Running | Memory service           |
| Send Text         | Production  | DO: /root/neurosphere_send_text | 3000 | Running | SMS service (tmux)      |
| LeadFlowTracker   | Development | Replit/Local                 | TBD  | Dev     | CRM system               |

---

## 📝 Update Protocol

**When you make changes to your service:**

1. **Update this file** with the change (endpoints, ports, data models)
2. **Increment the version number** at the top
3. **Commit and push to GitHub** in your service's repo
4. **Copy updated file to other repos** (or sync via script)

**Example workflow:**
```bash
# In AI-Memory Replit after adding new endpoint:
nano MULTI_PROJECT_ARCHITECTURE.md   # Update endpoint list
# Change version: 1.1.0 → 1.2.0
git add MULTI_PROJECT_ARCHITECTURE.md
git commit -m "AI-Memory: Added /v2/caller/profile endpoint - v1.2.0"
git push origin main

# Then copy to other projects:
# Option A: Manual - download and upload to other Replits
# Option B: Automated - use fetch_repos.js script in ChatStack to pull updates
```

**Auto-sync in ChatStack Replit:**
```bash
# ChatStack has all repos cloned in external/
# Run this to sync the latest architecture docs:
node fetch_repos.js  # Re-downloads all repos with latest changes
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

## 🔗 Cross-Project Code Access (ChatStack Only)

**ChatStack Replit has all 4 repos cloned locally** in the `external/` directory:

```bash
external/
├── ai-memory/           # Full AI-Memory codebase
├── LeadFlowTracker/     # Full CRM codebase  
└── neurosphere-send_text/  # Full SMS service codebase
```

**Benefits:**
- ✅ I can see actual endpoints and code from all services
- ✅ No more endpoint mismatches (like the `/memory/retrieve` vs `/v1/memories` issue)
- ✅ Architecture always stays aligned
- ✅ Easy to search across all projects

**To Update:**
```bash
# Re-download latest code from all repos
node fetch_repos.js
```

This uses the GitHub integration to pull latest code from your private repos.

---

## 🎯 Future Enhancements

- [x] Clone all 4 repos into ChatStack for full visibility
- [x] Document real endpoints from actual code
- [ ] Add Memory V2 endpoint specifications when implemented
- [ ] Add webhook specifications
- [ ] Document error codes and handling
- [ ] Add sequence diagrams for complex flows
- [ ] Create OpenAPI specs for each service
- [x] Find correct neurosphere_send_text repo name and add

---

**Maintained by:** NeuroSphere Development Team  
**Questions?** Check individual project READMEs or update this file with clarifications.
