# Deployment Instructions - Stable Thread ID Implementation

## 🎯 What Changed

Implemented stable `thread_id` based on phone numbers for cross-call conversation continuity.

### Changes Made:
1. **Flask (`main.py` line 686)**: Generate `thread_id = f"user_{user_id}"` instead of using Twilio CallSid
2. **FastAPI Memory Parser (`app/http_memory.py` lines 175-191)**: Parse newline-separated JSON from ai-memory service
3. **Documentation (`replit.md`)**: Added comprehensive hybrid architecture documentation

## 📦 Deployment to Production

### Step 1: Push to GitHub
```bash
# From this Replit workspace:
git add main.py app/http_memory.py replit.md
git commit -m "Implement stable thread_id for cross-call continuity"
git push origin main
```

### Step 2: Deploy on DigitalOcean Server
```bash
# SSH into production server
ssh root@209.38.143.71  # or your server IP

# Navigate to ChatStack directory
cd /opt/ChatStack

# Pull latest changes
git pull origin main

# Rebuild and restart containers
docker-compose down
docker-compose up -d --build

# Verify services are running
docker ps
docker logs chatstack-web-1 --tail 50
docker logs chatstack-orchestrator-worker-1 --tail 50
```

### Step 3: Test Cross-Call Continuity

#### Option A: Use Test Script (Recommended)
```bash
# On production server
cd /opt/ChatStack
python test_thread_continuity.py
```

Expected output:
- ✅ Call 1: User introduces name
- ✅ Call 2: AI remembers name from previous call
- ✅ Thread isolation: Different users don't see each other's data

#### Option B: Real Phone Test
1. **First Call**: Call +1-949-707-1290
   - Say: "Hi, my name is John Smith and I need help with auto insurance"
   - Hang up

2. **Second Call** (from same phone): Call +1-949-707-1290 again
   - Say: "What is my name?"
   - Expected: AI should remember "John Smith" from the first call

3. **Verify in Logs**:
```bash
# Check that stable thread_id is being used
docker logs chatstack-web-1 | grep "persistent thread_id"
# Should show: 🧵 Using persistent thread_id=user_9495565377 for user 9495565377

# Check FastAPI is maintaining history
docker logs chatstack-orchestrator-worker-1 | grep "thread="
```

## 🔍 How to Verify It's Working

### Check Thread History Size
```bash
# Inside FastAPI container, check THREAD_HISTORY
docker exec -it chatstack-orchestrator-worker-1 python -c "
from app.main import THREAD_HISTORY
print(f'Active threads: {len(THREAD_HISTORY)}')
for thread_id, history in list(THREAD_HISTORY.items())[:3]:
    print(f'  {thread_id}: {len(history)} messages')
"
```

### Check AI-Memory Service
```bash
# Verify memories are being stored with actual content
curl -X POST http://209.38.143.71:8100/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{"user_id": "9495565377", "message": "conversation", "limit": 10}'
```

Should return JSON with `message` fields containing actual conversation content, not empty strings.

## 🎯 Benefits of New Architecture

1. **Cross-Call Continuity**: Callers can hang up and call back - AI remembers the conversation
2. **Fast Performance**: 200+ message rolling history (no database queries per turn)
3. **Durable Facts**: Important info (names, policy numbers) survives server restarts via ai-memory service
4. **Scalable**: Thread-based architecture supports multiple concurrent calls

## 🔧 Tuning Parameters

### Increase History Window (if needed)
In `app/main.py` line 34:
```python
# Current: 100 messages (~50 turns)
THREAD_HISTORY: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=100))

# For longer memory: increase to 200
THREAD_HISTORY: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=200))
```

### Enable/Disable Features
In `app/main.py` lines 37-38:
```python
ENABLE_RECAP = True           # write/read tiny durable recap to AI-Memory
DISCOURAGE_GUESSING = True    # add system rail when no memories retrieved
```

## ⚠️ Important Notes

1. **Thread History Scope**: In-process history survives container uptime only. Server restarts will clear THREAD_HISTORY.
2. **Durable Storage**: Use ai-memory service for facts that must survive restarts (names, policy numbers, birthdays).
3. **Phone Number Format**: Thread IDs use normalized phone format: `user_9495565377` (10 digits, no +1).
4. **Single Worker Required**: Docker compose must use `--workers 1` to maintain session state.

## 🐛 Troubleshooting

### Issue: AI doesn't remember across calls
```bash
# Check thread_id is stable
docker logs chatstack-web-1 | grep "persistent_thread_id"
# Should be same for same phone number

# Check if THREAD_HISTORY is growing
docker logs chatstack-orchestrator-worker-1 | grep "Rolling in-process history"
```

### Issue: Empty message fields in ai-memory
```bash
# Verify fix is deployed
grep "json.dumps(value)" /opt/ChatStack/app/http_memory.py
# Should show line 81 with json.dumps()
```

### Issue: Container restarts lose history
This is expected behavior. For critical facts, use ai-memory service storage:
```python
# Store important facts durably
mem_store.write("person", "name", {"name": "John Smith"}, user_id="9495565377")
```

## 📊 Monitoring

### Check Memory Usage
```bash
docker stats chatstack-orchestrator-worker-1
```

With 100-message threads for ~100 active users: ~50-100MB RAM usage is normal.

### Clear Old Threads (if needed)
```bash
docker restart chatstack-orchestrator-worker-1
# Clears all THREAD_HISTORY, durable facts remain in ai-memory
```
