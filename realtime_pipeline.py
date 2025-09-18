"""
Complete Real-Time Audio Pipeline for Peterson Family Insurance
Integrates STT → LLM Streaming → TTS → WebSocket with proper codec conversion
"""

import asyncio
import base64
import json
import logging
import threading
import time
from typing import Optional, Generator, AsyncGenerator, Any
from queue import Queue
import struct

# Audio processing
try:
    import numpy as np
    from pydub import AudioSegment
    import io
except ImportError:
    logging.warning("Audio processing libraries not available")

class RealTimeAudioPipeline:
    """Complete pipeline for real-time conversational AI"""
    
    def __init__(self, elevenlabs_client=None):
        self.elevenlabs_client = elevenlabs_client
        self.active_conversations = {}
        
    def start_conversation(self, connection_id: str, websocket, call_sid: str, stream_sid: str):
        """Initialize a new conversation session"""
        self.active_conversations[connection_id] = {
            'websocket': websocket,
            'call_sid': call_sid,
            'stream_sid': stream_sid,
            'audio_buffer': bytearray(),
            'conversation_history': [],
            'response_in_progress': False,
            'audio_queue': Queue()
        }
        
        # Send initial greeting
        asyncio.create_task(self._send_greeting(connection_id))
    
    def process_incoming_audio(self, connection_id: str, audio_data: bytes):
        """Process incoming audio from caller"""
        if connection_id not in self.active_conversations:
            return
            
        conv = self.active_conversations[connection_id]
        conv['audio_buffer'].extend(audio_data)
        
        # Process when we have enough audio (~1 second at 8kHz)
        if len(conv['audio_buffer']) > 8000 and not conv['response_in_progress']:
            audio_chunk = bytes(conv['audio_buffer'])
            conv['audio_buffer'].clear()
            
            # Run STT in background thread
            threading.Thread(
                target=self._process_speech,
                args=(connection_id, audio_chunk),
                daemon=True
            ).start()
    
    def _process_speech(self, connection_id: str, audio_data: bytes):
        """Convert speech to text and generate response"""
        try:
            # Convert μ-law to text using STT
            transcript = self._speech_to_text(audio_data)
            
            if transcript and len(transcript.strip()) > 3:
                logging.info(f"🎤 '{transcript}'")
                
                # Get conversation history
                conv = self.active_conversations[connection_id]
                history = conv['conversation_history']
                
                # Generate streaming response
                asyncio.create_task(
                    self._generate_streaming_response(connection_id, transcript, history)
                )
                
        except Exception as e:
            logging.error(f"Speech processing error: {e}")
    
    def _speech_to_text(self, mu_law_data: bytes) -> Optional[str]:
        """Convert μ-law audio to text using Whisper or similar"""
        try:
            # Convert μ-law to PCM for STT processing
            pcm_data = self._mu_law_to_pcm(mu_law_data)
            
            # TODO: Integrate with Whisper/Deepgram/OpenAI STT
            # For now, simulate STT with voice activity detection
            if len(pcm_data) > 4000:  # Basic voice detection
                return "I need insurance information"  # Placeholder
            return None
            
        except Exception as e:
            logging.error(f"STT error: {e}")
            return None
    
    async def _generate_streaming_response(self, connection_id: str, user_message: str, history: list):
        """Generate AI response with streaming LLM and TTS"""
        try:
            conv = self.active_conversations[connection_id]
            conv['response_in_progress'] = True
            
            # Add user message to conversation
            conv['conversation_history'].append({
                'role': 'user', 
                'content': user_message
            })
            
            # Get streaming LLM response
            response_text = ""
            async for token in self._get_streaming_llm_response(user_message, history):
                response_text += token
                
                # Stream TTS when we have complete phrases
                if token in '.!?' or len(response_text) > 50:
                    await self._stream_tts_phrase(connection_id, response_text)
                    response_text = ""  # Reset for next phrase
            
            # Stream any remaining text
            if response_text.strip():
                await self._stream_tts_phrase(connection_id, response_text)
            
            # Add AI response to conversation
            full_response = ' '.join([msg for msg in conv['conversation_history'] 
                                    if msg['role'] == 'assistant'])
            conv['conversation_history'].append({
                'role': 'assistant',
                'content': full_response
            })
            
            conv['response_in_progress'] = False
            
        except Exception as e:
            logging.error(f"Response generation error: {e}")
            conv['response_in_progress'] = False
    
    async def _get_streaming_llm_response(self, message: str, history: list) -> AsyncGenerator[str, Any]:
        """Get streaming response from LLM using OpenAI Realtime API"""
        try:
            # Import the realtime LLM function
            from app.llm import chat_realtime_stream, _get_llm_config
            
            # Prepare messages for realtime API
            messages = []
            
            # Add conversation history
            for msg in history:
                messages.append(msg)
            
            # Add current user message
            messages.append({
                "role": "user", 
                "content": message
            })
            
            # Check if we're using a realtime model
            config = _get_llm_config()
            if "realtime" in config["model"].lower():
                # Use realtime streaming
                for token in chat_realtime_stream(messages, temperature=0.6, max_tokens=800):
                    yield token
                    await asyncio.sleep(0.01)  # Small delay for natural pacing
            else:
                # Fallback to regular chat completions
                from app.llm import chat
                
                response_content, _ = chat(messages, temperature=0.6, max_tokens=800)
                
                # Simulate streaming by splitting into words
                words = response_content.split()
                for word in words:
                    yield word + " "
                    await asyncio.sleep(0.1)
                
        except Exception as e:
            logging.error(f"LLM streaming error: {e}")
            yield "I'm sorry, I'm having trouble right now. "
    
    async def _stream_tts_phrase(self, connection_id: str, text: str):
        """Convert phrase to speech and stream to caller"""
        try:
            if not self.elevenlabs_client or not text.strip():
                return
                
            conv = self.active_conversations[connection_id]
            
            # Use ElevenLabs streaming TTS
            from elevenlabs import VoiceSettings
            
            audio_stream = self.elevenlabs_client.text_to_speech.stream(
                voice_id="dnRitNTYKgyEUEizTqqH",  # Samantha
                text=text.strip(),
                model_id="eleven_turbo_v2_5",
                voice_settings=VoiceSettings(
                    stability=0.71,
                    similarity_boost=0.5,
                    style=0.0,
                    use_speaker_boost=True
                )
            )
            
            # Stream audio chunks to caller
            for chunk in audio_stream:
                if isinstance(chunk, (bytes, bytearray)):
                    # Convert MP3 chunk to Twilio-compatible μ-law
                    mu_law_data = self._mp3_to_mu_law(chunk)
                    
                    if mu_law_data:
                        await self._send_audio_to_caller(connection_id, mu_law_data)
                        
                        # Small delay to prevent buffer overflow
                        await asyncio.sleep(0.02)
            
            logging.info(f"✅ Streamed TTS: '{text[:30]}...'")
            
        except Exception as e:
            logging.error(f"TTS streaming error: {e}")
    
    async def _send_greeting(self, connection_id: str):
        """Send initial greeting"""
        greeting = "Hi, this is Samantha from Peterson Family Insurance. How can I help you today?"
        await self._stream_tts_phrase(connection_id, greeting)
    
    async def _send_audio_to_caller(self, connection_id: str, mu_law_data: bytes):
        """Send audio data to Twilio Media Stream"""
        try:
            conv = self.active_conversations[connection_id]
            websocket = conv['websocket']
            stream_sid = conv['stream_sid']
            
            # Encode as base64 for Twilio
            payload = base64.b64encode(mu_law_data).decode('utf-8')
            
            # Send to Twilio Media Stream
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
    
    def _mp3_to_mu_law(self, mp3_data: bytes) -> Optional[bytes]:
        """Convert MP3 chunk to 8kHz μ-law for Twilio"""
        try:
            # Load MP3 data
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            
            # Convert to 8kHz mono
            audio = audio.set_frame_rate(8000).set_channels(1)
            
            # Get raw PCM data
            pcm_data = audio.raw_data
            
            # Convert PCM to μ-law
            return self._pcm_to_mu_law(pcm_data)
            
        except Exception as e:
            logging.error(f"MP3 to μ-law conversion error: {e}")
            return None
    
    def _pcm_to_mu_law(self, pcm_data: bytes) -> bytes:
        """Convert 16-bit PCM to μ-law encoding"""
        try:
            # Convert bytes to 16-bit integers
            samples = np.frombuffer(pcm_data, dtype=np.int16)
            
            # Convert to μ-law using standard algorithm
            mu_law_samples = []
            for sample in samples:
                # Apply μ-law compression
                sign = 1 if sample >= 0 else 0
                sample = abs(sample)
                
                # Clamp to avoid overflow
                sample = min(sample, 32635)
                
                # μ-law compression formula
                compressed = int(np.log(1 + 255 * sample / 32768) / np.log(1 + 255) * 127)
                
                # Apply sign
                if not sign:
                    compressed = compressed | 0x80
                    
                mu_law_samples.append(compressed)
            
            return bytes(mu_law_samples)
            
        except Exception as e:
            logging.error(f"PCM to μ-law error: {e}")
            return b''
    
    def _mu_law_to_pcm(self, mu_law_data: bytes) -> bytes:
        """Convert μ-law to 16-bit PCM for STT processing"""
        try:
            pcm_samples = []
            for byte in mu_law_data:
                # Extract sign and magnitude
                sign = 1 if (byte & 0x80) == 0 else -1
                magnitude = byte & 0x7F
                
                # Reverse μ-law compression
                sample = int(sign * (np.exp(magnitude * np.log(1 + 255) / 127) - 1) * 32768 / 255)
                pcm_samples.append(sample)
            
            # Convert to bytes
            return struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)
            
        except Exception as e:
            logging.error(f"μ-law to PCM error: {e}")
            return b''
    
    def end_conversation(self, connection_id: str):
        """Clean up conversation session"""
        if connection_id in self.active_conversations:
            del self.active_conversations[connection_id]