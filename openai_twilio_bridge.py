"""
Bridge between Twilio Media Streams and OpenAI Realtime API
"""

import json
import base64
import asyncio
import websockets
import logging
import threading
from queue import Queue
import time
from typing import Dict, Any

# Import our OpenAI Realtime client
from openai_realtime import OpenAIRealtimeClient

class TwilioOpenAIBridge:
    """Handle Twilio Media Stream WebSocket connections and bridge to OpenAI Realtime"""
    
    def __init__(self, openai_api_key=None):
        self.active_connections: Dict[str, Dict] = {}
        self.openai_clients: Dict[str, OpenAIRealtimeClient] = {}
        self.audio_queues: Dict[str, Queue] = {}
        self.openai_api_key = openai_api_key
        
    async def handle_connection(self, websocket):
        """Handle incoming Twilio Media Stream WebSocket connection"""
        connection_id = f"conn_{int(time.time())}"
        logging.info(f"🔌 New Twilio Media Stream connection: {connection_id}")
        
        # Initialize connection data
        self.active_connections[connection_id] = {
            'websocket': websocket,
            'call_sid': None,
            'stream_sid': None,
            'conversation_state': 'listening',
        }
        self.audio_queues[connection_id] = Queue()
        
        # Create OpenAI Realtime client for this connection
        def on_transcript(text, is_final):
            if is_final and connection_id in self.active_connections:
                logging.info(f"Transcript: {text}")
                
        def on_response(audio_bytes):
            if connection_id in self.active_connections:
                # Queue audio to be sent back to Twilio
                asyncio.create_task(self._send_audio_to_twilio(connection_id, audio_bytes))
                
        self.openai_clients[connection_id] = OpenAIRealtimeClient(
            api_key=self.openai_api_key,
            on_transcript_callback=on_transcript,
            on_response_callback=on_response
        )
        
        try:
            # Start OpenAI Realtime client connection
            self.openai_clients[connection_id].start_conversation(
                initial_instructions="You are a helpful AI assistant for phone calls. Respond clearly and concisely."
            )
            
            # Handle incoming WebSocket messages
            async for message in websocket:
                await self._handle_message(connection_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"📞 Connection {connection_id} closed")
        except Exception as e:
            logging.error(f"❌ WebSocket error for {connection_id}: {e}")
        finally:
            # Cleanup connection
            if connection_id in self.openai_clients:
                self.openai_clients[connection_id].close()
                del self.openai_clients[connection_id]
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            if connection_id in self.audio_queues:
                del self.audio_queues[connection_id]
    
    async def _handle_message(self, connection_id: str, message: str):
        """Process incoming Twilio Media Stream messages"""
        try:
            data = json.loads(message)
            event = data.get('event')
            
            conn = self.active_connections[connection_id]
            
            if event == 'connected':
                logging.info(f"🎵 Media stream connected: {connection_id}")
                
            elif event == 'start':
                # Store stream and call identifiers
                conn['call_sid'] = data['start']['callSid']
                conn['stream_sid'] = data['start']['streamSid']
                logging.info(f"🚀 Stream started - Call: {conn['call_sid']}, Stream: {conn['stream_sid']}")
                
                # Send initial greeting via OpenAI
                # No need to explicitly send a greeting as OpenAI will respond when audio is sent
                
            elif event == 'media':
                # Incoming audio data from caller
                payload = data['media']['payload']
                audio_data = base64.b64decode(payload)
                
                # Forward to OpenAI Realtime API
                if connection_id in self.openai_clients:
                    # Convert Twilio's mulaw audio to PCM if needed
                    # For simplicity, this example assumes OpenAI can handle the audio format directly
                    # In a real implementation, you might need to convert the audio format
                    self.openai_clients[connection_id].send_audio(audio_data)
                
            elif event == 'stop':
                logging.info(f"🔌 Stream stopped: {connection_id}")
                if connection_id in self.openai_clients:
                    self.openai_clients[connection_id].close()
                
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON received: {message[:100]}")
        except Exception as e:
            logging.error(f"Message handling error: {e}")
    
    async def _send_audio_to_twilio(self, connection_id: str, audio_bytes: bytes):
        """Send audio bytes back to Twilio via WebSocket"""
        if connection_id not in self.active_connections:
            return
            
        try:
            conn = self.active_connections[connection_id]
            websocket = conn['websocket']
            
            # Convert PCM audio to base64 for Twilio
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Create Media message for Twilio
            twilio_msg = {
                "event": "media",
                "streamSid": conn['stream_sid'],
                "media": {
                    "payload": audio_b64
                }
            }
            
            # Send to WebSocket
            await websocket.send(json.dumps(twilio_msg))
            
        except Exception as e:
            logging.error(f"Error sending audio to Twilio: {e}")