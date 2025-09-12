# Peterson Family Insurance AI Phone System - Complete Technical Documentation

## Overview

**Purpose**: AI-powered phone system for Peterson Family Insurance Agency using Samantha as the AI agent
**Phone Number**: +19497071290
**Production URL**: https://voice.theinsurancedoctors.com
**Target Response Time**: 2-2.5 seconds
**Deployment**: DigitalOcean Droplet with Docker + RunPod GPU for LLM

NeuroSphere Orchestrator is a FastAPI-based AI phone system that provides intelligent call handling with persistent memory capabilities. The system features an AI assistant named "Samantha" that maintains conversation continuity through a PostgreSQL vector database, supports tool integrations for external actions, and includes safety modes for content filtering. The orchestrator acts as a middleware layer between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations with memory retrieval, prompt engineering, and extensible tool functionality.

## User Preferences

Preferred communication style: Simple, everyday language.

---

## Architecture Flow

```
Twilio Call → nginx (HTTPS) → Flask Orchestrator (port 5000) → FastAPI Backend (port 8001) → RunPod LLM → ElevenLabs TTS → MP3 Audio → Twilio → Caller
                                     ↓
                            AI-Memory Service (port 8100) + PostgreSQL + pgvector
```

---

## Core Files & Scripts

### **Main Application Files**
| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `main.py` | Flask Orchestrator | Twilio webhooks, config bootstrap, static serving, starts FastAPI backend |
| `app/main.py` | FastAPI Backend | `/v1/chat` endpoint, health checks, admin interface |
| `app/llm.py` | LLM Integration | Communicates with RunPod endpoint for AI responses |
| `app/memory.py` | Memory Store | PostgreSQL + pgvector operations for conversation memory |
| `app/models.py` | Data Models | Pydantic request/response models |
| `app/packer.py` | Prompt Engineering | Context packing and memory injection |
| `app/tools.py` | Tool System | External tool execution and integration |

### **Configuration Files**
| File | Purpose | Contents |
|------|---------|----------|
| `config.json` | Public Configuration | Non-secret settings, URLs, model names |
| `config-internal.json` | Internal Configuration | Internal ports, hosts, service endpoints |
| `config_loader.py` | Configuration Manager | Centralized config, hot-reload, secret masking |

### **Deployment Files**
| File | Purpose | Usage |
|------|---------|--------|
| `docker-compose.yml` | Container Orchestration | Defines web service (nginx commented out) |
| `Dockerfile` | Container Build | Python 3.11, gunicorn, production setup |
| `deploy.sh` | Deployment Script | DigitalOcean automated deployment |
| `deploy-requirements.txt` | Production Dependencies | Production-specific Python packages |
| `nginx.conf` | Nginx Configuration | Proxy rules template |

---

## Required Secrets (Environment Variables)

### **Critical Secrets**
| Secret | Purpose | Format |
|--------|---------|---------|
| `DATABASE_URL` | PostgreSQL Connection | `postgresql://user:pass@host:port/dbname` |
| `TWILIO_ACCOUNT_SID` | Twilio API Authentication | `ACxxxxxxxx...` |
| `TWILIO_AUTH_TOKEN` | Twilio API Authentication | `xxxxxxxx...` |
| `ELEVENLABS_API_KEY` | Text-to-Speech Service | `sk-xxxxxxxx...` |
| `SESSION_SECRET` | Flask Session Security | Strong random string |

### **Database Secrets**
| Secret | Purpose |
|--------|---------|
| `PGHOST` | PostgreSQL Host |
| `PGPORT` | PostgreSQL Port (typically 25060 for DigitalOcean) |
| `PGDATABASE` | Database Name |
| `PGUSER` | Database Username |
| `PGPASSWORD` | Database Password |

### **Optional Secrets**
| Secret | Purpose | When Needed |
|--------|---------|-------------|
| `OPENAI_API_KEY` | OpenAI API Access | If using OpenAI instead of RunPod |
| `LLM_API_KEY` | Custom LLM Authentication | For RunPod or other LLM services |

---

## Network Architecture

