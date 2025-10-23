# NeuroSphere Voice - Multi-Tenant AI Phone System Platform

### Overview
NeuroSphere Voice is a multi-tenant, AI-powered phone system platform designed for insurance agencies. It provides each customer with a custom AI agent featuring a unique personality, voice, and dedicated phone number. Built on FastAPI, the platform offers intelligent call handling with persistent memory, rapid 2-2.5 second AI response times, secure customer authentication, and isolated conversation memory per tenant. It acts as middleware between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations through memory retrieval, prompt engineering, and extensible tools. The system utilizes OpenAI's Realtime API and is deployed on DigitalOcean.

### User Preferences
Preferred communication style: Simple, everyday language.

**File Naming Convention:**
- Add project identifier suffix to configuration files to avoid conflicts
- Examples: `docker-compose-cs.yml` (ChatStack), `docker-compose-ai.yml` (AI-Memory)
- Prevents accidental overwrites when managing multiple services

**Multi-Project Architecture:**
- This project is part of a 4-service ecosystem (ChatStack, AI-Memory, LeadFlowTracker, NeuroSphere Send Text)
- All repos are cloned locally in `external/` directory for full code visibility
- Shared architecture documentation in `MULTI_PROJECT_ARCHITECTURE.md` keeps all services aligned
- Run `node fetch_repos.js` to update external repos with latest code from GitHub
- This prevents API endpoint mismatches and ensures architectural consistency

### System Architecture
The system employs a microservices architecture with distinct components:

**Core Components:**
-   **ChatStack (Phone System)**: A Flask orchestrator handles Twilio webhooks.
-   **AI Engine**: A FastAPI backend manages LLM integration and conversation flow.
-   **AI-Memory Service**: An external HTTP service for persistent memory and admin configuration, allowing dynamic configuration without code deployments.
-   **LLM Integration**: Utilizes OpenAI Realtime API (gpt-realtime) for AI responses, achieving 2-2.5 second response times.
-   **Memory System**: A hybrid system with V1 (raw) and V2 (structured) storage:
    -   **Rolling Thread History**: FastAPI maintains a deque of up to 500 messages per unique `thread_id`, saved to and loaded from PostgreSQL. It includes automatic memory consolidation and provides both within-call and cross-call continuity.
    -   **Automatic Memory Consolidation**: Triggers at 400 messages, using an LLM to extract structured data (people, facts, preferences, commitments) from older messages, which are then de-duplicated and the thread history pruned.
    -   **Memory V1 (Legacy)**: Raw memories stored as key-value pairs, requires normalization on retrieval (slower)
    -   **Memory V2 (Recommended)**: Pre-processed enriched profiles with:
        - Call summaries instead of raw transcripts
        - Extracted key variables (identity, relationships, vehicles, policies)
        - Personality trait running averages (Big 5 + communication style)
        - Fast retrieval via dedicated endpoints: `/caller/profile/{phone}`, `/personality/averages/{phone}`, `/call/summary`
    -   **AI-Memory Service**: External HTTP service at `http://209.38.143.71:8100` providing both V1 and V2 APIs.
-   **Call Recording & Transcripts**: Every call automatically saves:
    -   **Transcript**: Retrieved from AI-Memory (authoritative source) and saved to `/opt/ChatStack/static/calls/{call_sid}.txt` with formatted conversation history
    -   **Audio Recording**: Downloaded from Twilio after call ends, saved to `/opt/ChatStack/static/calls/{call_sid}.mp3`
    -   **Call Index**: Metadata stored in `calls.json` with timestamps, caller info, and file references
    -   **Security**: Twilio signature validation, URL sanitization, file size limits, atomic writes with file locking
-   **Prompt Engineering**: Employs file-based system prompts for AI personalities, intelligent context packing, and safety triggers.
-   **Tool System**: An extensible, JSON schema-based architecture with a central dispatcher for external tool execution.
-   **Data Models**: Pydantic for type-safe validation.
-   **Safety & Security**: Multi-tier content filtering, PII protection, rate limiting, and input validation.
-   **Notion CRM Integration**: Bi-directional sync with Notion via a Node.js/Express service for customer profiles, call logs, policies, tasks, and calendars.

**UI/UX Decisions:**
-   **Admin Panel**: Web interface at `/admin.html` for dynamic control of greetings, voice settings, and AI personality.
-   **30-Slider Personality Control**: Fine-grained AI behavior control across 30 dimensions with 5 quick presets, generating natural language instructions for system prompts.
-   **Voice-First Design**: Seamless voice interaction using ElevenLabs TTS.
-   **Real-time Updates**: Admin changes apply immediately.
-   **Customer Authentication**: Secure login system with password hashing and session management.
-   **Multi-Tenant Dashboard**: Isolated access for each customer to their AI settings, call history, and configuration.

**Technical Implementations:**
-   **Python Frameworks**: Flask and FastAPI.
-   **Database**: PostgreSQL with `pgvector`.
-   **Containerization**: Docker and `docker-compose`.
-   **Web Server**: Nginx for HTTPS termination and proxying.
-   **Deployment**: DigitalOcean Droplets.
-   **Environment Configuration**: Production secrets are stored in `/opt/ChatStack/.env` on DigitalOcean, non-secrets in `config.json`.

**Deployment Procedures:**

**Standard Update Process** (Use this for all code deployments):
```bash
# SSH into DigitalOcean server
ssh root@your-digitalocean-ip
cd /opt/ChatStack

# Run the standardized update script
./update.sh
```

The `update.sh` script is the **one consistent way** to deploy updates. It:
- Pulls latest code from GitHub
- Rebuilds all Docker services (including orchestrator-worker)
- Restarts everything properly
- Shows status and logs

**Technical Details:**
-   **orchestrator-worker** (FastAPI backend on port 8001): Must be rebuilt after code changes to pick up new Python code
-   **web service** (Flask admin on port 5000): Auto-reloads with gunicorn `--reload` flag for most changes
-   **Nginx changes**: Copy config to `/etc/nginx/sites-enabled/`, test with `nginx -t`, reload with `systemctl reload nginx`
-   **Voice settings**: Loaded from AI-Memory service at startup; orchestrator restart required after admin panel changes to apply new voice/personality
-   **Production location**: `/opt/ChatStack/` on DigitalOcean droplet
-   **Secrets**: Stored in `/opt/ChatStack/.env` (never commit to GitHub)

### External Dependencies

**Services:**
-   **Twilio**: For voice call management.
-   **OpenAI API**: Primary LLM service (GPT Realtime).
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