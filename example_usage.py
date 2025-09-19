import time
import os
from openai_realtime import OpenAIRealtimeClient

# Initialize client
client = OpenAIRealtimeClient(api_key=os.environ.get("OPENAI_API_KEY"))

# Define messages
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Tell me about the benefits of voice AI assistants"}
]

# Stream response
print("Streaming response:")
response_text = ""

for token in client.stream(messages):
    print(token, end="", flush=True)
    response_text += token
    time.sleep(0.01)  # Simulate real-time display

print("\n\nFinal response:", response_text)