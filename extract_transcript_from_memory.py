#!/usr/bin/env python3
"""
Extract call transcript from AI-Memory service and save to calls directory.
Usage: python3 extract_transcript_from_memory.py <call_sid> <phone_number>
Example: python3 extract_transcript_from_memory.py CA1711dafdebd8d0e5a1a678db73545d15 9493342332
"""

import sys
import json
import requests
from datetime import datetime

def extract_and_save_transcript(call_sid, phone_number):
    """Extract transcript from AI-Memory and save to calls directory"""
    
    # Query AI-Memory service
    print(f"🔍 Querying AI-Memory for call {call_sid}...")
    
    response = requests.post(
        "http://209.38.143.71:8100/memory/retrieve",
        headers={"Content-Type": "application/json"},
        json={
            "user_id": phone_number,
            "message": f"thread_history {call_sid}",
            "limit": 500,
            "types": ["thread_history"]
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to retrieve memory: {response.status_code}")
        return False
    
    # Parse response
    data = response.json()
    memory_content = data.get("memory", "")
    
    if not memory_content:
        print(f"❌ No memory found for call {call_sid}")
        return False
    
    # Parse the memory content (it's a JSON string containing messages)
    try:
        memory_data = json.loads(memory_content)
        messages = memory_data.get("messages", [])
    except json.JSONDecodeError:
        print(f"❌ Failed to parse memory content")
        return False
    
    if not messages:
        print(f"❌ No messages found in memory")
        return False
    
    print(f"✅ Found {len(messages)} messages")
    
    # Format transcript
    transcript_lines = []
    transcript_lines.append(f"Call SID: {call_sid}")
    transcript_lines.append(f"Phone Number: +1{phone_number}")
    transcript_lines.append(f"Retrieved: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    transcript_lines.append("=" * 80)
    transcript_lines.append("")
    
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        
        if role == "ASSISTANT":
            transcript_lines.append(f"AI: {content}")
        elif role == "USER":
            transcript_lines.append(f"CALLER: {content}")
        else:
            transcript_lines.append(f"{role}: {content}")
        transcript_lines.append("")
    
    transcript_text = "\n".join(transcript_lines)
    
    # Save to file
    output_path = f"/opt/ChatStack/static/calls/{call_sid}.txt"
    
    try:
        with open(output_path, 'w') as f:
            f.write(transcript_text)
        print(f"✅ Transcript saved to: {output_path}")
        print(f"📄 File size: {len(transcript_text)} bytes")
        print(f"🌐 Access at: https://voice.theinsurancedoctors.com/calls/{call_sid}.txt")
        return True
    except Exception as e:
        print(f"❌ Failed to save file: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 extract_transcript_from_memory.py <call_sid> <phone_number>")
        print("Example: python3 extract_transcript_from_memory.py CA1711dafdebd8d0e5a1a678db73545d15 9493342332")
        sys.exit(1)
    
    call_sid = sys.argv[1]
    phone_number = sys.argv[2].replace("+1", "").replace("+", "")
    
    success = extract_and_save_transcript(call_sid, phone_number)
    sys.exit(0 if success else 1)
