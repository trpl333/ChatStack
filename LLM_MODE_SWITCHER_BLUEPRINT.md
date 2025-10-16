# LLM Mode Switcher Blueprint
## Dual-Mode Phone AI System: OpenAI Realtime ↔ RunPod Streaming

---

## 1. System Overview

### Current State
- **Active Mode**: OpenAI Realtime API (WebSocket)
- **Speed**: 400-600ms response time
- **Limitation**: Safety restrictions block custom personalities

### Proposed Enhancement
- **Dual-mode system** with admin toggle
- **Mode A**: OpenAI Realtime (fast, restricted)
- **Mode B**: RunPod A100 Streaming (fast, unrestricted)

---

## 2. Architecture Comparison

### Mode A: OpenAI Realtime (Current)
```
Twilio Voice Input
       ↓
OpenAI Realtime WebSocket (all-in-one)
  - Built-in STT (speech-to-text)
  - LLM inference (GPT-4o-realtime)
  - Built-in TTS (text-to-speech)
       ↓
Voice Output
```

**Latency**: ~400-600ms total

### Mode B: RunPod Streaming (New)
```
Twilio Voice Input
       ↓
Whisper STT (RunPod A100)
  - Convert audio → text
       ↓
RunPod LLM (Llama-3-70B streaming)
  - Stream tokens as generated
       ↓
ElevenLabs TTS (streaming)
  - Convert text → audio
       ↓
Voice Output
```

**Latency**: ~500-700ms with streaming (first audio ~300-400ms)

---

## 3. Configuration Structure

### 3.1 Environment Variables (.env)

**Location**: `/opt/ChatStack/.env` (DigitalOcean production)

```env
# ============= CORE SETTINGS =============
ENVIRONMENT=production
LLM_MODE=openai_realtime  # or: runpod_streaming

# ============= OPENAI REALTIME MODE =============
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-realtime-preview-2024-10-01

# ============= RUNPOD STREAMING MODE =============
# LLM Inference
RUNPOD_API_KEY=xxxxxxxxxxxxx  # May be empty if using internal routing
RUNPOD_A100_ENDPOINT=https://a100.neurospherevoice.com
RUNPOD_A40_ENDPOINT=https://a40.neurospherevoice.com
RUNPOD_LLM_MODEL=meta-llama/Meta-Llama-3-70B-Instruct

# Speech-to-Text (Whisper)
WHISPER_ENDPOINT=https://a100.neurospherevoice.com  # Can reuse same RunPod
WHISPER_MODEL=openai/whisper-large-v3

# Text-to-Speech (ElevenLabs)
ELEVENLABS_API_KEY=xxxxxxxxxxxxx
ELEVENLABS_VOICE_ID=FGY2WhTYpPnrIDTdsKH5
ELEVENLABS_MODEL=eleven_flash_v2_5

# ============= SHARED SERVICES =============
# AI-Memory (environment-aware)
AI_MEMORY_URL_PROD=http://172.17.0.1:8100      # Docker bridge (production)
AI_MEMORY_URL_DEV=http://209.38.143.71:8100    # External IP (development)

# Twilio (used by both modes)
TWILIO_ACCOUNT_SID=xxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxx

# Database (used by both modes)
DATABASE_URL=postgresql://user:pass@host:5432/db
```

### 3.2 Config File (config.json)

**Location**: `/opt/ChatStack/config.json` (committed to git, no secrets)

```json
{
  "llm_modes": {
    "openai_realtime": {
      "name": "OpenAI Realtime (Fast, Restricted)",
      "base_url": "https://api.openai.com/v1",
      "websocket_url": "wss://api.openai.com/v1/realtime",
      "supports_streaming": true,
      "uses_builtin_voice": true,
      "uses_builtin_stt": true,
      "estimated_latency_ms": 500
    },
    "runpod_streaming": {
      "name": "RunPod A100 (Fast, Unrestricted)",
      "llm_endpoint": "use_env:RUNPOD_A100_ENDPOINT",
      "stt_endpoint": "use_env:WHISPER_ENDPOINT",
      "tts_provider": "elevenlabs",
      "supports_streaming": true,
      "uses_builtin_voice": false,
      "uses_builtin_stt": false,
      "estimated_latency_ms": 650
    }
  },
  "default_mode": "openai_realtime",
  "fallback_mode": "runpod_streaming"
}
```

### 3.3 Admin Panel Settings (AI-Memory)

**Storage**: AI-Memory service (dynamic, user-controlled)

