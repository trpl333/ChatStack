# NeuroSphere Voice - Multi-Tenant AI Phone System Platform

### Overview
**NeuroSphere Voice** is a **multi-tenant** AI-powered phone system platform built by The Insurance Doctors / Peterson Family Insurance (DBAs of the same company). The platform serves multiple insurance agency customers, with each customer getting their own AI agent with custom personality, voice, and dedicated phone number. Built on NeuroSphere Orchestrator (FastAPI), it's designed for intelligent call handling with persistent memory and rapid 2-2.5 second response times. The system features secure customer authentication, isolated conversation memory per tenant, and comprehensive multi-layer security. The orchestrator acts as middleware between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations through memory retrieval, prompt engineering, and extensible tool functionality. The system uses OpenAI's Realtime API and is fully deployed on DigitalOcean.

---

## 🚨 CRITICAL DEPLOYMENT RULE - READ THIS FIRST 🚨

**PERMANENT DEPLOYMENT WORKFLOW - NO EXCEPTIONS:**

All code changes MUST follow this exact sequence to keep Replit, GitHub, and DigitalOcean in perfect sync:

### ✅ REQUIRED WORKFLOW:
1. **Fix code in Replit** (development environment)
2. **Push to GitHub** (version control):
   ```bash
   git add [files]
   git commit -m "[description]"
   git push origin main
   ```
3. **Deploy to DigitalOcean** (production):
   ```bash
   cd /opt/ChatStack
   git fetch origin
   git reset --hard origin/main
   docker-compose down
   docker-compose up -d --build
   docker logs chatstack-orchestrator-worker-1 --tail 20  # verify
   ```

### ❌ NEVER ALLOWED:
- **NO manual edits** on DigitalOcean server (sed, vim, nano, etc.)
- **NO direct file modifications** in `/opt/ChatStack/` on production
- **NO "quick fixes"** that bypass git workflow
- **NO deployment without GitHub** as the source of truth

### 🔒 WHY THIS RULE EXISTS:
Manual production edits create:
- Syntax errors from incomplete changes
- Drift between environments (Replit ≠ GitHub ≠ DigitalOcean)
- Deployment failures and phone system crashes
- Lost changes when pulling from git

**This rule was established after manual sed commands created catastrophic syntax errors that crashed the production phone system. Always use git workflow.**

---

## 📍 SERVICE LOCATIONS ON DIGITALOCEAN

**CRITICAL: The system consists of SEPARATE repositories and deployment locations:**

### ChatStack (Main Phone System)
- **GitHub Repo**: `https://github.com/trpl333/ChatStack.git`
- **DigitalOcean Path**: `/opt/ChatStack/`
- **Services**: Flask web (port 5000), FastAPI orchestrator (port 8001)
- **Deployment**:
  ```bash
  cd /opt/ChatStack
  git fetch origin
  git reset --hard origin/main
  docker-compose down
  docker-compose up -d --build
  docker logs chatstack-web-1 --tail 20
  docker logs chatstack-orchestrator-worker-1 --tail 20
  ```

### AI-Memory Service (Persistent Memory & Admin Settings)
**📅 Last Updated: Oct 17, 2025 - CRITICAL LOCATION CLARIFICATION**

- **GitHub Repo**: `https://github.com/trpl333/ai-memory.git` *(needs verification)*
- **ACTUAL DigitalOcean Path**: `/opt/neurosphere-memory-bridge/` ⚠️
- **Service Type**: Systemd service (NOT Docker)
- **Service Name**: `ai-memory.service`
- **Port**: 8100
- **Connection URL**: `http://209.38.143.71:8100` (external DigitalOcean service)
- **Purpose**: Stores conversation memory, admin settings, user data

**🗂️ Directory Confusion - READ THIS:**
There are **3 different AI-Memory directories** on the server - DO NOT confuse them:

1. **`/opt/neurosphere-memory-bridge/`** ✅ ACTIVE AI-Memory service
   - This is the REAL AI-Memory service running on port 8100
   - Contains: `main.py`, `.venv/`, `.env`
   - Started via systemd: `systemctl start ai-memory`
   
2. **`/opt/ai-memory/`** ❌ This is actually ChatStack repo clone (NOT AI-Memory!)
   - Contains ChatStack code, NOT AI-Memory service
   - Has `ai-memory-main.py` which is just a reference copy
   
3. **`/root/ai-memory/`** ⚠️ Old/stale copy from Oct 6-9, 2025
   - Legacy directory, may be outdated
   - DO NOT use for production

**Service Management (Systemd - NOT Docker):**
```bash
# Check status
systemctl status ai-memory

# Start/Stop/Restart
systemctl start ai-memory
systemctl stop ai-memory
systemctl restart ai-memory

# View logs
journalctl -u ai-memory -f

# Health check
curl http://127.0.0.1:8100/health
curl http://209.38.143.71:8100/health
```

