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
- **GitHub Repo**: `https://github.com/trpl333/ai-memory.git`
- **DigitalOcean Path**: `/opt/ai-memory/`
- **Service**: FastAPI memory service (port 8100)
- **Purpose**: Stores conversation memory, admin settings, user data
- **Deployment**:
  ```bash
  cd /opt/ai-memory
  git fetch origin
  git reset --hard origin/main
  docker-compose down
  docker-compose up -d --build
  docker logs ai-memory-worker-1 --tail 20
  ```
- **⚠️ IMPORTANT**: The `ai-memory-main.py` file in the ChatStack repo is just a REFERENCE COPY. To modify AI-Memory, you MUST work in the separate `ai-memory` repository.

### Other Services on DigitalOcean
- `/opt/neurosphere-sync/` - Notion sync service
- `/opt/orchestrator/` - Legacy orchestrator (if still active)

**When making changes:**
1. ✅ Identify which repo/service needs the change
2. ✅ Make changes in the correct GitHub repository
3. ✅ Deploy to the correct `/opt/` directory
4. ❌ NEVER edit files directly on the server

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