### **External Ports**
| Port | Service | Purpose |
|------|---------|---------|
| 80 | nginx | HTTP (redirects to HTTPS) |
| 443 | nginx | HTTPS with SSL certificates |
| 22 | SSH | Server administration |

### **Internal Ports**
| Port | Service | Purpose |
|------|---------|---------|
| 5000 | Flask App | Main orchestrator, Twilio webhooks |
| 8001 | FastAPI | LLM backend, chat API |
| 8100 | AI-Memory | Memory service (external) |
| 5432 | PostgreSQL | Database (managed service) |

---

## API Endpoints

### **Public Endpoints (Flask - Port 5000)**
| Method | Endpoint | Purpose | Called By |
|--------|----------|---------|-----------|
| POST | `/phone/incoming` | Twilio webhook for incoming calls | Twilio |
| POST | `/phone/process-speech` | Handle user speech input | Twilio |
| GET | `/static/audio/*.mp3` | Serve generated audio files | Twilio |
| GET | `/admin` | Admin interface | Administrators |

### **Internal Endpoints (FastAPI - Port 8001)**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/v1/chat/completions` | LLM chat completions |
| POST | `/v1/memories` | Memory storage |
| GET | `/admin` | Admin static files |

### **External Dependencies**
| Service | Endpoint | Purpose |
|---------|----------|---------|
| RunPod LLM | `https://a40.neurospherevoice.com/v1/chat/completions` | AI responses |
| ElevenLabs | `https://api.elevenlabs.io/v1/text-to-speech` | Natural voice synthesis |
| AI-Memory | `http://209.38.143.71:8100` | Conversation memory |
| Twilio | Webhook callbacks | Voice call management |

---

## Data Flow - Complete Call Process

### **1. Incoming Call**
```
Caller dials +19497071290
↓
Twilio receives call
↓
POST to https://voice.theinsurancedoctors.com/phone/incoming
```

### **2. Initial Greeting**
```
nginx proxy → Flask main.py:handle_incoming_call()
↓
get_personalized_greeting() checks memory
↓
text_to_speech() → ElevenLabs TTS → saves audio/greeting_CALLSID.mp3
↓
Returns TwiML with <Play> tag for audio file
```

### **3. Speech Processing**
```
User speaks → Twilio ASR → POST /phone/process-speech
↓
Flask receives transcription
↓
Calls ai_response() → FastAPI backend port 8001
↓
Backend calls RunPod LLM via app/llm.py
↓
LLM response → ElevenLabs TTS → saves audio/response_TIMESTAMP.mp3
↓
Returns TwiML with <Play> tag
```

### **4. Memory Storage**
```
Throughout conversation:
↓
Memory objects saved via AI-Memory service
↓
PostgreSQL with pgvector for semantic search
↓
Retrieved for context in future calls
```

---

## Deployment Components

### **Docker Configuration**
```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports: ["5000:5000"]
    restart: unless-stopped
    # nginx service commented out (uses system nginx)
```

### **Required nginx Configuration**
```nginx
# Location block needed in /etc/nginx/sites-available/default
location /phone/ {
    proxy_pass http://127.0.0.1:5000/phone/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### **Deployment Commands**
```bash
# Initial Deployment
git clone https://github.com/trpl333/ChatStack.git
cd ChatStack
nano .env  # Configure all secrets
chmod +x deploy.sh
./deploy.sh

# Updates
git pull origin main
docker-compose down
docker-compose up -d --build

# Verification
docker ps  # Should show chatstack-web-1 running
curl https://voice.theinsurancedoctors.com/phone/incoming -X POST -d "test=1"
```

---

## Troubleshooting Checklist

### **Call Hangs Up Issues**
1. ✓ Check nginx proxy configuration for `/phone/` location
2. ✓ Verify Flask app responding: `curl http://localhost:5000/phone/incoming`
3. ✓ Check Docker container logs: `docker logs chatstack-web-1`
4. ✓ Test HTTPS endpoint: `curl https://voice.theinsurancedoctors.com/phone/incoming`

