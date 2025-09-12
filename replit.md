# Peterson Family Insurance AI Phone System

## Overview
This project is an AI-powered phone system for Peterson Family Insurance, utilizing "Samantha" as the AI agent. The system, built on NeuroSphere Orchestrator, is a FastAPI-based solution designed for intelligent call handling with persistent memory. It aims for a rapid response time of 2-2.5 seconds. Key capabilities include maintaining conversation continuity via a PostgreSQL vector database, integrating external tools for actions, and employing safety modes for content filtering. The orchestrator serves as middleware between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations through memory retrieval, prompt engineering, and extensible tool functionality.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The system employs a hybrid Flask + FastAPI backend. A Flask orchestrator (`main.py`) handles Twilio webhooks and spawns the FastAPI backend (`app/main.py`), which manages the core `/v1/chat` endpoint and LLM integration.

### Core Components:
- **LLM Integration**: Communicates with an OpenAI-compatible API endpoint (defaulting to Qwen2-7B-Instruct) for AI responses, with structured message passing and error handling.
- **Memory System**: Utilizes PostgreSQL with the `pgvector` extension for semantic search, storing categorized memories (person, preference, project, rule, moment, fact) with TTL support. Short-term memory is managed for in-session context.
- **Prompt Engineering**: Employs file-based system prompts for AI personalities, intelligent context packing from memory, and safety triggers for content filtering.
- **Tool System**: An extensible, JSON schema-based architecture for external tool execution (e.g., meeting booking, message sending) with a central dispatcher and error recovery.
- **Data Models**: Pydantic for type-safe validation of request/response models, including role-based messages and structured memory objects.
- **Safety & Security**: Features multi-tier content filtering, PII protection, rate limiting, and comprehensive input validation.

### UI/UX Decisions:
- Minimal UI for administrative functions via an `/admin` endpoint.
- Focus on seamless voice interaction, with audio files served for natural voice synthesis.

### Technical Implementations:
- **Python Frameworks**: Flask and FastAPI.
- **Database**: PostgreSQL with `pgvector` for vector embeddings and `pgcrypto` for UUIDs.
- **Containerization**: Docker for deployment, with `docker-compose.yml` for orchestration.
- **Web Server**: Nginx for HTTPS termination, proxying requests to the Flask and FastAPI services.
- **Deployment**: Primarily on DigitalOcean Droplets with a RunPod GPU for LLM inference.

## External Dependencies

### Services:
- **Twilio**: For voice call management and incoming call webhooks.
- **RunPod LLM**: Primary LLM service (specific endpoint: `https://a40.neurospherevoice.com/v1/chat/completions`).
- **ElevenLabs**: For natural voice synthesis and text-to-speech conversion.
- **AI-Memory Service**: An external service for conversation memory persistence (`http://209.38.143.71:8100`).

### Databases:
- **PostgreSQL**: Used with `pgvector` extension for conversation memory and semantic search.

### Libraries (Key Examples):
- **FastAPI** & **Uvicorn**: Web framework and ASGI server.
- **Pydantic**: Data validation.
- **NumPy**: Vector operations.
- **Requests**: HTTP client.
- **psycopg2**: PostgreSQL adapter.

### Optional Integrations (Planned/Recommended):
- **Redis**: For production short-term memory.
- **Embedding Services**: Such as OpenAI Embeddings or Sentence Transformers for production embedding generation.

---

## Nginx Configuration Management

### **Check Active Configurations**
```bash
ls /etc/nginx/sites-enabled/
```

**Expected configurations:**
- `voice-theinsurancedoctors-com.conf` → AI Phone System
- `neurosphere-llms.conf` → RunPod LLM proxy (if serving different domain)

### **Rules**
1. **Only one config** should claim `server_name voice.theinsurancedoctors.com`
2. **The `voice-theinsurancedoctors-com.conf`** must contain both `/phone/` and `/static/` proxy blocks:
   ```nginx
   location /phone/ {
       proxy_pass http://127.0.0.1:5000/phone/;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }

   location /static/ {
       proxy_pass http://127.0.0.1:5000/static/;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
3. **`neurosphere-llms.conf`** should serve different hostname (e.g., `a40.neurospherevoice.com`)

### **Conflict Detection**
```bash
# Check what neurosphere-llms.conf serves
sudo cat /etc/nginx/sites-enabled/neurosphere-llms.conf | grep -E "server_name|listen|default_server"
```

**Action Rules:**
- **Keep it** if it serves different domain
- **Disable it** if it references `voice.theinsurancedoctors.com` or has `default_server`

### **Deployment Commands**
```bash
# Deploy canonical config
sudo cp /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf /etc/nginx/sites-enabled/

# Remove conflicts (only if they claim same domain)
sudo rm /etc/nginx/sites-enabled/default  # if exists
sudo rm /etc/nginx/sites-enabled/neurosphere-llms.conf  # only if conflicts

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### **Verification**
```bash
# Test static files proxied correctly
curl -I https://voice.theinsurancedoctors.com/static/audio/
# Should return: HTTP/1.1 200 OK (not 404)

# Test phone endpoint
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "test=1"
# Should return TwiML with HTTPS URLs
```

---

## Troubleshooting Checklist

### **Call Hangs Up Issues**
1. ✓ **Check for multiple nginx configurations causing conflicts**:
   ```bash
   ls /etc/nginx/sites-enabled/
   # Should prioritize: voice-theinsurancedoctors-com.conf
   # Check conflicts: sudo cat /etc/nginx/sites-enabled/neurosphere-llms.conf | grep -E "server_name|default_server"
   ```
2. ✓ **Verify `/static/` proxy is configured** for audio file access:
   ```bash
   curl -I https://voice.theinsurancedoctors.com/static/audio/
   # Should return 200 OK, not 404
   ```
3. ✓ Check nginx proxy configuration for `/phone/` location
4. ✓ Verify Flask app responding: `curl http://localhost:5000/phone/incoming`
5. ✓ Check Docker container logs: `docker logs chatstack-web-1`
6. ✓ Test HTTPS endpoint: `curl https://voice.theinsurancedoctors.com/phone/incoming`

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