```json
{
  "setting_key": "llm_mode",
  "value": "openai_realtime",
  "options": ["openai_realtime", "runpod_streaming"],
  "updatable_via_ui": true
}
```

---

## 4. Secret & Port Mapping

### 4.1 Secrets by Mode

| Service | OpenAI Realtime | RunPod Streaming | Location |
|---------|----------------|------------------|----------|
| **LLM API Key** | `OPENAI_API_KEY` | `RUNPOD_API_KEY` (optional) | `.env` |
| **STT** | Built-in | Uses Whisper on RunPod | N/A |
| **TTS API Key** | Built-in | `ELEVENLABS_API_KEY` | `.env` |
| **Voice ID** | Default | `ELEVENLABS_VOICE_ID` | `.env` |

### 4.2 Endpoints by Mode (with namespace fixes)

| Service | OpenAI Realtime | RunPod Streaming |
|---------|----------------|------------------|
| **Main Endpoint** | `wss://api.openai.com/v1/realtime` | `https://a100.neurospherevoice.com` |
| **WebSocket Path** | `/phone/media-stream` | `/streaming/media` (distinct!) |
| **STT Endpoint** | Built-in | `https://a100.neurospherevoice.com/v1/audio` |
| **TTS Endpoint** | Built-in | `https://api.elevenlabs.io/v1` |
| **Ports** | 443 (HTTPS/WSS) | 443 (HTTPS) |

**Nginx Configuration (distinct paths to avoid collision):**
```nginx
# OpenAI Realtime WebSocket
location /phone/media-stream {
    proxy_pass http://127.0.0.1:8001/phone/media-stream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}

# RunPod Streaming (separate path)
location /streaming/ {
    proxy_pass http://127.0.0.1:8001/streaming/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### 4.3 Environment Detection (with Docker bridge verification)

```python
def get_ai_memory_url():
    """Environment-aware AI-Memory URL with fallback"""
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        # Try Docker bridge first
        bridge_url = os.getenv("AI_MEMORY_URL_PROD", "http://172.17.0.1:8100")
        
        # Verify Docker bridge is reachable
        try:
            response = requests.get(f"{bridge_url}/health", timeout=2)
            if response.status_code == 200:
                return bridge_url
        except requests.RequestException:
            logger.warning(f"Docker bridge {bridge_url} unreachable, falling back to external")
        
        # Fallback to external
        return os.getenv("AI_MEMORY_URL_DEV", "http://209.38.143.71:8100")
    else:
        return os.getenv("AI_MEMORY_URL_DEV", "http://209.38.143.71:8100")
```

---

## 5. Implementation Plan

### 5.1 Core Pipeline Router (with ChatGPT fixes)

**File**: `app/llm_router.py` (new file)

```python
import os
import asyncio
from threading import Lock

# Global lock to prevent mid-call mode switching
_mode_switch_lock = Lock()
_active_call_count = 0
_current_mode = None
_grace_period_seconds = 5

def increment_call_count():
    global _active_call_count
    _active_call_count += 1

def decrement_call_count():
    global _active_call_count
    _active_call_count = max(0, _active_call_count - 1)

async def get_active_llm_pipeline():
    """Get active LLM pipeline based on mode with hot reload and grace period"""
    global _current_mode
    
    # Hot reload mode from .env (fixes caching issue)
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    requested_mode = get_admin_setting("llm_mode", os.getenv("LLM_MODE", "openai_realtime"))
    
    # If mode changed and calls are active, wait for grace period
    if _current_mode != requested_mode and _active_call_count > 0:
        logger.warning(f"Mode switch requested during {_active_call_count} active calls. Applying {_grace_period_seconds}s grace period...")
        await asyncio.sleep(_grace_period_seconds)
    
    _current_mode = requested_mode
    
    if _current_mode == "openai_realtime":
        return OpenAIRealtimePipeline()
    elif _current_mode == "runpod_streaming":
        return RunPodStreamingPipeline()
    else:
        raise ValueError(f"Unknown LLM mode: {_current_mode}")

def switch_llm_mode(new_mode: str):
    """Switch LLM mode with safety checks"""
    global _current_mode
    
    with _mode_switch_lock:
        if _active_call_count > 0:
            raise RuntimeError(f"Cannot switch mode: {_active_call_count} calls active. Wait for completion.")
        
        _current_mode = new_mode
        # Update AI-Memory
        mem_store.write("admin_setting", "llm_mode", {"value": new_mode}, user_id="admin")
        logger.info(f"✅ LLM mode switched to: {new_mode}")