**Service File Location:**
- `/etc/systemd/system/ai-memory.service`
- Created: Oct 17, 2025 at 18:19 UTC
- WorkingDirectory: `/opt/neurosphere-memory-bridge`
- ExecStart: `.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8100`

**⚠️ KNOWN ISSUES (as of Oct 17, 2025):**
1. **Endpoint Mismatch**: Service returns 404 for `/memory/retrieve` 
   - ChatStack expects: `/memory/retrieve`, `/memory/store`
   - Current service may have different endpoint names
   - **Action needed**: Verify endpoint compatibility between ChatStack and AI-Memory

2. **Historical Notes:**
   - Service was managed by cron job until Oct 7, 2025 (restarted every 5 mins)
   - Manually stopped Oct 7 at 17:35 UTC
   - Recreated Oct 17 at 18:19 UTC

**⚠️ CRITICAL DEPENDENCY:**
- The `ai-memory-main.py` file in ChatStack repo is just a REFERENCE COPY
- To modify AI-Memory, work in `/opt/neurosphere-memory-bridge/` on the server
- ChatStack depends entirely on this service - if it's down, phone system fails

### All Active Services on DigitalOcean
**📅 Last Verified: Oct 17, 2025**

**Critical Services (must be running):**

1. **orchestrator.service** - ChatStack Orchestrator
   - Path: `/opt/ChatStack/`
   - Port: 5000 (Flask) + 8001 (FastAPI)
   - Control: `systemctl start/stop/restart orchestrator`
   - Logs: `journalctl -u orchestrator -f`

2. **ai-memory.service** - Memory Service
   - Path: `/opt/neurosphere-memory-bridge/`
   - Port: 8100
   - Control: `systemctl start/stop/restart ai-memory`
   - Logs: `journalctl -u ai-memory -f`

3. **voice-bridge.service** - Twilio Voice Bridge
   - Path: `/opt/voice-bridge/`
   - Port: 9100
   - Control: `systemctl start/stop/restart voice-bridge`
   - Logs: `journalctl -u voice-bridge -f`

**Other Services:**
- `/opt/neurosphere-sync/` - Notion sync service
- `/opt/orchestrator/` - Legacy orchestrator (if still active)

**When making changes:**
1. ✅ Identify which repo/service needs the change
2. ✅ Make changes in the correct GitHub repository
3. ✅ Deploy to the correct `/opt/` directory
4. ❌ NEVER edit files directly on the server

---

## 🔧 CRITICAL: AI-Memory Service Dependency

### Why AI-Memory Was Separated

**Historical Context:**
- AI-Memory was originally part of ChatStack's docker-compose.yml
- It was separated into its own service at `/opt/ai-memory/` for independent scaling and management
- Each service now has its own GitHub repo, Docker containers, and deployment cycle

### Critical Dependency Chain

```
Phone Call → ChatStack (Flask/FastAPI) → AI-Memory Service → PostgreSQL
```

**⚠️ IF AI-MEMORY IS DOWN, THE ENTIRE PHONE SYSTEM STOPS WORKING**

ChatStack cannot function without AI-Memory because it stores:
- All conversation history and context
- Admin panel settings (personality sliders, greetings, voice)
- User authentication and registration data
- Transfer rules and routing configuration

### Troubleshooting: "Phone System Stopped Working"
**📅 Updated: Oct 17, 2025 - Systemd Service Management**

**Step 1: Check AI-Memory Service Status**
```bash
# SSH to DigitalOcean, then:
systemctl status ai-memory

# Also test endpoint:
curl http://209.38.143.71:8100/health

# Expected response:
# {"ok": true}
```

**Step 2: Check if AI-Memory is Listening on Port 8100**
```bash
sudo lsof -i :8100
# OR
netstat -tulnp | grep 8100

# Expected output:
# uvicorn running on 0.0.0.0:8100
```

**Step 3: Restart AI-Memory if Down**
```bash
# Restart the systemd service
sudo systemctl restart ai-memory

# Check logs
journalctl -u ai-memory -f --lines 50

# Verify it's working:
curl http://127.0.0.1:8100/health
```

**Step 4: Restart Orchestrator (if AI-Memory was down)**
```bash
# Restart ChatStack orchestrator
sudo systemctl restart orchestrator

# Check status
systemctl status orchestrator

# View logs
journalctl -u orchestrator -f --lines 20
```

### Quick Health Check Script
```bash
# Add to your server for quick diagnostics:
echo "Checking AI-Memory..." && curl -s http://209.38.143.71:8100/health | jq
echo "Checking ChatStack Web..." && curl -s http://127.0.0.1:5000/health | jq
echo "Checking Orchestrator..." && curl -s http://127.0.0.1:8001/health | jq
```

