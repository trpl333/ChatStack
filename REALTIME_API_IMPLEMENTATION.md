# OpenAI Realtime API Implementation Guide

## Overview
This implementation migrates the Peterson Family Insurance phone AI system from the current architecture (OpenAI Chat Completions + ElevenLabs TTS) to OpenAI's Realtime API for faster response times.

**Expected Performance:** 1.2-1.5 seconds (down from current 2-2.5 seconds)

## Architecture Changes

### Before (Current System)
```
Twilio → Flask (/phone/incoming) → OpenAI Text API → Flask → ElevenLabs TTS → Twilio
```
**Response Time:** 2-2.5 seconds

### After (Realtime API)
```
Twilio ←→ Flask (WebSocket /phone/media-stream) ←→ OpenAI Realtime API
```
**Response Time:** 1.2-1.5 seconds (40-50% faster)

## New Files Created

### 1. `app/realtime_bridge.py`
**Purpose:** Bridge between Twilio Media Streams and OpenAI Realtime API

**Key Components:**
- `RealtimeBridge` class: Manages WebSocket connections
- Audio format conversion: mulaw 8kHz ↔ PCM16 24kHz
- Bidirectional audio streaming queues
- OpenAI session management

### 2. `main.py` (Updated)
**New Endpoints:**
- `GET/WS /phone/media-stream` - WebSocket endpoint for Twilio Media Streams
- `POST /phone/incoming-realtime` - New incoming call handler using Realtime API

**New Function:**
- `build_system_instructions_with_memory()` - Injects conversation context into Realtime API session

## Deployment to DigitalOcean Server

### Prerequisites
- SSH access to DO server (root@209.38.143.71)
- Python dependencies: `flask-sock`, `websockets`, `openai>=1.58.1`
- Existing `/opt/ChatStack/.env` file (DO NOT MODIFY)

### Deployment Steps

1. **Make deployment script executable:**
   ```bash
   chmod +x deploy_realtime_to_do.sh
   ```

2. **Run deployment:**
   ```bash
   ./deploy_realtime_to_do.sh
   ```
   
   This will:
   - Create backup of current code
   - Upload new files
   - Install dependencies
   - Restart Docker containers

3. **Update Twilio webhook:**
   - Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
   - Select your phone number
   - Update "A CALL COMES IN" webhook to:
     ```
     https://voice.theinsurancedoctors.com/phone/incoming-realtime
     ```

4. **Test the system:**
   - Call your Twilio number
   - Monitor logs:
     ```bash
     ssh root@209.38.143.71
     cd /opt/ChatStack
     docker-compose logs -f web
     ```

## Configuration

### OpenAI Realtime API Settings
Located in `app/realtime_bridge.py` - `connect_to_openai()` method:

```python
{
    "modalities": ["text", "audio"],
    "voice": "alloy",  # Options: alloy, echo, fable, onyx, nova, shimmer
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "temperature": 0.7,
    "max_response_output_tokens": 150,
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500
    }
}
```

### Admin Settings Integration
The system uses existing admin settings:
- `ai_instructions` - Base system prompt for the AI
- `agent_name` - Name placeholder replacement
- `voice_id` - OpenAI voice selection (default: "alloy")

## Testing & Verification

### Latency Tracking
The implementation includes comprehensive timing logs:
```
⏱️ Stage: Call received | Elapsed: 0.001s
⏱️ Stage: OpenAI connection established | Elapsed: 0.250s
⏱️ Stage: First audio chunk received | Elapsed: 1.200s
```

### Expected Logs
```
📞 Incoming call from +1234567890 - Using OpenAI Realtime API
🌐 WebSocket connection established from Twilio
✅ Connected to OpenAI Realtime API
📤 Sent session configuration to OpenAI
✅ OpenAI session created: sess_abc123
📞 Stream started: MZabc123, User: 9495565377, Callback: True
🎤 User started speaking
🎤 User stopped speaking
📝 OpenAI text: Hello! How can I help you today?
✅ OpenAI audio response complete
🔌 WebSocket connection closed | Total time: 45.123s
```

### Common Issues

#### Issue: WebSocket handshake fails
**Solution:** Ensure nginx proxy has WebSocket upgrade headers:
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

#### Issue: Audio playback is garbled
**Solution:** Verify audio format conversion is working correctly. Check logs for conversion errors.

#### Issue: OpenAI connection fails
**Solution:** Verify `OPENAI_API_KEY` is set in `/opt/ChatStack/.env`

## Rollback Procedure

If issues occur, rollback to previous version:

1. **Find latest backup:**
   ```bash
   ssh root@209.38.143.71
   ls -la /opt/ChatStack_backup_*
   ```

2. **Restore backup:**
   ```bash
   cp -r /opt/ChatStack_backup_20251002_123456/* /opt/ChatStack/
   cd /opt/ChatStack
   docker-compose restart
   ```

3. **Revert Twilio webhook:**
   Update webhook back to:
   ```
   https://voice.theinsurancedoctors.com/phone/incoming
   ```

## Monitoring & Maintenance

### Key Metrics to Track
- **Response latency:** Target < 1.5s
- **WebSocket connection stability:** Should stay open for entire call duration
- **Audio quality:** No garbling or distortion
- **Memory integration:** Context properly injected

### Logs to Monitor
```bash
# Real-time logs
docker-compose logs -f web

# Search for errors
docker-compose logs web | grep -i "error"

# Check Realtime API connections
docker-compose logs web | grep "OpenAI Realtime"
```

## Cost Comparison

### Current System (per 1000 calls, avg 2 min each)
- OpenAI Chat Completions: ~$15-20
- ElevenLabs TTS: ~$25-30
- **Total:** ~$40-50

### Realtime API (per 1000 calls, avg 2 min each)
- OpenAI Realtime API: ~$30-40 (combined text + audio)
- **Total:** ~$30-40

**Cost savings:** 20-25% reduction

## Next Steps After Deployment

1. **Test thoroughly:**
   - Make 10+ test calls
   - Verify conversation continuity
   - Check memory recall
   - Test callback detection

2. **Monitor performance:**
   - Track response times
   - Monitor error rates
   - Check audio quality

3. **Optimize if needed:**
   - Adjust VAD thresholds
   - Tune turn detection settings
   - Optimize system instructions

4. **Consider full migration:**
   - If successful, replace `/phone/incoming` with Realtime API
   - Remove old OpenAI + ElevenLabs code
   - Update all Twilio webhooks

## Support & Troubleshooting

- **OpenAI Realtime API Docs:** https://platform.openai.com/docs/guides/realtime
- **Twilio Media Streams Docs:** https://www.twilio.com/docs/voice/media-streams
- **Flask-Sock Docs:** https://flask-sock.readthedocs.io/

For issues, check:
1. Docker container logs
2. OpenAI API status
3. Twilio webhook configuration
4. Network connectivity between services
