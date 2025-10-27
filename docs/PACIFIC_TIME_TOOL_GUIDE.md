# Pacific Time Tool for AI Agent

## ✅ What's Been Added

Your AI agent can now tell callers the accurate **Pacific Time** (PT) whenever they ask! The tool automatically handles:
- ⏰ Current time in 12-hour or 24-hour format
- 📅 Day of the week and full date
- 🌍 PST (Pacific Standard Time) vs PDT (Pacific Daylight Time)
- 🎯 Always accurate - pulls real-time from system clock

## 🚀 How It Works

When a caller asks:
- "What time is it?"
- "Can you tell me the time?"
- "What's the current time?"

The AI will:
1. Call the `get_current_time` tool
2. Get Pacific timezone time
3. Respond naturally with the time, day, and date

**Example Response:**
> "It's 2:45 PM PT (PDT) on Monday, October 14, 2025"

## 📋 Deployment Instructions

**On your DigitalOcean server:**

```bash
cd /opt/ChatStack

# Pull the latest code with Pacific time tool
git pull origin main

# Restart the orchestrator to load the new tool
docker-compose restart orchestrator-worker

# Verify it's running
docker-compose ps

# Check logs to confirm tool is loaded
docker logs chatstack-orchestrator-worker-1 --tail 50
```

## 🧪 Testing

**Test the tool via API:**

```bash
# Test the tool directly
curl -X POST http://localhost:8001/v1/tools/get_current_time \
  -H "Content-Type: application/json" \
  -d '{"format": "12-hour"}'
```

**Expected Response:**
```json
{
  "success": true,
  "result": "🕐 The current time is 02:45 PM PT (PDT) on Monday, October 14, 2025",
  "time": "02:45 PM PT",
  "day": "Monday",
  "date": "October 14, 2025",
  "timezone": "PDT",
  "timestamp": "2025-10-14T14:45:30.123456-07:00"
}
```

**Test via phone call:**
1. Call your Twilio number: `+1 (949) 556-5377`
2. Ask the AI: "What time is it?"
3. The AI should respond with the current Pacific time

## 🔧 Technical Details

### Tool Schema
- **Name:** `get_current_time`
- **Description:** Get the current time in Pacific Time Zone (PT)
- **Parameters:**
  - `format` (optional): "12-hour" (default) or "24-hour"
- **Returns:**
  - Formatted time string
  - Day of week
  - Full date
  - Timezone (PST/PDT)
  - ISO timestamp

### Files Modified
1. **`app/tools.py`** - Added tool implementation
   - Imports `ZoneInfo` for timezone handling
   - New tool schema in `TOOL_SCHEMAS`
   - Handler: `_get_current_time()`
   - Dispatcher routing added

2. **`app/prompts/system_sam.txt`** - Updated system prompt
   - AI now knows about the time tool
   - Instructions on when to use it

## 🎯 Why Pacific Time?

Your agency is based in California, and most of your clients are in the Pacific timezone. The tool:
- Uses `America/Los_Angeles` timezone data
- Automatically switches between PST (winter) and PDT (summer)
- Always shows current time even during daylight saving changes

## 📝 Usage Notes

**The AI will automatically use this tool when appropriate:**
- No manual intervention needed
- Works 24/7 with accurate time
- Handles PST/PDT transitions automatically
- Natural language responses

**Supported formats:**
- 12-hour: "02:45 PM PT"
- 24-hour: "14:45 PT"

## 🔍 Troubleshooting

**If the AI doesn't respond with time:**

1. Check if tool is loaded:
```bash
curl http://localhost:8001/v1/tools | jq '.tools[] | select(.name=="get_current_time")'
```

2. Check orchestrator logs:
```bash
docker logs chatstack-orchestrator-worker-1 --tail 100 | grep -i "time\|tool"
```

3. Verify system prompt includes the tool:
```bash
cat app/prompts/system_sam.txt | grep -A 5 "get_current_time"
```

**If time is incorrect:**
- The tool uses the server's system time
- Verify server timezone: `timedatectl`
- Should be set to America/Los_Angeles or UTC (tool converts to PT)

## 🎉 Benefits

✅ **Always Accurate** - Real-time clock, not hardcoded  
✅ **Timezone Aware** - Handles PST/PDT automatically  
✅ **Natural Responses** - AI speaks conversationally about time  
✅ **No User Input Needed** - Works automatically when asked  
✅ **Date Included** - Provides full context (day, date, time)

Your AI agent is now even more helpful! 🚀
