# 🚨 Final Server Setup - AI-Memory Connection Issue

## Critical Issue Found

Your orchestrator logs show:
```
ERROR: Failed to connect to AI-Memory service: host='172.19.0.4', port=8100
WARNING: Memory store running in degraded mode
```

**This means:** Your system can't save or retrieve conversation memory right now!

---

## 🔧 Fix Steps (Run on Server)

### Step 1: Check AI-Memory Service Status

```bash
# Is AI-Memory running?
docker ps | grep ai-memory

# If you see a container, check its logs
docker logs <ai-memory-container-id> --tail=50

# Test if it's reachable
curl http://209.38.143.71:8100/health
```

**Expected:** Should return `{"status":"ok","memory_store":"connected"}`

---

### Step 2: Fix Docker Network Issue

The orchestrator is looking for AI-Memory at `172.19.0.4:8100` (Docker internal IP) but can't connect.

**Option A: Use External IP**

```bash
cd /opt/ChatStack

# Check config.json
cat config.json | grep ai_memory_url

# Should be: "ai_memory_url": "http://209.38.143.71:8100"
# If it shows 172.19.0.4, update it:

nano config.json
# Change: "ai_memory_url": "http://209.38.143.71:8100"
# Save: Ctrl+O, Enter, Ctrl+X

# Restart orchestrator
docker-compose restart orchestrator-worker
```

**Option B: Add to Docker Network**

```bash
# Find AI-Memory container name
docker ps | grep ai-memory

# Connect it to ChatStack network
docker network connect chatstack_appnet <ai-memory-container-name>

# Restart orchestrator
docker-compose restart orchestrator-worker
```

---

### Step 3: Fix Nginx for Transcript Access

```bash
cd /opt/ChatStack

# Run the nginx fix script
sudo ./fix-nginx-calls-path.sh

# Verify nginx is happy
sudo nginx -t
sudo systemctl reload nginx
```

---

### Step 4: Verify Everything Works

```bash
# Run full health check
./server-health-check.sh

# Watch orchestrator logs
docker-compose logs -f orchestrator-worker
```

**Look for:**
- ✅ `Connecting to AI-Memory service at http://...`
- ✅ `Memory store connected` (not "degraded mode")

---

## 🎯 Quick All-in-One Command

If you want to run everything at once:

```bash
cd /opt/ChatStack

# Restart with fresh config
docker-compose restart orchestrator-worker

# Wait for startup
sleep 10

# Check logs
docker-compose logs orchestrator-worker --tail=20 | grep -E "AI-Memory|Memory store"

# Fix nginx
sudo ./fix-nginx-calls-path.sh

# Health check
./server-health-check.sh
```

---

## 🧪 Test Call After Fix

Once AI-Memory connects, make a test call and verify:

```bash
# Watch for these log messages:
docker-compose logs -f orchestrator-worker | grep -E "thread_id|AI-Memory|Retrieved.*messages"
```

**Success looks like:**
```
INFO: Connecting to AI-Memory service at http://209.38.143.71:8100
INFO: ✅ Memory store connected
INFO: 🔍 Retrieving transcript from AI-Memory for call CAxxxxx, thread_id=customer_X_user_Y
INFO: ✅ Retrieved 45 messages from AI-Memory
INFO: 🧠 Sending 20 previous messages to OpenAI for context
```

---

## 📊 What This Fixes

Once AI-Memory connects:
- ✅ AI will remember names from previous calls
- ✅ Conversation history persists across calls
- ✅ Transcripts save to database
- ✅ SMS gets actual summary
- ✅ Notion logs full call data

**Without AI-Memory:** System works but has no long-term memory.

---

## 🆘 If AI-Memory Container is Missing

If `docker ps | grep ai-memory` returns nothing:

```bash
# Check if it's stopped
docker ps -a | grep ai-memory

# If you see it, start it:
docker start <container-id>

# If it doesn't exist, you need to rebuild it:
cd /opt/ai-memory
docker-compose up -d
```

---

## ✅ Success Indicators

**After fixes, you should see:**

1. **Health check shows:**
   ```
   ✅ Orchestrator (8001) - Running
   ✅ AI-Memory (8100) - Connected
   ```

2. **Logs show:**
   ```
   INFO: Memory store connected
   (Not "degraded mode")
   ```

3. **Test call works:**
   - AI remembers your name
   - Transcript saves
   - SMS has summary

---

Run these steps and let me know what you see! 🚀