```

### 5.2 Pipeline Interface

```python
class BaseLLMPipeline(ABC):
    @abstractmethod
    async def process_audio(self, audio_data: bytes, user_id: str) -> AudioResponse:
        """Process audio input and return audio output"""
        pass
    
    @abstractmethod
    def get_config(self) -> dict:
        """Get pipeline configuration"""
        pass

class OpenAIRealtimePipeline(BaseLLMPipeline):
    async def process_audio(self, audio_data, user_id):
        # WebSocket connection to OpenAI Realtime
        # Returns audio directly
        pass

class RunPodStreamingPipeline(BaseLLMPipeline):
    async def process_audio(self, audio_data, user_id):
        # 1. Whisper STT: audio → text
        # 2. RunPod LLM: text → text (streaming)
        # 3. ElevenLabs TTS: text → audio (streaming)
        pass
```

### 5.3 Admin UI Toggle

**File**: `static/admin.html`

```html
<div class="card">
  <h4>🔧 LLM Mode Selection</h4>
  <select id="llmMode">
    <option value="openai_realtime">OpenAI Realtime (Fast, Restricted)</option>
    <option value="runpod_streaming">RunPod A100 (Fast, Unrestricted)</option>
  </select>
  <button onclick="saveLLMMode()">Switch Mode</button>
  <p class="text-muted">
    <strong>OpenAI:</strong> ~500ms, safety restrictions<br>
    <strong>RunPod:</strong> ~650ms, no restrictions
  </p>
</div>
```

### 5.4 Deployment Checklist

**Step 1: Update .env on DigitalOcean**
```bash
# SSH to DigitalOcean
nano /opt/ChatStack/.env

# Add new variables (keep existing secrets):
LLM_MODE=openai_realtime
RUNPOD_A100_ENDPOINT=https://a100.neurospherevoice.com
WHISPER_ENDPOINT=https://a100.neurospherevoice.com
ELEVENLABS_API_KEY=xxxxx
ELEVENLABS_VOICE_ID=FGY2WhTYpPnrIDTdsKH5
```

**Step 2: Deploy Code**
```bash
cd /opt/ChatStack
git fetch origin
git reset --hard origin/main
docker-compose down
docker-compose up -d --build
```

**Step 3: Verify**
```bash
# Check mode
curl http://localhost:5000/admin-status | jq '.llm_mode'

# Test both modes via admin panel
```

---

## 6. Streaming Implementation Details

### 6.1 OpenAI Realtime (Already Implemented)

```python
# app/llm.py - chat_realtime_stream()
ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime"

for token in ws_stream:
    yield token  # Tokens streamed in real-time
```

### 6.2 RunPod Streaming (with buffer parser fix)

```python
# New: app/runpod_streaming.py
async def runpod_stream_inference(text: str):
    """Stream LLM response from RunPod with proper chunk buffering"""
    buffer = ""
    token_idx = 0
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{RUNPOD_ENDPOINT}/v1/chat/completions",
            json={
                "model": "meta-llama/Meta-Llama-3-70B-Instruct",
                "messages": [{"role": "user", "content": text}],
                "stream": True  # Enable streaming
            },
            timeout=aiohttp.ClientTimeout(total=30)  # Add timeout
        ) as response:
            async for line in response.content:
                try:
                    if line.startswith(b"data: "):
                        buffer += line.decode('utf-8')[6:].strip()
                        
                        # Only parse when we have complete JSON
                        if buffer.endswith("}") or buffer.endswith("]"):
                            data = json.loads(buffer)
                            buffer = ""  # Clear buffer after successful parse
                            
                            if "choices" in data:
                                delta = data["choices"][0]["delta"].get("content", "")
                                if delta:
                                    # Throttle logging (every 10th token)
                                    if token_idx % 10 == 0:
                                        logger.debug(f"Token {token_idx}: {delta}")
                                    token_idx += 1
                                    yield delta
                except json.JSONDecodeError:
                    # Partial chunk - keep buffering
                    continue
                except asyncio.TimeoutError:
                    logger.error("RunPod streaming timeout")
                    break
```

### 6.3 ElevenLabs Streaming (Already Implemented)

```python
# main.py - text_to_speech()
audio_stream = client.text_to_speech.stream(
    voice_id=ELEVENLABS_VOICE_ID,
    text=text,
    model_id="eleven_flash_v2_5"
)

for chunk in audio_stream:
    yield chunk  # Audio streamed as generated
```

---

## 7. Error Handling & Fallback

### 7.1 Mode-Specific Errors

```python
try:
    pipeline = get_active_llm_pipeline()
    response = await pipeline.process_audio(audio, user_id)
