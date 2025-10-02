"""
OpenAI Realtime API WebSocket Bridge for Twilio Media Streams
Handles bidirectional audio streaming between Twilio and OpenAI Realtime API
"""
import os
import json
import base64
import audioop
import asyncio
import websockets
import logging
from typing import Optional, Dict, Any
from queue import Queue
from threading import Thread

logger = logging.getLogger(__name__)

# Audio format constants
TWILIO_SAMPLE_RATE = 8000  # 8kHz mulaw
OPENAI_SAMPLE_RATE = 24000  # 24kHz PCM16
CHUNK_SIZE = 160  # 20ms at 8kHz

class RealtimeBridge:
    """Bridge between Twilio Media Streams and OpenAI Realtime API"""
    
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.twilio_ws = None
        self.openai_ws = None
        self.stream_sid = None
        self.call_sid = None
        self.openai_session_id = None
        
        # Audio queues
        self.twilio_to_openai_queue = Queue()
        self.openai_to_twilio_queue = Queue()
        
        # Control flags
        self.is_connected = False
        self.should_stop = False
        
    async def connect_to_openai(self, system_instructions: str, voice: str = "alloy"):
        """Establish WebSocket connection to OpenAI Realtime API"""
        openai_url = f"wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        try:
            self.openai_ws = await websockets.connect(openai_url, extra_headers=headers)
            logger.info("✅ Connected to OpenAI Realtime API")
            
            # Send session configuration
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": system_instructions,
                    "voice": voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    },
                    "temperature": 0.7,
                    "max_response_output_tokens": 150
                }
            }
            
            await self.openai_ws.send(json.dumps(session_config))
            logger.info("📤 Sent session configuration to OpenAI")
            
            # Wait for session confirmation
            response = await self.openai_ws.recv()
            data = json.loads(response)
            if data.get("type") == "session.created":
                self.openai_session_id = data.get("session", {}).get("id")
                logger.info(f"✅ OpenAI session created: {self.openai_session_id}")
                self.is_connected = True
                return True
            else:
                logger.error(f"Unexpected response from OpenAI: {data}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            return False
    
    def convert_mulaw_to_pcm16(self, mulaw_data: bytes) -> bytes:
        """Convert Twilio's mulaw 8kHz audio to OpenAI's PCM16 24kHz"""
        try:
            # Step 1: Decode mulaw to linear PCM (8kHz)
            pcm_8k = audioop.ulaw2lin(mulaw_data, 2)  # 2 bytes per sample (16-bit)
            
            # Step 2: Resample from 8kHz to 24kHz (3x upsampling)
            pcm_24k, state = audioop.ratecv(
                pcm_8k, 
                2,  # Sample width (16-bit = 2 bytes)
                1,  # Channels (mono)
                TWILIO_SAMPLE_RATE,  # Input rate
                OPENAI_SAMPLE_RATE,  # Output rate
                None  # State (None for first call)
            )
            
            return pcm_24k
            
        except Exception as e:
            logger.error(f"Audio conversion error (mulaw->PCM16): {e}")
            return b''
    
    def convert_pcm16_to_mulaw(self, pcm16_data: bytes) -> bytes:
        """Convert OpenAI's PCM16 24kHz audio to Twilio's mulaw 8kHz"""
        try:
            # Step 1: Resample from 24kHz to 8kHz (3x downsampling)
            pcm_8k, state = audioop.ratecv(
                pcm16_data,
                2,  # Sample width (16-bit = 2 bytes)
                1,  # Channels (mono)
                OPENAI_SAMPLE_RATE,  # Input rate
                TWILIO_SAMPLE_RATE,  # Output rate
                None  # State
            )
            
            # Step 2: Encode linear PCM to mulaw
            mulaw = audioop.lin2ulaw(pcm_8k, 2)
            
            return mulaw
            
        except Exception as e:
            logger.error(f"Audio conversion error (PCM16->mulaw): {e}")
            return b''
    
    async def forward_twilio_to_openai(self):
        """Forward audio from Twilio to OpenAI"""
        try:
            while not self.should_stop and self.is_connected:
                if not self.twilio_to_openai_queue.empty():
                    mulaw_data = self.twilio_to_openai_queue.get()
                    
                    # Convert audio format
                    pcm16_data = self.convert_mulaw_to_pcm16(mulaw_data)
                    
                    if pcm16_data and self.openai_ws:
                        # Send to OpenAI as base64
                        pcm16_base64 = base64.b64encode(pcm16_data).decode('utf-8')
                        message = {
                            "type": "input_audio_buffer.append",
                            "audio": pcm16_base64
                        }
                        await self.openai_ws.send(json.dumps(message))
                
                await asyncio.sleep(0.01)  # Small delay to prevent busy loop
                
        except Exception as e:
            logger.error(f"Error forwarding Twilio->OpenAI audio: {e}")
    
    async def listen_to_openai(self):
        """Listen for responses from OpenAI and forward to Twilio"""
        try:
            while not self.should_stop and self.is_connected:
                if self.openai_ws:
                    response = await self.openai_ws.recv()
                    data = json.loads(response)
                    event_type = data.get("type")
                    
                    if event_type == "response.audio.delta":
                        # Incremental audio chunk from OpenAI
                        audio_base64 = data.get("delta", "")
                        if audio_base64:
                            pcm16_data = base64.b64decode(audio_base64)
                            # Convert and queue for Twilio
                            mulaw_data = self.convert_pcm16_to_mulaw(pcm16_data)
                            self.openai_to_twilio_queue.put(mulaw_data)
                    
                    elif event_type == "response.audio.done":
                        logger.info("✅ OpenAI audio response complete")
                    
                    elif event_type == "response.text.delta":
                        # Text transcript (useful for logging)
                        text = data.get("delta", "")
                        logger.info(f"📝 OpenAI text: {text}")
                    
                    elif event_type == "conversation.item.created":
                        logger.info("💬 OpenAI created conversation item")
                    
                    elif event_type == "input_audio_buffer.speech_started":
                        logger.info("🎤 User started speaking")
                    
                    elif event_type == "input_audio_buffer.speech_stopped":
                        logger.info("🎤 User stopped speaking")
                        # Commit the audio buffer for processing
                        await self.openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.commit"
                        }))
                        # Request response generation
                        await self.openai_ws.send(json.dumps({
                            "type": "response.create"
                        }))
                    
                    elif event_type == "error":
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                        logger.error(f"❌ OpenAI error: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error listening to OpenAI: {e}")
    
    async def forward_openai_to_twilio(self, twilio_ws):
        """Forward audio from OpenAI to Twilio WebSocket"""
        try:
            while not self.should_stop:
                if not self.openai_to_twilio_queue.empty():
                    mulaw_data = self.openai_to_twilio_queue.get()
                    
                    if mulaw_data and self.stream_sid:
                        # Send to Twilio
                        mulaw_base64 = base64.b64encode(mulaw_data).decode('utf-8')
                        message = {
                            "event": "media",
                            "streamSid": self.stream_sid,
                            "media": {
                                "payload": mulaw_base64
                            }
                        }
                        
                        # Send synchronously via flask-sock
                        twilio_ws.send(json.dumps(message))
                
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Error forwarding OpenAI->Twilio audio: {e}")
    
    def handle_twilio_message(self, message: Dict[str, Any]):
        """Process incoming message from Twilio Media Stream"""
        event_type = message.get("event")
        
        if event_type == "connected":
            logger.info("✅ Twilio Media Stream connected")
        
        elif event_type == "start":
            self.stream_sid = message.get("streamSid")
            self.call_sid = message.get("start", {}).get("callSid")
            custom_params = message.get("start", {}).get("customParameters", {})
            logger.info(f"📞 Stream started: {self.stream_sid}, Call: {self.call_sid}")
            logger.info(f"📋 Custom params: {custom_params}")
        
        elif event_type == "media":
            # Incoming audio from Twilio (base64 mulaw)
            payload = message.get("media", {}).get("payload", "")
            if payload:
                mulaw_data = base64.b64decode(payload)
                self.twilio_to_openai_queue.put(mulaw_data)
        
        elif event_type == "stop":
            logger.info("📞 Twilio stream stopped")
            self.should_stop = True
            self.is_connected = False
    
    async def close(self):
        """Cleanup and close connections"""
        self.should_stop = True
        self.is_connected = False
        
        if self.openai_ws:
            try:
                await self.openai_ws.close()
                logger.info("✅ Closed OpenAI WebSocket")
            except:
                pass
        
        # Clear queues
        while not self.twilio_to_openai_queue.empty():
            self.twilio_to_openai_queue.get()
        while not self.openai_to_twilio_queue.empty():
            self.openai_to_twilio_queue.get()
