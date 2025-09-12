#!/usr/bin/env python3
"""
Simple WebSocket server for Twilio Media Streams
Integrates with existing Flask app for true sub-1-second streaming
"""

import asyncio
import websockets
import json
import base64
import logging
import sys
import os

# Add current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class TwilioStreamHandler:
    """Simple handler for Twilio Media Streams"""
    
    def __init__(self):
        self.connections = {}
        
    async def handle_media_stream(self, websocket, path):
        """Handle Twilio Media Stream WebSocket"""
        connection_id = f"stream_{id(websocket)}"
        self.connections[connection_id] = {
            'websocket': websocket,
            'call_sid': None,
            'stream_sid': None
        }
        
        logging.info(f"🔌 New Media Stream connection: {connection_id}")
        
        try:
            async for message in websocket:
                await self._process_message(connection_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"📞 Connection closed: {connection_id}")
        except Exception as e:
            logging.error(f"❌ WebSocket error: {e}")
        finally:
            if connection_id in self.connections:
                del self.connections[connection_id]
    
    async def _process_message(self, connection_id, message):
        """Process incoming Twilio messages"""
        try:
            data = json.loads(message)
            event = data.get('event')
            conn = self.connections[connection_id]
            
            if event == 'connected':
                logging.info(f"🎵 Media stream connected")
                
            elif event == 'start':
                conn['call_sid'] = data['start']['callSid']
                conn['stream_sid'] = data['start']['streamSid']
                logging.info(f"🚀 Stream started - Call: {conn['call_sid']}")
                
                # Send initial greeting
                await self._send_greeting(connection_id)
                
            elif event == 'media':
                # Incoming audio from caller
                payload = data['media']['payload']
                audio_data = base64.b64decode(payload)
                
                # Simple voice activity detection
                if len(audio_data) > 160:  # ~20ms at 8kHz
                    logging.info(f"🎤 Received {len(audio_data)} bytes of audio")
                    
                    # TODO: Add STT processing here
                    # For now, echo a response after some audio is received
                    await self._send_test_response(connection_id)
                
            elif event == 'stop':
                logging.info(f"🔌 Stream stopped")
                
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            logging.error(f"Message processing error: {e}")
    
    async def _send_greeting(self, connection_id):
        """Send initial greeting as base64 audio"""
        try:
            # Simple greeting tone (placeholder for real TTS)
            greeting_audio = self._generate_tone(440, 0.5)  # 440Hz for 0.5s
            await self._send_audio(connection_id, greeting_audio)
            logging.info("✅ Sent greeting audio")
        except Exception as e:
            logging.error(f"Greeting error: {e}")
    
    async def _send_test_response(self, connection_id):
        """Send test response audio"""
        try:
            # Different tone for responses
            response_audio = self._generate_tone(880, 0.3)  # 880Hz for 0.3s
            await self._send_audio(connection_id, response_audio)
            logging.info("✅ Sent response audio")
        except Exception as e:
            logging.error(f"Response error: {e}")
    
    def _generate_tone(self, freq, duration):
        """Generate simple sine wave tone for testing"""
        import math
        sample_rate = 8000  # Twilio uses 8kHz
        samples = int(sample_rate * duration)
        
        audio_data = bytearray()
        for i in range(samples):
            # Generate sine wave
            sample = int(32767 * math.sin(2 * math.pi * freq * i / sample_rate))
            # Convert to μ-law (simplified - just use linear for testing)
            mu_law = max(-128, min(127, sample // 256))
            audio_data.append(mu_law & 0xFF)
        
        return bytes(audio_data)
    
    async def _send_audio(self, connection_id, audio_data):
        """Send audio data to Twilio Media Stream"""
        try:
            conn = self.connections[connection_id]
            websocket = conn['websocket']
            stream_sid = conn['stream_sid']
            
            if not stream_sid:
                return
            
            # Encode audio as base64
            payload = base64.b64encode(audio_data).decode('utf-8')
            
            # Send media message to Twilio
            message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload
                }
            }
            
            await websocket.send(json.dumps(message))
            
        except Exception as e:
            logging.error(f"Audio send error: {e}")

async def main():
    """Start the WebSocket server"""
    handler = TwilioStreamHandler()
    
    # Start server on port 9100 (matches nginx config)
    server = await websockets.serve(
        handler.handle_media_stream,
        "0.0.0.0", 
        9100,
        ping_interval=None,  # Disable ping for Twilio compatibility
        ping_timeout=None
    )
    
    logging.info("🚀 Twilio Media Streams WebSocket server started on port 9100")
    logging.info("📡 Ready to receive calls at wss://voice.theinsurancedoctors.com/twilio")
    
    # Keep running
    await server.wait_closed()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())