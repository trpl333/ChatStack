#!/usr/bin/env python3
"""
Demo script for OpenAI Realtime API WebSocket integration
"""

import os
import time
import argparse
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our OpenAI Realtime client
from openai_realtime import OpenAIRealtimeClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("openai_realtime_demo")

def main():
    """Run the demo"""
    parser = argparse.ArgumentParser(description="OpenAI Realtime API WebSocket Demo")
    parser.add_argument("--model", default="gpt-realtime", help="Model to use")
    parser.add_argument("--voice", default="marin", help="Voice to use")
    parser.add_argument("--instructions", default="You are a helpful assistant named Alex. Be concise and friendly.", 
                        help="System instructions for the model")
    args = parser.parse_args()
    
    # Create client
    logger.info("Creating OpenAI Realtime client...")
    client = OpenAIRealtimeClient(model=args.model, voice=args.voice)
    
    # Define callbacks
    def on_message(data):
        event_type = data.get("type", "unknown")
        if event_type == "audio.data":
            # Audio data is handled by the client internally
            pass
        elif event_type == "speech.partial":
            logger.info(f"Partial transcription: {data.get('speech', {}).get('text', '')}")
        elif event_type == "speech.final":
            logger.info(f"Final transcription: {data.get('speech', {}).get('text', '')}")
        elif event_type == "message":
            logger.info(f"Message from {data.get('message', {}).get('role', '')}: {data.get('message', {}).get('content', '')}")
        else:
            logger.info(f"Received event: {event_type}")
    
    # Connect to the API
    logger.info("Connecting to OpenAI Realtime API...")
    if not client.connect(on_message=on_message):
        logger.error("Failed to connect")
        return
    
    # Update session with instructions
    logger.info("Updating session configuration...")
    client.update_session(
        instructions=args.instructions,
        modalities=["audio", "text"]
    )
    
    # Wait for session to be updated
    time.sleep(1)
    
    # Send a test message
    logger.info("Sending test message...")
    client.send_message("Hello! Can you tell me about the weather today?")
    
    # Wait for response
    time.sleep(1)
    
    # Request response
    logger.info("Requesting response...")
    client.create_response()
    
    # Wait for and print responses
    logger.info("Waiting for responses (30 seconds)...")
    start_time = time.time()
    while (time.time() - start_time) < 30:
        # Check for text responses
        text = client.get_next_text(timeout=0.1)
        if text:
            logger.info(f"Text response: {text}")
        
        # For audio responses in a real implementation,
        # you would process the audio chunks here
        
        # Small delay to prevent CPU spinning
        time.sleep(0.1)
    
    # Disconnect
    logger.info("Disconnecting...")
    client.disconnect()
    logger.info("Demo completed")

if __name__ == "__main__":
    main()