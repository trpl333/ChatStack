#!/usr/bin/env python3
"""
WebSocket server that bridges Twilio Media Streams with OpenAI Realtime API
"""

import asyncio
import websockets
import logging
import os
import sys
from dotenv import load_dotenv

# Add current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the bridge
from openai_twilio_bridge import TwilioOpenAIBridge

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("openai-twilio-server")

# Get OpenAI API key
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("OPENAI_API_KEY environment variable not set")
    sys.exit(1)

# Create the bridge
bridge = TwilioOpenAIBridge(openai_api_key=openai_api_key)

async def main():
    # Start WebSocket server
    host = "0.0.0.0"  # Listen on all interfaces
    port = int(os.environ.get("WEBSOCKET_PORT", "9100"))
    
    logger.info(f"Starting WebSocket server on {host}:{port}")
    
    async with websockets.serve(bridge.handle_connection, host, port):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutting down")