#!/usr/bin/env python3
"""
Example usage of OpenAI Realtime API with WebSockets
"""

import os
import time
import logging
import threading
from openai_realtime import OpenAIRealtimeClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("openai-realtime-example")

def on_transcript(text, is_final):
    """Callback for transcript events"""
    if is_final:
        logger.info(f"Final transcript: {text}")
    else:
        logger.info(f"Partial transcript: {text}")
    
def on_response(audio_data):
    """Callback for audio response data"""
    # In a real application, you might play this audio or save it
    logger.info(f"Received {len(audio_data)} bytes of audio")
    
def main():
    # Create the OpenAI Realtime client
    client = OpenAIRealtimeClient(
        on_transcript_callback=on_transcript,
        on_response_callback=on_response
    )
    
    # Connect and start conversation
    client.start_conversation(
        initial_instructions="You are a helpful AI assistant. Answer questions clearly and concisely."
    )
    
    # Wait for connection to establish
    time.sleep(2)
    
    # Test sending some audio (simulated here)
    # In a real application, you'd capture audio from a microphone
    sample_audio = bytes([0] * 4800)  # 0.2 seconds of silence at 24kHz
    logger.info("Sending test audio data...")
    client.send_audio(sample_audio)
    
    # Keep the application running for demonstration
    try:
        logger.info("Press Ctrl+C to exit...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        client.close()
        
if __name__ == "__main__":
    main()