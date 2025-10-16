# LLM Mode Switcher - Pre-Deployment Verification Checklist

## 🚨 Run This Before Deploying to DigitalOcean

---

## ✅ Phase 1: Environment Variables

### 1.1 Verify .env File Exists
```bash
# On DigitalOcean
ls -la /opt/ChatStack/.env
cat /opt/ChatStack/.env | grep -E "LLM_MODE|OPENAI|RUNPOD|WHISPER|ELEVENLABS"
```

**Expected**: All required variables present

### 1.2 Test Docker Bridge Network
```bash
# Inside container
docker exec chatstack-web-1 ping -c 3 172.17.0.1
docker exec chatstack-web-1 curl http://172.17.0.1:8100/health
```

**Expected**: Successful ping and 200 response from AI-Memory

### 1.3 Verify Hot Reload Works
```bash
# Change mode
echo "LLM_MODE=runpod_streaming" >> /opt/ChatStack/.env

# Restart containers (REQUIRED after env change)
docker-compose down && docker-compose up -d --build

# Verify mode changed
docker logs chatstack-web-1 --tail 20 | grep "LLM_MODE"
```

**Expected**: New mode logged on startup

---

## ✅ Phase 2: Route & Proxy Verification

### 2.1 Check Flask Routes
```bash
# List all Flask routes
curl http://localhost:5000/admin-status | jq

# Test health endpoint
curl http://localhost:5000/health/llm | jq
```

**Expected**: Both return 200 OK

### 2.2 Check FastAPI Routes
```bash
# List FastAPI routes  
curl http://localhost:8001/docs

# Test health
curl http://localhost:8001/health | jq
```

**Expected**: Swagger docs + 200 health check

### 2.3 Test Nginx Proxy (External)
```bash
# From outside server
curl https://voice.theinsurancedoctors.com/api/prompt-blocks/presets | jq | head -10

# Test new LLM health route
curl https://voice.theinsurancedoctors.com/health/llm | jq
```

**Expected**: Valid JSON responses

---

## ✅ Phase 3: WebSocket Namespaces

### 3.1 Verify Distinct Paths
```bash
# Check Nginx config
cat /etc/nginx/sites-available/voice.theinsurancedoctors.com | grep -E "location.*realtime|location.*streaming"
```

**Expected**: Separate location blocks for:
- `/phone/media-stream` (OpenAI Realtime)
- `/streaming/*` (RunPod if needed)

### 3.2 Test WebSocket Connection
```bash
# OpenAI Realtime path
wscat -c "wss://voice.theinsurancedoctors.com/phone/media-stream"
```

**Expected**: Connection established (then Ctrl+C to exit)

---

## ✅ Phase 4: Service Latency & Timeouts

### 4.1 Test Whisper Endpoint
```bash
curl -X POST https://a100.neurospherevoice.com/v1/audio/transcriptions \
  -F "file=@test_audio.wav" \
  -F "model=whisper-large-v3" \
  --max-time 5
```

**Expected**: Response within 5 seconds

### 4.2 Test RunPod LLM
```bash
time curl -X POST https://a100.neurospherevoice.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Meta-Llama-3-70B-Instruct","messages":[{"role":"user","content":"Hi"}],"max_tokens":50}' \
  --max-time 3
```

**Expected**: Response within 3 seconds, real time printed

### 4.3 Test ElevenLabs Rate Limits
```bash
# Send 5 concurrent requests
for i in {1..5}; do
  curl -X POST https://api.elevenlabs.io/v1/text-to-speech/$ELEVENLABS_VOICE_ID \
    -H "xi-api-key: $ELEVENLABS_API_KEY" \
    -d '{"text":"Test","model_id":"eleven_flash_v2_5"}' &
done
wait
```

**Expected**: All succeed without 429 errors

---

## ✅ Phase 5: Mode Switching Safety

### 5.1 Check Active Call Count
```bash
# Add this endpoint first
curl http://localhost:5000/api/active-calls | jq '.count'
```

**Expected**: Returns current call count

### 5.2 Test Mode Switch with Lock
```bash
# Try switching while calls active (should fail gracefully)
curl -X POST http://localhost:5000/admin/llm-mode \
  -d '{"mode":"runpod_streaming"}' | jq
```

**Expected**: Error if calls active, success if idle

### 5.3 Verify Grace Period
```bash
# Switch mode
curl -X POST http://localhost:5000/admin/llm-mode -d '{"mode":"runpod_streaming"}'

# Check if old sessions finish on old mode
# (New calls should use new mode after 5 sec grace)
sleep 6
curl http://localhost:5000/admin-status | jq '.llm_mode'
```

