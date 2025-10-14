# Configure Twilio Phone Number (805) 265-4625

## Step-by-Step Setup

### 1. Log in to Twilio Console
Go to: https://console.twilio.com/

### 2. Find Your Phone Number
- Click **Phone Numbers** → **Manage** → **Active Numbers**
- Click on **(805) 265-4625**

### 3. Configure Voice Webhooks

**When a call comes in:**
- Select: **Webhook**
- URL: `https://neurospherevoice.com/twilio-webhook`
- HTTP Method: **POST**

**Call Status Updates (optional but recommended):**
- URL: `https://neurospherevoice.com/twilio-status`
- HTTP Method: **POST**

### 4. Configure Messaging (optional)
If you want SMS support:

**When a message comes in:**
- URL: `https://neurospherevoice.com/twilio-sms`
- HTTP Method: **POST**

### 5. Save Configuration
Click **Save** at the bottom of the page.

## Test Your Phone Number

### Call the number:
```
(805) 265-4625
```

**Expected behavior:**
1. ✅ Call connects
2. ✅ AI greeting plays: "Hi, this is Samantha from Peterson Family Insurance..."
3. ✅ AI responds to your questions
4. ✅ 2-2.5 second response time

## Troubleshooting

### If call doesn't connect:
```bash
# Check Twilio webhook logs
https://console.twilio.com/monitor/logs/debugger

# Check Docker logs on server
ssh root@209.38.143.71
docker logs chatstack-web-1 --tail 100
```

### If AI doesn't respond:
```bash
# Check orchestrator logs
ssh root@209.38.143.71
docker logs chatstack-orchestrator-1 --tail 100
```

## Quick Test Commands

```bash
# Test webhook locally on server
curl http://localhost:5000/twilio-webhook \
  -X POST \
  -d "From=%2B18052654625&CallSid=TEST123"

# Test from internet
curl https://neurospherevoice.com/twilio-webhook \
  -X POST \
  -d "From=%2B18052654625&CallSid=TEST123"
```

## Important Notes

- **Webhook URL must be HTTPS** (already configured with SSL)
- **Nginx is proxying** requests to Flask on port 5000
- **FastAPI orchestrator** runs on port 8001 (internal)
- **AI-Memory service** at http://209.38.143.71:8100 (external)

## Your Twilio Configuration Summary

| Setting | Value |
|---------|-------|
| Phone Number | (805) 265-4625 |
| Voice Webhook | https://neurospherevoice.com/twilio-webhook |
| Method | POST |
| Status Callback | https://neurospherevoice.com/twilio-status |
| Server | DigitalOcean 209.38.143.71 |
| SSL | ✅ Let's Encrypt |