**Remember:** AI-Memory must be running BEFORE ChatStack starts, otherwise ChatStack will start in degraded mode without memory/admin features.

---

### User Preferences
Preferred communication style: Simple, everyday language.

**File Naming Convention:**
- Add project identifier suffix to configuration files to avoid conflicts
- Examples: `docker-compose-cs.yml` (ChatStack), `docker-compose-ai.yml` (AI-Memory)
- Prevents accidental overwrites when managing multiple services

### System Architecture
The system operates as a true microservices architecture with a clear separation of concerns:

1.  **Phone System (ChatStack)**: Flask orchestrator (`main.py`) handles Twilio webhooks.
2.  **AI Engine**: FastAPI backend (`app/main.py`) manages LLM integration and conversation flow.
3.  **AI-Memory Service**: External HTTP service handles all persistent memory and admin configuration.

All admin settings (greetings, voice settings, AI instructions) are stored in the AI-Memory service, enabling dynamic configuration without code deployment.

**CRITICAL: Environment Configuration**
The `/opt/ChatStack/.env` file on the DigitalOcean server contains all production secrets and must **NEVER** be deleted, overwritten, or modified. Secrets are in `.env`, non-secrets in `config.json`.

**Core Components:**

-   **LLM Integration**: Fully migrated to OpenAI Realtime API (gpt-realtime) for AI responses with 2-2.5 second response times.
-   **Memory System**: A persistent hybrid, three-tier system for unlimited conversation memory:
    -   **Layer 1: Rolling Thread History**: FastAPI maintains a deque of up to 500 messages per unique `thread_id` (e.g., `user_{phone_number}`), saved to and loaded from the database. It features automatic memory consolidation at 400 messages and provides both within-call and cross-call continuity.
    -   **Layer 2: Automatic Memory Consolidation**: Triggers at 400 messages, using an LLM to extract structured data (people, facts, preferences, commitments) from the oldest 200 messages. This data is de-duplicated and the thread history is pruned.
    -   **Layer 3: AI-Memory Service**: An HTTP-based service (`http://209.38.143.71:8100`) for permanent storage of structured facts, admin settings, and user registration.
-   **Prompt Engineering**: Employs file-based system prompts for AI personalities, intelligent context packing, and safety triggers.
-   **Tool System**: An extensible, JSON schema-based architecture for external tool execution (e.g., meeting booking, message sending) with a central dispatcher.
-   **Data Models**: Pydantic for type-safe validation of request/response models.
-   **Safety & Security**: Multi-tier content filtering, PII protection, rate limiting, and input validation.
-   **Notion CRM Integration**: Complete bi-directional sync with Notion via a Node.js/Express service. This integrates customer profiles, call logs, policies, tasks, and calendars, enriching AI context and logging all call transcripts.

**UI/UX Decisions:**
-   **Admin Panel**: Web interface at `/admin.html` for dynamic control over greetings, voice settings, and AI personality.
-   **30-Slider Personality Control**: Fine-grained AI behavior control across 30 dimensions (warmth, empathy, directness, humor, etc.) with 5 quick presets (Professional Agent, Friendly Helper, Assertive Closer, Empathetic Support, Balanced Default). Each slider (0-100) generates natural language instructions injected into system prompts.
-   **Voice-First Design**: Seamless voice interaction using ElevenLabs TTS.
-   **Real-time Updates**: Admin changes apply immediately.
-   **Customer Authentication**: Secure login system with password hashing, session management, and protected dashboard access.
-   **Multi-Tenant Dashboard**: Each customer has isolated access to their AI settings, call history, and configuration.

**Technical Implementations:**
-   **Python Frameworks**: Flask and FastAPI.
-   **Database**: PostgreSQL with `pgvector` for embeddings.
-   **Containerization**: Docker and `docker-compose`.
-   **Web Server**: Nginx for HTTPS termination and proxying.
-   **Deployment**: Primarily DigitalOcean Droplets.

### External Dependencies

**Services:**
-   **Twilio**: For voice call management and webhooks.
-   **OpenAI API**: Primary LLM service using GPT Realtime (`https://api.openai.com/v1/chat/completions`).
-   **ElevenLabs**: For natural voice synthesis (Text-to-Speech).
-   **AI-Memory Service**: External HTTP service for conversation memory persistence (`http://209.38.143.71:8100`).
-   **Notion API Service**: Node.js/Express server (port 8200) for Notion integration.

**Databases:**
-   **PostgreSQL**: Used with `pgvector` for conversation memory and semantic search.

**Libraries (Key Examples):**
-   **FastAPI** & **Uvicorn**: Web framework and ASGI server.
-   **Pydantic**: Data validation.
-   **NumPy**: Vector operations.
-   **Requests**: HTTP client.
-   **psycopg2**: PostgreSQL adapter.