### **Voice Issues**
1. ✓ Verify `ELEVENLABS_API_KEY` is set
2. ✓ Check `/static/audio/` directory permissions
3. ✓ Test ElevenLabs integration in logs
4. ✓ Fallback to Twilio voice if ElevenLabs fails

### **AI Response Issues**
1. ✓ Verify RunPod endpoint: `https://a40.neurospherevoice.com`
2. ✓ Check `LLM_BASE_URL` environment variable
3. ✓ Test LLM connection in startup logs
4. ✓ Verify no `/v1/v1/` duplicate in URLs

---

## System Architecture

### Backend Architecture
- **Framework**: Flask + FastAPI hybrid with asyncio support for handling concurrent requests
- **Entry Point**: Flask orchestrator (main.py) spawns FastAPI backend (app/main.py)
- **Modular Design**: Separated concerns across app modules (llm, memory, packer, tools, models)
- **Lifespan Management**: Async context manager for startup/shutdown procedures and resource cleanup

### Memory System
- **Vector Database**: PostgreSQL with pgvector extension for semantic similarity search
- **Embedding Strategy**: Deterministic hash-based embeddings (placeholder for production embedding service)
- **Memory Types**: Categorized storage (person, preference, project, rule, moment, fact) with TTL support
- **Short-term Memory**: In-memory conversation recaps for maintaining context within sessions
- **Memory Lifecycle**: Automatic cleanup of expired memories and retention policies

### LLM Integration
- **OpenAI-Compatible API**: Configurable base URL and model selection via environment variables
- **Request Management**: Structured message passing with temperature, top_p, and max_tokens controls
- **Error Handling**: Connection validation and timeout management for external LLM services
- **Response Processing**: Token usage tracking and response formatting

### Prompt Engineering
- **System Personas**: File-based system prompts for different AI personalities (Sam, Safety mode)
- **Context Packing**: Intelligent memory retrieval and prompt construction
- **Safety Triggers**: Content filtering and safety mode activation based on context
- **Memory Integration**: Relevant memory injection into conversation context

### Tool System
- **Extensible Architecture**: JSON schema-based tool definitions with parameter validation
- **Tool Dispatcher**: Central routing system for tool execution and response handling
- **Built-in Tools**: Meeting booking, message sending, and other productivity integrations
- **Error Recovery**: Graceful handling of tool failures with fallback responses

### Data Models
- **Pydantic Validation**: Type-safe request/response models with field validation
- **Message Structure**: Role-based message system (system, user, assistant)
- **Memory Objects**: Structured memory representation with metadata and TTL
- **Tool Interfaces**: Standardized tool call and response models

### Safety and Security
- **Content Filtering**: Multi-tier safety system with configurable strictness levels
- **PII Protection**: Automatic detection and masking of personally identifiable information
- **Rate Limiting**: Built-in protections against abuse and resource exhaustion
- **Input Validation**: Comprehensive request validation and sanitization

## External Dependencies

### Database
- **PostgreSQL**: Primary data store with pgvector extension for vector operations
- **pgcrypto**: UUID generation and cryptographic functions
- **Connection Management**: psycopg2 with connection pooling and transaction management

### LLM Services
- **OpenAI-Compatible API**: External LLM endpoint (configurable base URL)
- **Default Model**: Qwen2-7B-Instruct with support for model switching
- **Authentication**: Bearer token support for secured LLM access

### Python Libraries
- **FastAPI**: Web framework with automatic API documentation
- **Uvicorn**: ASGI server for production deployment
- **Pydantic**: Data validation and serialization
- **NumPy**: Vector operations and embedding manipulation
- **Requests**: HTTP client for LLM API communication

### Development and Deployment
- **Environment Configuration**: Extensive environment variable support for deployment flexibility
- **CORS Support**: Cross-origin request handling for web interfaces
- **Logging**: Structured logging with configurable levels
- **Health Checks**: LLM connection validation and system status monitoring

### Optional Integrations
- **Redis**: Recommended for production short-term memory storage
- **Embedding Services**: OpenAI Embeddings, Sentence Transformers for production embedding generation
- **Monitoring**: Application performance monitoring and observability tools