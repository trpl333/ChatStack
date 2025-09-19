"""
OpenAI Realtime API Integration for ChatStack
Integrates with existing architecture for real-time voice AI
"""

import os
import json
import logging
import websocket
import threading
import time
import base64
from queue import Queue

from openai_realtime import OpenAIRealtimeClient

logger = logging.getLogger("chatstack.openai_realtime")

class OpenAIRealtimeHandler:
    """Handler for OpenAI Realtime API integration with ChatStack"""
    
    def __init__(self, api_key=None, model="gpt-realtime", voice="marin"):
        """Initialize the handler"""
        self.client = OpenAIRealtimeClient(api_key=api_key, model=model, voice=voice)
        self.active_connections = {}
        self.audio_queues = {}
        
    async def handle_connection(self, websocket):
        """Handle an incoming WebSocket connection"""
        connection_id = f"conn_{int(time.time())}"
        logger.info(f"🔌 New connection: {connection_id}")
        
        # Initialize connection data
        self.active_connections[connection_id] = {
            'websocket': websocket,
            'call_sid': None,
            'openai_client': None,
            'conversation_state': 'listening',
            'partial_transcript': '',
            'response_in_progress': False
        }
        self.audio_queues[connection_id] = Queue()
        
        try:
            # Create OpenAI Realtime client for this connection
            self.active_connections[connection_id]['openai_client'] = self.client
            
            # Start audio processing thread
            audio_thread = threading.Thread(
                target=self._process_audio_stream, 
                args=(connection_id,),
                daemon=True
            )
            audio_thread.start()
            
            # Handle incoming WebSocket messages
            async for message in websocket:
                await self._handle_message(connection_id, message)
                
        except Exception as e:
            logger.error(f"❌ WebSocket error: {e}")
        finally:
            # Clean up connection
            if connection_id in self.active_connections:
                # Disconnect OpenAI client
                if self.active_connections[connection_id]['openai_client']:
                    self.active_connections[connection_id]['openai_client'].disconnect()
                del self.active_connections[connection_id]
            if connection_id in self.audio_queues:
                del self.audio_queues[connection_id]
    
    async def _handle_message(self, connection_id, message):
        """Process incoming WebSocket messages"""
        try:
            data = json.loads(message)
            event = data.get('event')
            
            conn = self.active_connections[connection_id]
            
            if event == 'connected':
                logger.info(f"🎵 Media stream connected: {connection_id}")
                
            elif event == 'start':
                # Store call identifier
                conn['call_sid'] = data['start'].get('callSid')
                logger.info(f"🚀 Stream started - Call: {conn['call_sid']}")
                
                # Initialize OpenAI Realtime session
                await self._initialize_openai_session(connection_id)
                
            elif event == 'media':
                # Incoming audio from caller
                payload = data['media']['payload']
                audio_data = base64.b64decode(payload)
                
                # Add to processing queue
                self.audio_queues[connection_id].put(audio_data)
                
            elif event == 'stop':
                logger.info(f"🔌 Stream stopped: {connection_id}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message[:100]}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    async def _initialize_openai_session(self, connection_id):
        """Initialize OpenAI Realtime session for this connection"""
        conn = self.active_connections[connection_id]
        client = conn['openai_client']
        
        # Define message handler for this connection
        def on_message(data):
            # Handle audio responses
            if data.get("type") == "audio.data" and "data" in data:
                audio_bytes = base64.b64decode(data["data"])
                # Queue audio response to be sent back to caller
                threading.Thread(
                    target=self._send_audio_response,
                    args=(connection_id, audio_bytes),
                    daemon=True
                ).start()
        
        # Connect to OpenAI
        if not client.connect(on_message=on_message):
            logger.error(f"Failed to connect to OpenAI Realtime API for {connection_id}")
            return
        
        # Configure session
        client.update_session(
            instructions="""
            You are a helpful AI assistant for voice conversations.
            Be concise and friendly in your responses.
            Listen carefully to the user's questions and provide accurate answers.
            """,
            modalities=["audio", "text"]
        )
        
        # Send greeting message
        client.create_response(instructions="Introduce yourself briefly and ask how you can help.")
        
        logger.info(f"✅ OpenAI Realtime session initialized for {connection_id}")
    
    def _process_audio_stream(self, connection_id):
        """Process incoming audio from the queue"""
        while connection_id in self.active_connections:
            try:
                # Get audio from queue
                audio_data = self.audio_queues[connection_id].get(timeout=0.5)
                
                # Send to OpenAI Realtime API
                conn = self.active_connections[connection_id]
                client = conn['openai_client']
                if client and client.connected:
                    client.send_audio(audio_data)
                
            except Exception as e:
                # Queue.get timeout is expected
                if not str(e).startswith('Empty'):
                    logger.error(f"Audio processing error for {connection_id}: {e}")
    
    async def _send_audio_response(self, connection_id, audio_bytes):
        """Send audio response back to the client"""
        try:
            if connection_id not in self.active_connections:
                return
                
            conn = self.active_connections[connection_id]
            websocket = conn['websocket']
            
            # Convert to Twilio-compatible format (if needed)
            # Encode audio bytes to base64
            encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Create media message
            response = {
                "event": "media",
                "media": {
                    "payload": encoded_audio
                }
            }
            
            # Send response
            await websocket.send(json.dumps(response))
            
        except Exception as e:
            logger.error(f"Failed to send audio response: {e}")