except OpenAIError as e:
    logger.error(f"OpenAI error: {e}")
    # Fallback to RunPod
    pipeline = RunPodStreamingPipeline()
    response = await pipeline.process_audio(audio, user_id)
except RunPodError as e:
    logger.error(f"RunPod error: {e}")
    # Fallback to OpenAI
    pipeline = OpenAIRealtimePipeline()
    response = await pipeline.process_audio(audio, user_id)
```

### 7.2 Service Health Checks

```python
@app.route('/health/llm', methods=['GET'])
def llm_health():
    mode = os.getenv("LLM_MODE")
    
    if mode == "openai_realtime":
        # Test OpenAI connection
        status = test_openai_connection()
    elif mode == "runpod_streaming":
        # Test RunPod + Whisper + ElevenLabs
        status = {
            "runpod": test_runpod(),
            "whisper": test_whisper(),
            "elevenlabs": test_elevenlabs()
        }
    
    return jsonify({"mode": mode, "status": status})
```

---

## 8. Performance Benchmarks

### Expected Latencies (with streaming)

| Stage | OpenAI Realtime | RunPod Streaming |
|-------|----------------|------------------|
| **First audio** | ~200ms | ~300-400ms |
| **STT** | Built-in | ~100-150ms |
| **LLM (first token)** | ~100ms | ~150-200ms |
| **TTS (first audio)** | Built-in | ~150-200ms |
| **Network overhead** | ~50ms | ~100ms |
| **TOTAL (perceived)** | ~400ms | ~500-650ms |

### Streaming Benefits

Both modes stream responses, so users hear the first words quickly:
- **OpenAI**: First word in ~200ms, complete response ~400-600ms
- **RunPod**: First word in ~300-400ms, complete response ~500-700ms

**Difference**: ~100-200ms (barely perceptible on phone)

---

## 9. Cost Analysis

### OpenAI Realtime
- **Input audio**: $0.06 / minute
- **Output audio**: $0.24 / minute
- **Total**: ~$0.30 / minute of conversation

### RunPod A100 + ElevenLabs
- **RunPod A100**: $1.89/hour = $0.0315/minute (when running)
- **Whisper** (on same GPU): Included
- **ElevenLabs**: ~$0.30 per 1000 characters
- **Total**: ~$0.05-0.10 / minute (cheaper at scale)

### Cost Crossover
- **Low volume** (<50 calls/day): OpenAI cheaper (no idle GPU cost)
- **High volume** (>200 calls/day): RunPod cheaper (GPU amortized)

---

## 10. Security Considerations

### Secret Storage
- ✅ All API keys in `.env` (never in git)
- ✅ `.env` excluded via `.gitignore`
- ✅ Production `.env` on DigitalOcean never overwritten
- ✅ Mode selection in AI-Memory (admin can toggle)

### Network Security
- ✅ HTTPS/WSS only (no unencrypted connections)
- ✅ API keys passed in headers (not URL params)
- ✅ RunPod endpoints proxied through nginx with rate limiting

### Data Privacy
- ✅ Conversations stay on your infrastructure (DO + RunPod)
- ✅ OpenAI mode: Data sent to OpenAI (check their DPA)
- ✅ RunPod mode: Data stays in your RunPod instance

---

## 11. Testing Plan

### Phase 1: Unit Tests
- [ ] Test mode switching logic
- [ ] Test secret loading for each mode
- [ ] Test pipeline routing

### Phase 2: Integration Tests
- [ ] Test OpenAI Realtime flow end-to-end
- [ ] Test RunPod Streaming flow end-to-end
- [ ] Test mode switching during runtime

### Phase 3: Load Tests
- [ ] Concurrent calls in OpenAI mode
- [ ] Concurrent calls in RunPod mode
- [ ] Measure actual latencies under load

### Phase 4: Production Validation
- [ ] A/B test with real calls
- [ ] Monitor error rates per mode
- [ ] Collect user feedback on quality/latency

---

## 12. Migration Path

### Day 1: Preparation
1. Add new env variables to `/opt/ChatStack/.env`
2. Test RunPod A100 endpoint connectivity
3. Verify ElevenLabs API key works

### Day 2: Development
1. Create `llm_router.py` with pipeline interface
2. Implement `RunPodStreamingPipeline` class
3. Add admin UI toggle for mode selection

### Day 3: Testing
1. Test both modes in development (Replit)
2. Deploy to staging environment
3. Run automated tests

### Day 4: Production Deployment
1. Deploy to DigitalOcean production
2. Start in OpenAI mode (safe default)
3. Monitor for 24 hours

### Day 5: Gradual Rollout
1. Switch 10% of calls to RunPod mode
2. Monitor latency and errors
3. Increase to 50% if successful
4. Full switch or keep as toggle option

---

## 13. Future Enhancements

### Phase 2 (Future)
- **Auto mode switching**: Based on load, time of day, or user preference
- **Custom models**: Support for fine-tuned models on RunPod
- **Multi-GPU**: Load balance across multiple RunPod instances
- **Voice cloning**: Custom voices per customer using ElevenLabs

### Phase 3 (Future)
- **Local Whisper**: Run STT on DigitalOcean to reduce latency
- **Local TTS**: Piper TTS or Coqui for cost savings
- **Hybrid mode**: OpenAI for complex, RunPod for simple queries

---

## 14. Rollback Plan

If RunPod mode has issues:

```bash
# Emergency rollback via admin panel
curl -X POST https://voice.theinsurancedoctors.com/admin/settings \
  -d '{"llm_mode": "openai_realtime"}'

