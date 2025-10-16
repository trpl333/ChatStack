#!/bin/bash
# Check what DigitalOcean production is actually using for greetings and agent_name

echo "=== Checking DigitalOcean Production Logs ==="
echo ""

# SSH to DigitalOcean and check recent call logs
ssh root@209.38.143.71 << 'ENDSSH'

echo "1️⃣ Checking orchestrator logs for agent_name retrieval:"
docker logs chatstack-orchestrator-worker-1 --tail 100 2>&1 | grep -i "agent_name\|greeting\|barbara\|samantha" | tail -20

echo ""
echo "2️⃣ Checking web (Flask) logs for greeting generation:"
docker logs chatstack-web-1 --tail 100 2>&1 | grep -i "greeting\|agent_name\|barbara\|samantha" | tail -20

echo ""
echo "3️⃣ Check what greetings are currently stored in AI-Memory:"
curl -s -X POST http://172.17.0.1:8100/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{"user_id":"admin","key":"admin:new_caller_greeting"}' \
  | grep -o '"value":"[^"]*"' | head -1

echo ""
echo "4️⃣ Check agent_name in AI-Memory:"
curl -s -X POST http://172.17.0.1:8100/memory/retrieve \
  -H "Content-Type: application/json" \
  -d '{"user_id":"admin","key":"admin:agent_name"}' \
  | grep -o '"value":"[^"]*"' | head -1

echo ""
echo "5️⃣ Check git status (to see if code is up to date):"
cd /opt/ChatStack
git status | head -5
git log --oneline | head -3

ENDSSH

echo ""
echo "=== End of Production Check ==="
