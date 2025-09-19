#!/usr/bin/env python3
"""
OpenAI Realtime WebSocket Server for ChatStack
"""

import asyncio
import websockets
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import OpenAI Realtime handler
from openai_realtime_integration import OpenAIRealtimeHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("openai_realtime_server")

# Initialize OpenAI Realtime handler
realtime_handler = OpenAIRealtimeHandler(
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-realtime",
    voice="marin"
)

async def handler(websocket, path):
    """Handle WebSocket connections"""
    logger.info(f"New connection from {websocket.remote_address}")
    await realtime_handler.handle_connection(websocket)

async def main():
    """Run the WebSocket server"""
    # Get server configuration from environment variables or use defaults
    host = os.environ.get("OPENAI_REALTIME_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("OPENAI_REALTIME_SERVER_PORT", 9101))
    
    logger.info(f"Starting OpenAI Realtime WebSocket server on {host}:{port}")
    
    # Start WebSocket server
    async with websockets.serve(handler, host, port):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")