**Expected**: Mode switches after grace period

---

## ✅ Phase 6: Streaming JSON Parser

### 6.1 Test RunPod Streaming Response
```bash
curl -N -X POST https://a100.neurospherevoice.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Meta-Llama-3-70B-Instruct","messages":[{"role":"user","content":"Count to 5"}],"stream":true}' \
  2>&1 | tee /tmp/stream_test.log
```

**Expected**: Check for partial chunks or malformed JSON in log

### 6.2 Verify Buffer Parser
```bash
# Check code has buffer handling
grep -n "buffer.*json" app/runpod_streaming.py
```

**Expected**: Buffer logic exists to handle partial chunks

---

## ✅ Phase 7: Logging Configuration

### 7.1 Check Log Throttling
```bash
# Make a test call, check log volume
docker logs chatstack-orchestrator-worker-1 --tail 100 | wc -l
```

**Expected**: <100 lines per call (not 1000s)

### 7.2 Verify Token Logging is Throttled
```bash
grep -n "token_idx % 10" app/runpod_streaming.py
```

**Expected**: Token logging happens every 10th token, not every token

---

## ✅ Phase 8: AI-Memory Namespace Isolation

### 8.1 Test Mode-Specific Keys
```bash
# Store test memory
curl -X POST http://209.38.143.71:8100/memory/store \
  -d '{"user_id":"test_user:openai_realtime","key":"test","value":"openai_data"}'

curl -X POST http://209.38.143.71:8100/memory/store \
  -d '{"user_id":"test_user:runpod_streaming","key":"test","value":"runpod_data"}'

# Retrieve and verify isolation
curl http://209.38.143.71:8100/memory/retrieve?user_id=test_user:openai_realtime | jq
curl http://209.38.143.71:8100/memory/retrieve?user_id=test_user:runpod_streaming | jq
```

**Expected**: Each mode has separate memory namespace

### 8.2 Check Prompt Blocks Namespace
```bash
# Verify prompts use mode key
docker logs chatstack-web-1 | grep "prompt_blocks.*user_id"
```

**Expected**: User IDs include mode: `admin:openai_realtime` or `admin:runpod_streaming`

---

## ✅ Phase 9: End-to-End Flow Test

### 9.1 OpenAI Realtime Mode
```bash
# Set mode
echo "LLM_MODE=openai_realtime" > /opt/ChatStack/.env.mode
docker-compose restart

# Make test call
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming \
  -d "From=+15555555555&CallSid=test123"

# Check logs
docker logs chatstack-orchestrator-worker-1 --tail 20 | grep -i "openai\|realtime"
```

**Expected**: Call routed to OpenAI Realtime

### 9.2 RunPod Streaming Mode
```bash
# Set mode
echo "LLM_MODE=runpod_streaming" > /opt/ChatStack/.env.mode
docker-compose restart

# Make test call
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming \
  -d "From=+15555555555&CallSid=test456"

# Check logs
docker logs chatstack-orchestrator-worker-1 --tail 30 | grep -i "runpod\|whisper\|elevenlabs"
```

**Expected**: Call uses Whisper → RunPod → ElevenLabs pipeline

---

## ✅ Phase 10: Fallback & Error Handling

### 10.1 Simulate OpenAI Failure
```bash
# Temporarily break OpenAI key
docker exec chatstack-web-1 sed -i 's/OPENAI_API_KEY=.*/OPENAI_API_KEY=invalid/' /app/.env

# Make call (should fallback to RunPod)
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "From=+15555555555"

# Check logs for fallback
docker logs chatstack-orchestrator-worker-1 --tail 50 | grep -i "fallback\|runpod"

# Restore key
docker-compose restart
```

**Expected**: Automatic fallback to RunPod mode

### 10.2 Simulate RunPod Failure
```bash
# Set invalid RunPod endpoint
docker exec chatstack-web-1 sed -i 's|RUNPOD_A100_ENDPOINT=.*|RUNPOD_A100_ENDPOINT=https://invalid.com|' /app/.env

# Make call (should fallback to OpenAI)
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "From=+15555555555"

# Check logs
docker logs chatstack-orchestrator-worker-1 --tail 50 | grep -i "fallback\|openai"

# Restore endpoint
docker-compose restart
```

**Expected**: Automatic fallback to OpenAI mode

---

## ✅ Phase 11: Performance Benchmarks