# Or via .env
ssh root@209.38.143.71
echo "LLM_MODE=openai_realtime" >> /opt/ChatStack/.env
docker-compose restart web
```

---

## 15. Success Metrics

### Performance
- ✅ RunPod mode achieves <800ms total latency
- ✅ No increase in dropped calls
- ✅ <1% error rate per mode

### Quality
- ✅ User satisfaction rating >4.5/5 for both modes
- ✅ Personality customization works in RunPod mode
- ✅ Voice quality matches or exceeds OpenAI

### Business
- ✅ Cost per call reduced by >30% in RunPod mode
- ✅ Ability to customize personalities increases sales
- ✅ System uptime >99.9% with fallback mode

---

## 16. Documentation Updates Needed

- [ ] Update `replit.md` with dual-mode architecture
- [ ] Add `.env.example` with all required variables
- [ ] Create admin guide for mode switching
- [ ] Document troubleshooting per mode

---

## APPENDIX A: Complete .env Template

```env
# Environment
ENVIRONMENT=production

# LLM Mode Selection
LLM_MODE=openai_realtime

# OpenAI Realtime
OPENAI_API_KEY=sk-proj-xxxxx
OPENAI_MODEL=gpt-4o-realtime-preview-2024-10-01

# RunPod Streaming
RUNPOD_API_KEY=xxxxx
RUNPOD_A100_ENDPOINT=https://a100.neurospherevoice.com
RUNPOD_A40_ENDPOINT=https://a40.neurospherevoice.com
RUNPOD_LLM_MODEL=meta-llama/Meta-Llama-3-70B-Instruct

# Whisper STT
WHISPER_ENDPOINT=https://a100.neurospherevoice.com
WHISPER_MODEL=openai/whisper-large-v3

# ElevenLabs TTS
ELEVENLABS_API_KEY=xxxxx
ELEVENLABS_VOICE_ID=FGY2WhTYpPnrIDTdsKH5
ELEVENLABS_MODEL=eleven_flash_v2_5

# AI-Memory
AI_MEMORY_URL_PROD=http://172.17.0.1:8100
AI_MEMORY_URL_DEV=http://209.38.143.71:8100

# Twilio
TWILIO_ACCOUNT_SID=xxxxx
TWILIO_AUTH_TOKEN=xxxxx

# Database
DATABASE_URL=postgresql://user:pass@host:5432/db

# Other
SESSION_SECRET=xxxxx
SERVER_URL=https://voice.theinsurancedoctors.com
```

---

## APPENDIX B: Quick Reference Commands

```bash
# Check current mode
curl http://localhost:5000/admin-status | jq '.llm_mode'

# Switch to OpenAI
curl -X POST http://localhost:5000/admin/settings -d '{"llm_mode":"openai_realtime"}'

# Switch to RunPod
curl -X POST http://localhost:5000/admin/settings -d '{"llm_mode":"runpod_streaming"}'

# Test RunPod endpoint
curl -X POST https://a100.neurospherevoice.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Meta-Llama-3-70B-Instruct","messages":[{"role":"user","content":"Hello"}],"max_tokens":50}'

# Monitor logs
docker logs chatstack-orchestrator-worker-1 --tail 100 -f
```

---

**Blueprint Status**: Ready for review  
**Next Step**: Validate with ChatGPT, then implement  
**Estimated Implementation**: 2-3 days (with testing)
