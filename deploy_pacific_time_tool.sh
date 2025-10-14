#!/bin/bash

echo "🕐 Deploying Pacific Time Tool..."
echo ""

# Backup existing files
echo "📦 Backing up existing files..."
cp app/tools.py app/tools.py.backup.$(date +%Y%m%d_%H%M%S)
cp app/prompts/system_sam.txt app/prompts/system_sam.txt.backup.$(date +%Y%m%d_%H%M%S)

# Update tools.py - add zoneinfo import
echo "1️⃣ Updating app/tools.py imports..."
sed -i '4 a from zoneinfo import ZoneInfo' app/tools.py

# Add get_current_time to tool schemas (insert before closing brace of TOOL_SCHEMAS)
echo "2️⃣ Adding get_current_time tool schema..."
cat >> /tmp/time_tool_schema.txt << 'SCHEMA'
    },
    "get_current_time": {
        "description": "Get the current time in Pacific Time Zone (PT). Use this when someone asks what time it is.",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Time format to return",
                    "enum": ["12-hour", "24-hour"],
                    "default": "12-hour"
                }
            },
            "required": []
        }
    }
}
SCHEMA

# Replace the last } of TOOL_SCHEMAS with the new tool
sed -i '/^}$/,/^}$/{
  /^}$/{
    r /tmp/time_tool_schema.txt
    d
  }
}' app/tools.py

# Add dispatcher routing
echo "3️⃣ Adding tool dispatcher routing..."
sed -i '/elif tool_name == "text_to_speech":/a\            elif tool_name == "get_current_time":\n                return self._get_current_time(parameters)' app/tools.py

# Add the implementation function (after _text_to_speech method)
echo "4️⃣ Adding tool implementation..."
cat >> /tmp/time_tool_impl.txt << 'IMPL'
    
    def _get_current_time(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the current time in Pacific Time Zone.
        
        Args:
            params: Time parameters (format option)
            
        Returns:
            Current time result
        """
        time_format = params.get("format", "12-hour")
        
        # Get current Pacific time
        pacific_tz = ZoneInfo("America/Los_Angeles")
        now = datetime.now(pacific_tz)
        
        # Format the time
        if time_format == "24-hour":
            time_str = now.strftime("%H:%M")
            formatted_time = f"{time_str} PT"
        else:
            time_str = now.strftime("%I:%M %p")
            formatted_time = f"{time_str} PT"
        
        # Get day of week and date
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        
        # Determine PST or PDT
        dst_offset = now.dst()
        timezone_name = "PST" if dst_offset is None or dst_offset.total_seconds() == 0 else "PDT"
        
        result = f"🕐 The current time is {formatted_time} ({timezone_name}) on {day_name}, {date_str}"
        
        logger.info(f"Current Pacific time requested: {formatted_time}")
        
        return {
            "success": True,
            "result": result,
            "error": None,
            "time": formatted_time,
            "day": day_name,
            "date": date_str,
            "timezone": timezone_name,
            "timestamp": now.isoformat()
        }
IMPL

# Insert before get_available_tools method
sed -i '/def get_available_tools/i\'"$(cat /tmp/time_tool_impl.txt)" app/tools.py

# Update system prompt
echo "5️⃣ Updating system prompt..."
sed -i '/^Tool Usage:$/,/^$/c\
Tool Usage:\
You have access to helpful tools during conversations. Use them when appropriate:\
\
Available Tools:\
1. get_current_time - Get the current time in Pacific Time Zone (PT)\
   - Use when someone asks "what time is it?" or about the current time\
   - Automatically handles PST/PDT (Pacific Standard/Daylight Time)\
   - Returns time with day and date\
\
2. book_meeting - Schedule meetings or calendar events\
3. send_message - Send SMS or messages\
4. search_knowledge - Search internal knowledge base\
\
Tool Usage Guidelines:\
- Proactively suggest relevant tools when they would be helpful\
- When someone asks the time, use get_current_time to give them accurate Pacific time\
- Explain what tools will do before using them\
- Provide clear summaries of tool results\
- Offer alternatives if tools aren'\''t available\
' app/prompts/system_sam.txt

# Restart orchestrator
echo ""
echo "6️⃣ Restarting orchestrator..."
docker-compose restart orchestrator-worker

# Wait for restart
sleep 3

# Test the tool
echo ""
echo "7️⃣ Testing the tool..."
curl -X POST http://localhost:8001/v1/tools/get_current_time \
  -H "Content-Type: application/json" \
  -d '{"format": "12-hour"}' 2>/dev/null | jq '.'

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📞 Test by calling your Twilio number and asking 'What time is it?'"