### 11.1 Measure OpenAI Latency
```bash
# Time 10 calls
for i in {1..10}; do
  time curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming \
    -d "From=+15555555555&CallSid=bench_$i" > /dev/null
done
```

**Expected**: Average <600ms

### 11.2 Measure RunPod Latency
```bash
# Switch to RunPod mode
echo "LLM_MODE=runpod_streaming" >> /opt/ChatStack/.env
docker-compose restart

# Time 10 calls
for i in {1..10}; do
  time curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming \
    -d "From=+15555555555&CallSid=bench_runpod_$i" > /dev/null
done
```

**Expected**: Average <800ms

---

## ✅ Phase 12: Security Audit

### 12.1 Verify No Secrets in Logs
```bash
docker logs chatstack-web-1 --tail 500 | grep -i "api_key\|secret\|password"
```

**Expected**: No actual secret values (only variable names)

### 12.2 Check .env in .gitignore
```bash
cat /opt/ChatStack/.gitignore | grep ".env"
```

**Expected**: `.env` is excluded

### 12.3 Verify HTTPS Everywhere
```bash
# Check all external endpoints use HTTPS
grep -r "http://" app/ | grep -v "localhost\|127.0.0.1\|172.17.0.1"
```

**Expected**: Only internal services use http://

---

## ✅ Phase 13: Admin Panel UI Test

### 13.1 Load Admin Panel
```bash
curl https://voice.theinsurancedoctors.com/admin.html | grep -i "llm.*mode"
```

**Expected**: LLM Mode toggle visible in HTML

### 13.2 Test Mode Switch via UI
```bash
# Simulate UI toggle
curl -X POST https://voice.theinsurancedoctors.com/api/admin/llm-mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"runpod_streaming"}' | jq
```

**Expected**: `{"success": true, "mode": "runpod_streaming"}`

### 13.3 Verify UI Reflects Change
```bash
curl https://voice.theinsurancedoctors.com/admin-status | jq '.llm_mode'
```

**Expected**: New mode returned

---

## ✅ Phase 14: Rollback Procedure Test

### 14.1 Practice Emergency Rollback
```bash
# Simulate problem - switch to broken mode
curl -X POST http://localhost:5000/admin/llm-mode -d '{"mode":"invalid"}'

# Emergency rollback
echo "LLM_MODE=openai_realtime" > /opt/ChatStack/.env
docker-compose down && docker-compose up -d --build

# Verify
curl http://localhost:5000/admin-status | jq '.llm_mode'
```

**Expected**: Successfully reverted to OpenAI Realtime

---

## ✅ Final Checklist Summary

| Phase | Check | Status |
|-------|-------|--------|
| 1 | .env variables complete | [ ] |
| 1 | Docker bridge network works | [ ] |
| 1 | Hot reload functional | [ ] |
| 2 | Flask routes accessible | [ ] |
| 2 | FastAPI routes accessible | [ ] |
| 2 | Nginx proxy works | [ ] |
| 3 | WebSocket namespaces separate | [ ] |
| 4 | Whisper latency <5s | [ ] |
| 4 | RunPod latency <3s | [ ] |
| 4 | ElevenLabs handles concurrent | [ ] |
| 5 | Active call counting works | [ ] |
| 5 | Mode switch has lock/grace | [ ] |
| 6 | Streaming parser handles chunks | [ ] |
| 7 | Logging is throttled | [ ] |
| 8 | AI-Memory namespaces isolated | [ ] |
| 9 | OpenAI E2E works | [ ] |
| 9 | RunPod E2E works | [ ] |
| 10 | OpenAI→RunPod fallback works | [ ] |
| 10 | RunPod→OpenAI fallback works | [ ] |
| 11 | OpenAI latency acceptable | [ ] |
| 11 | RunPod latency acceptable | [ ] |
| 12 | No secrets in logs | [ ] |
| 12 | .env in gitignore | [ ] |
| 12 | HTTPS everywhere | [ ] |
| 13 | Admin UI shows toggle | [ ] |
| 13 | UI mode switch works | [ ] |
| 14 | Rollback procedure works | [ ] |

---

## 🚀 Ready for Production?

**All checkboxes marked?** → Proceed with deployment  
**Any failures?** → Fix before deploying

**Post-Deployment:**
1. Monitor logs for 24 hours
2. A/B test with 10% traffic
3. Collect latency metrics
4. Gather user feedback

---

**Emergency Contacts:**
- RunPod Support: support@runpod.io
- OpenAI Status: status.openai.com
- ElevenLabs Support: support@elevenlabs.io
