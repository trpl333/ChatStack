# 🚀 Quick Deployment - Push & Pull

## Changes Ready to Deploy:
✅ AI conversation memory fix (sends previous 20 messages to OpenAI)
✅ Transcript retrieval fix (newline-delimited JSON parsing)
✅ Notion dashboard integration (Call SID, URLs, Status, Agent)
✅ Server health check script
✅ Transcript path diagnostic script
✅ Nginx configuration fix script

---

## Step 1: Push to GitHub (from Replit)

### Option A: Replit UI
1. Click **Source Control** icon (left sidebar)
2. Review changes
3. Commit message: `Fix AI memory + Notion integration + nginx transcripts`
4. Click **Commit & Push**

### Option B: Shell
```bash
git add -A
git commit -m "Fix AI memory + Notion integration + nginx transcripts"
git push origin main
```

---

## Step 2: Deploy on DigitalOcean Server

```bash
# SSH to server
ssh root@your-server-ip

# Navigate to project
cd /opt/ChatStack

# Pull latest code
git pull origin main

# Make scripts executable
chmod +x server-health-check.sh debug-transcript-path.sh fix-nginx-calls-path.sh

# Rebuild orchestrator (picks up code changes)
docker-compose up -d --build orchestrator-worker

# Wait for it to start
sleep 10

# Fix nginx to serve transcripts
./fix-nginx-calls-path.sh

# Start Notion API server
cd .notion_backup_replit
node notion-api-server.js &
cd ..

# Run health check
./server-health-check.sh
```

---

## Step 3: Verify Everything Works

```bash
# Check orchestrator health
curl http://localhost:8001/health

# Check Notion API
curl http://localhost:8200/health

# Test transcript access
./debug-transcript-path.sh

# Watch logs for next call
docker-compose logs -f orchestrator-worker
```

---

## What to Look For in Logs (Next Call):

✅ `🧠 Sending 20 previous messages to OpenAI for context`
✅ `✅ Retrieved 81 messages from AI-Memory` (full transcript)
✅ `📊 Logging call to Notion: CAxxxxx`
✅ `✅ Call logged to Notion dashboard`

---

## Quick Troubleshooting:

**If transcripts not accessible:**
```bash
./fix-nginx-calls-path.sh
```

**If Notion not logging:**
```bash
cd /opt/ChatStack/.notion_backup_replit
node notion-api-server.js &
curl http://localhost:8200/health
```

**If AI doesn't remember:**
```bash
# Check logs for:
docker-compose logs orchestrator-worker | grep "Sending.*messages to OpenAI"
```

---

## Expected Results:

✅ AI remembers previous calls
✅ Full transcripts saved (not truncated)
✅ Transcripts accessible via web: `https://voice.theinsurancedoctors.com/calls/{call_sid}.txt`
✅ Calls logged to Notion with full metadata
✅ SMS notifications sent (brief summary)
