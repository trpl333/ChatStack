#!/bin/bash
# Complete Pacific Time Tool Installation
# Run on DigitalOcean server: bash install_pacific_time_tool.sh

cd /opt/ChatStack

echo "🕐 Installing Pacific Time Tool for AI Agent..."

# Step 1: Restore clean tools.py from Git
echo "📦 Restoring clean base file..."
git checkout app/tools.py

# Step 2: Add zoneinfo import
echo "1️⃣ Adding timezone import..."
sed -i '/from datetime import datetime/a from zoneinfo import ZoneInfo' app/tools.py

# Step 3: Add tool schema to TOOL_SCHEMAS
echo "2️⃣ Adding tool schema..."
# Find line with closing } of text_to_speech and add get_current_time before final }
python3 << 'PYTHON'
with open('app/tools.py', 'r') as f:
    content = f.read()

# Add get_current_time tool before closing } of TOOL_SCHEMAS
tool_schema = '''    },
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
}'''

# Replace the closing } of TOOL_SCHEMAS (after text_to_speech)
import re
content = re.sub(
    r'(\s+\}\s+\}\s*\n)(\}\s*\n\nclass ToolDispatcher)',
    tool_schema + '\n\nclass ToolDispatcher',
    content,
    count=1
)

with open('app/tools.py', 'w') as f:
    f.write(content)
print("✅ Tool schema added")
PYTHON

# Step 4: Add dispatcher routing
echo "3️⃣ Adding dispatcher routing..."
python3 << 'PYTHON'
with open('app/tools.py', 'r') as f:
    content = f.read()

# Add dispatcher after text_to_speech
content = content.replace(
    '            elif tool_name == "text_to_speech":\n                return self._text_to_speech(parameters)',
    '            elif tool_name == "text_to_speech":\n                return self._text_to_speech(parameters)\n            elif tool_name == "get_current_time":\n                return self._get_current_time(parameters)'
)

with open('app/tools.py', 'w') as f:
    f.write(content)
print("✅ Dispatcher routing added")
PYTHON

# Step 5: Add implementation function
echo "4️⃣ Adding implementation..."
python3 << 'PYTHON'
with open('app/tools.py', 'r') as f:
    content = f.read()

impl = '''
    def _get_current_time(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get current time in Pacific Time Zone."""
        time_format = params.get("format", "12-hour")
        pacific_tz = ZoneInfo("America/Los_Angeles")
        now = datetime.now(pacific_tz)
        
        if time_format == "24-hour":
            time_str = now.strftime("%H:%M")
            formatted_time = f"{time_str} PT"
        else:
            time_str = now.strftime("%I:%M %p")
            formatted_time = f"{time_str} PT"
        
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
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
'''

# Add before get_available_tools
content = content.replace(
    '    def get_available_tools(self)',
    impl + '\n    def get_available_tools(self)'
)

with open('app/tools.py', 'w') as f:
    f.write(content)
print("✅ Implementation added")
PYTHON

# Step 6: Verify syntax
echo "5️⃣ Verifying Python syntax..."
python3 -m py_compile app/tools.py && echo "✅ Syntax OK" || (echo "❌ Syntax error!" && exit 1)

# Step 7: Restart orchestrator
echo "6️⃣ Restarting orchestrator..."
docker-compose restart orchestrator-worker

# Step 8: Wait and test
sleep 5

echo ""
echo "7️⃣ Testing the tool..."
curl -X POST http://localhost:8001/v1/tools/get_current_time \
  -H "Content-Type: application/json" \
  -d '{"format": "12-hour"}' 2>/dev/null | jq '.'

echo ""
echo "================================================"
echo "✅ Pacific Time Tool Installation Complete!"
echo "================================================"
echo ""
echo "📞 Test it: Call your Twilio number and ask 'What time is it?'"
echo "🎯 The AI will respond with accurate Pacific time!"
echo ""
