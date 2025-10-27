# Deploy Latest Changes to DigitalOcean Production Server

## 🚀 Quick Deployment Steps

### 1. SSH into Your Server
```bash
ssh root@your-droplet-ip
# Or use your configured SSH alias
```

### 2. Navigate to Project Directory
```bash
cd /opt/ChatStack
```

### 3. Pull Latest Code
```bash
git status  # Check for any uncommitted changes
git pull origin main  # Or your branch name
```

### 4. Copy Updated Files
```bash
# Copy Notion client to app directory
cp .notion_backup_replit/notion_client.py app/

# Verify it was copied
ls -lh app/notion_client.py
```

### 5. Rebuild Orchestrator Service (CRITICAL!)
```bash
# This picks up all code changes including:
# - Fixed AI-Memory JSON parsing
# - Conversation history sent to OpenAI
# - Notion integration

docker-compose up -d --build orchestrator-worker

# Wait 10 seconds for service to start
sleep 10
```

### 6. Verify Services Are Running
```bash
# Check all Docker containers
docker-compose ps

# Should show:
# - orchestrator-worker: Up
# - web: Up (if you have it)

# Test orchestrator health
curl http://localhost:8001/health
# Should return: {"status":"healthy",...}

# Test web service
curl http://localhost:5000
# Should return: 200 OK
```

### 7. Check Notion API Server (Port 8200)
```bash
# Check if running
lsof -i :8200

# If not running, start it:
cd /opt/ChatStack/.notion_backup_replit
node notion-api-server.js &

# Or with PM2 (if installed):
pm2 start notion-api-server.js
pm2 save
```

### 8. Check SMS Service (Port 3000)
```bash
# Check if running
lsof -i :3000

# If not running, check tmux session:
tmux ls

# Attach to sendtext session:
tmux attach -t sendtext

# If session doesn't exist, start it:
cd /root/neurosphere_send_text
source /opt/ChatStack/.env  # Load environment variables
tmux new -s sendtext -d "python3 send_text.py"
```

### 9. Run Health Check Script
```bash
# Download and run the health check
cd /opt/ChatStack
chmod +x server-health-check.sh
./server-health-check.sh

# This will verify:
# ✅ Docker services
# ✅ Orchestrator (port 8001)
# ✅ Web service (port 5000)
# ✅ Notion API (port 8200)
# ✅ SMS service (port 3000)
# ✅ AI-Memory connection
# ✅ Database
# ✅ Environment variables
# ✅ Nginx
```

### 10. Monitor Logs
```bash
# Watch orchestrator logs in real-time
docker-compose logs -f orchestrator-worker

# You should see:
# ✅ "Connected to AI-Memory service"
# ✅ "Configuration reloaded"
# ✅ "Calls directory ready"

# Press Ctrl+C to exit
```

---

## 🧪 Test the System

### Make a Test Call
1. **Call your Twilio number** from a phone that's called before
2. **Watch the logs** for these new messages:
   ```
   🧠 Sending 20 previous messages to OpenAI for context
   ✅ Loaded 20 previous messages into AI context
   ```
3. **Verify the AI remembers** previous conversations
4. **Check Notion** for the call entry with:
   - Call SID
   - Full transcript
   - Brief summary
   - Status: New
   - Assigned Agent: Unassigned
   - Transcript URL
   - Audio URL

### Check Transcript Retrieval
```bash
# After a call ends, check the logs for:
docker-compose logs orchestrator-worker | grep "Retrieved.*messages from AI-Memory"

# Should show:
# ✅ Retrieved XXX messages from AI-Memory
# (NOT: ⚠️ AI-Memory retrieval failed)
```

---

## 🔧 Troubleshooting

### If Orchestrator Won't Start
```bash
# Check logs for errors
docker-compose logs orchestrator-worker | tail -50

# Restart with fresh build
docker-compose down
docker-compose up -d --build
```

### If Notion Integration Fails
```bash
# Check Notion API server
curl http://localhost:8200/health

# Check environment variable
grep NOTION_TOKEN /opt/ChatStack/.env

# Restart Notion server
cd /opt/ChatStack/.notion_backup_replit
pm2 restart notion-api-server
# Or:
pkill -f "node notion-api-server"
node notion-api-server.js &
```

### If SMS Not Sending
```bash
# Check send_text service
tmux attach -t sendtext
# (Press Ctrl+B then D to detach)

# Check environment variables are loaded
ps aux | grep send_text.py
cat /proc/$(pgrep -f send_text.py)/environ | tr '\0' '\n' | grep TWILIO
```

### If AI Doesn't Remember Previous Calls
```bash
# Check if thread history is being loaded
docker-compose logs orchestrator-worker | grep "Loaded thread history"

# Should show:
# 🔄 Loaded thread history for user_XXX: X messages

# Check AI-Memory connection
curl http://209.38.143.71:8100/health
```

---

## 📊 Service Ports Reference

| Service | Port | Check Command |
|---------|------|---------------|
| Orchestrator (FastAPI) | 8001 | `curl localhost:8001/health` |
| Web (Flask) | 5000 | `curl localhost:5000` |
| Notion API | 8200 | `curl localhost:8200/health` |
| SMS Service | 3000 | `lsof -i :3000` |
| AI-Memory (External) | 8100 | `curl http://209.38.143.71:8100/health` |
| Nginx (HTTPS) | 443 | `systemctl status nginx` |

---

## ✅ Success Indicators

After deployment, you should see:

- ✅ All Docker containers running
- ✅ Orchestrator health check passes
- ✅ Notion API responding on port 8200
- ✅ SMS service running on port 3000
- ✅ AI-Memory service reachable
- ✅ Nginx serving HTTPS traffic
- ✅ Test call completes successfully
- ✅ Notion shows new call entry
- ✅ SMS notification received
- ✅ AI references previous conversations

---

## 🆘 Quick Rollback (If Needed)

If something breaks after deployment:

```bash
cd /opt/ChatStack

# Go back to previous commit
git log --oneline -5  # Find the previous commit hash
git checkout <previous-commit-hash>

# Rebuild
docker-compose up -d --build orchestrator-worker

# Or restore from backup
# (Make sure you have backups configured!)
```
