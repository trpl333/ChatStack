"""
OpenAI Realtime API Integration with WebSockets
Provides a client for connecting to OpenAI's Realtime API for voice conversations
"""

import os
import json
import logging
import asyncio
import threading
import base64
import websocket
from queue import Queue
from typing import Optional, Dict, Any, List, Callable
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("openai-realtime")

class OpenAIRealtimeClient:
    """Client for OpenAI's Realtime API using WebSockets"""
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 model: str = "gpt-realtime",
                 organization_id: Optional[str] = None,
                 project_id: Optional[str] = None,
                 on_transcript_callback: Optional[Callable] = None,
                 on_response_callback: Optional[Callable] = None):
        """Initialize the OpenAI Realtime client
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use (defaults to gpt-realtime)
            organization_id: OpenAI organization ID (optional)
            project_id: OpenAI project ID (optional)
            on_transcript_callback: Callback for transcript events
            on_response_callback: Callback for assistant response events
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY env var or pass as parameter.")
            
        self.model = model
        self.organization_id = organization_id or os.environ.get("OPENAI_ORG_ID")
        self.project_id = project_id or os.environ.get("OPENAI_PROJECT_ID")
        
        self.websocket = None
        self.ws_url = f"wss://api.openai.com/v1/realtime?model={model}"
        self.is_connected = False
        self.session_id = None
        
        # Callbacks
        self.on_transcript = on_transcript_callback
        self.on_response = on_response_callback
        
        # Queue for audio data processing
        self.audio_queue = Queue()
        self.response_audio_queue = Queue()
        self.ws_thread = None
        
    def connect(self):
        """Connect to the OpenAI Realtime API using WebSockets"""
        logger.info(f"Connecting to OpenAI Realtime API: {self.ws_url}")
        
        # Define WebSocket callbacks
        def on_open(ws):
            logger.info("Connected to OpenAI Realtime API")
            self.is_connected = True
            
            # Send initial session configuration
            self._send_session_update({
                "type": "realtime",
                "model": self.model,
                "output_modalities": ["audio", "text"],
                "audio": {
                    "input": {
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000,
                        },
                        "turn_detection": {
                            "type": "semantic_vad"
                        }
                    },
                    "output": {
                        "format": {
                            "type": "audio/pcm",
                        },
                        "voice": "shimmer",
                    }
                },
                "instructions": "You are a helpful AI assistant. Respond clearly and concisely."
            })

        def on_message(ws, message):
            try:
                data = json.loads(message)
                logger.debug(f"Received event: {data.get('type', 'unknown')}")
                
                # Handle different event types
                event_type = data.get('type')
                
                if event_type == 'session.created':
                    self.session_id = data.get('session', {}).get('id')
                    logger.info(f"Session created: {self.session_id}")
                    
                elif event_type == 'session.updated':
                    logger.info("Session updated successfully")
                    
                elif event_type == 'speech.started':
                    logger.info("Assistant speech started")
                    
                elif event_type == 'speech.partial':
                    if self.on_transcript:
                        text = data.get('speech', {}).get('text', '')
                        self.on_transcript(text, is_final=False)
                
                elif event_type == 'speech.final':
                    if self.on_transcript:
                        text = data.get('speech', {}).get('text', '')
                        self.on_transcript(text, is_final=True)
                
                elif event_type == 'audio.encoding':
                    # Handle audio encoding parameters
                    pass
                
                elif event_type == 'audio.frame':
                    # Process audio frame from the assistant
                    audio_data = data.get('audio', {}).get('data', '')
                    if audio_data:
                        audio_bytes = base64.b64decode(audio_data)
                        self.response_audio_queue.put(audio_bytes)
                        if self.on_response:
                            self.on_response(audio_bytes)
                
                elif event_type == 'error':
                    error = data.get('error', {})
                    logger.error(f"OpenAI Realtime API error: {error.get('message', 'Unknown error')}")
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from OpenAI Realtime API")
            except Exception as e:
                logger.error(f"Error processing message: {e}")

        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
            self.is_connected = False

        # Create WebSocket connection
        headers = ["Authorization: Bearer " + self.api_key]
        if self.organization_id:
            headers.append("OpenAI-Organization: " + self.organization_id)
        
        self.websocket = websocket.WebSocketApp(
            self.ws_url,
            header=headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Start WebSocket in a separate thread
        self.ws_thread = threading.Thread(target=self.websocket.run_forever, daemon=True)
        self.ws_thread.start()
        logger.info("WebSocket thread started")
        
    def _send_session_update(self, session_config: Dict[str, Any]):
        """Send a session update event to the Realtime API"""
        if not self.websocket:
            logger.error("Cannot update session: WebSocket not connected")
            return
            
        event = {
            "type": "session.update",
            "session": session_config
        }
        
        self.websocket.send(json.dumps(event))
        logger.info("Sent session update")
        
    def update_session(self, 
                      instructions: Optional[str] = None,
                      prompt_id: Optional[str] = None,
                      prompt_version: Optional[str] = None,
                      prompt_variables: Optional[Dict[str, Any]] = None,
                      output_modalities: Optional[List[str]] = None,
                      voice: Optional[str] = None):
        """Update the session with new parameters
        
        Args:
            instructions: New instructions for the model
            prompt_id: ID of a stored prompt to use
            prompt_version: Version of the stored prompt
            prompt_variables: Variables to pass to the prompt
            output_modalities: List of output modalities (e.g. ["audio", "text"])
            voice: Voice to use for audio output
        """
        session_config = {
            "type": "realtime"
        }
        
        if instructions:
            session_config["instructions"] = instructions
            
        if prompt_id:
            prompt_config = {"id": prompt_id}
            if prompt_version:
                prompt_config["version"] = prompt_version
            if prompt_variables:
                prompt_config["variables"] = prompt_variables
            session_config["prompt"] = prompt_config
            
        if output_modalities:
            session_config["output_modalities"] = output_modalities
            
        if voice:
            if not "audio" in session_config:
                session_config["audio"] = {}
            if not "output" in session_config["audio"]:
                session_config["audio"]["output"] = {}
            session_config["audio"]["output"]["voice"] = voice
            
        self._send_session_update(session_config)
        
    def send_audio(self, audio_data: bytes):
        """Send audio data to the Realtime API
        
        Args:
            audio_data: PCM audio bytes to send
        """
        if not self.websocket or not self.is_connected:
            logger.error("Cannot send audio: WebSocket not connected")
            return
        
        # Encode audio data as base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        # Send audio event
        event = {
            "type": "audio.frame",
            "audio": {
                "data": audio_base64
            }
        }
        
        self.websocket.send(json.dumps(event))
        
    def start_conversation(self, initial_instructions: str = None):
        """Start a conversation with the Realtime API
        
        Args:
            initial_instructions: Instructions for the model
        """
        if not self.is_connected:
            self.connect()
            
        # Wait for connection to establish
        retry_count = 0
        while not self.is_connected and retry_count < 5:
            logger.info("Waiting for connection...")
            retry_count += 1
            time.sleep(1)
            
        if not self.is_connected:
            logger.error("Failed to connect to OpenAI Realtime API")
            return False
            
        # Update session if initial instructions provided
        if initial_instructions:
            self.update_session(instructions=initial_instructions)
            
        return True
        
    def close(self):
        """Close the WebSocket connection"""
        if self.websocket:
            self.websocket.close()
            logger.info("WebSocket connection closed")
            
        # Wait for thread to terminate
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            
        self.is_connected = False
        self.websocket = None