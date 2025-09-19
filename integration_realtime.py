"""
Integration of OpenAI Realtime WebSocket API with ChatStack
Enables using Realtime API in existing ChatStack pipelines
"""

import os
import sys
import time
import threading
import logging
from typing import Optional, Dict, Any, List, Generator

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import OpenAI Realtime client
from openai_realtime_ws import OpenAIRealtimeClient

class RealtimeAPIIntegration:
    """Integration of OpenAI Realtime API with ChatStack"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Realtime API integration"""
        self.api_key = api_key
        self.clients = {}  # Map of session_id to client instances
        self.response_buffers = {}  # Map of session_id to response buffers
        self.active_calls = {}  # Track active API calls
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        
    def initialize_session(self, session_id: str, instructions: str) -> bool:
        """Initialize a new Realtime API session"""
        try:
            # Create new client
            client = OpenAIRealtimeClient(
                api_key=self.api_key,
                on_message_callback=lambda msg: self._handle_message(session_id, msg),
                on_error_callback=lambda err: self._handle_error(session_id, err)
            )
            
            # Connect to OpenAI
            client.connect()
            
            # Store the client
            self.clients[session_id] = client
            self.response_buffers[session_id] = {
                "text": "",
                "audio": bytearray(),
                "complete": False,
                "error": None
            }
            
            # Update session with instructions
            client.update_session(
                instructions=instructions,
                output_modalities=["text", "audio"],
                audio_settings={
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
                            "rate": 24000,
                        },
                        "voice": "alloy",
                    }
                }
            )
            
            self.logger.info(f"✅ Initialized session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize session {session_id}: {e}")
            return False
    
    def send_message(self, session_id: str, message: str) -> Generator[Dict[str, Any], None, None]:
        """Send a message and yield streaming response chunks"""
        if session_id not in self.clients:
            self.logger.error(f"❌ Session {session_id} not initialized")
            yield {"error": f"Session {session_id} not initialized"}
            return
        
        try:
            client = self.clients[session_id]
            
            # Reset response buffer
            self.response_buffers[session_id] = {
                "text": "",
                "audio": bytearray(),
                "complete": False,
                "error": None
            }
            self.active_calls[session_id] = True
            
            # Add user message to conversation
            client.add_conversation_item(role="user", content=message)
            
            # Request response
            client.create_response(
                modalities=["text", "audio"],
                temperature=0.7,
                max_tokens=800
            )
            
            # Yield streaming responses
            last_text_length = 0
            last_audio_length = 0
            
            while self.active_calls.get(session_id, False):
                buffer = self.response_buffers[session_id]
                
                # Check for new text
                if len(buffer["text"]) > last_text_length:
                    new_text = buffer["text"][last_text_length:]
                    last_text_length = len(buffer["text"])
                    yield {"type": "text", "content": new_text, "complete": buffer["complete"]}
                
                # Check for new audio
                if len(buffer["audio"]) > last_audio_length:
                    new_audio = bytes(buffer["audio"][last_audio_length:])
                    last_audio_length = len(buffer["audio"])
                    yield {"type": "audio", "content": new_audio, "complete": buffer["complete"]}
                
                # Check for errors
                if buffer["error"]:
                    yield {"type": "error", "content": buffer["error"]}
                    break
                    
                # Check for completion
                if buffer["complete"]:
                    yield {"type": "complete", "content": {"text": buffer["text"], "audio": bytes(buffer["audio"])}}
                    break
                    
                # Sleep briefly to avoid tight loop
                time.sleep(0.01)
                
        except Exception as e:
            self.logger.error(f"❌ Error in session {session_id}: {e}")
            yield {"type": "error", "content": str(e)}
            
        finally:
            self.active_calls[session_id] = False
    
    def send_audio(self, session_id: str, audio_data: bytes, end_of_audio: bool = False) -> None:
        """Send audio data to the Realtime API"""
        if session_id not in self.clients:
            self.logger.error(f"❌ Session {session_id} not initialized")
            return
        
        try:
            client = self.clients[session_id]
            
            # Send audio data
            client.send_event({
                "type": "audio.data",
                "data": {
                    "audio_data": audio_data.hex() if isinstance(audio_data, bytes) else audio_data,
                    "end_of_audio": end_of_audio
                }
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error sending audio in session {session_id}: {e}")
    
    def end_session(self, session_id: str) -> None:
        """End a Realtime API session"""
        if session_id in self.clients:
            try:
                self.clients[session_id].close()
                self.active_calls[session_id] = False
                del self.clients[session_id]
                del self.response_buffers[session_id]
                self.logger.info(f"✅ Ended session {session_id}")
            except Exception as e:
                self.logger.error(f"❌ Error ending session {session_id}: {e}")
    
    def _handle_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Handle messages from OpenAI Realtime API"""
        try:
            if session_id not in self.response_buffers:
                return
                
            buffer = self.response_buffers[session_id]
            event_type = message.get('type')
            
            if event_type == "response.text":
                # Append text chunk
                text_chunk = message.get("text", {}).get("value", "")
                buffer["text"] += text_chunk
                
            elif event_type == "response.audio":
                # Append audio chunk
                audio_data = message.get("audio", {}).get("data", "")
                if audio_data:
                    import base64
                    audio_bytes = base64.b64decode(audio_data)
                    buffer["audio"].extend(audio_bytes)
                    
            elif event_type == "response.end":
                # Mark response as complete
                buffer["complete"] = True
                
            elif event_type == "error":
                # Store error message
                error_message = message.get("error", {}).get("message", "Unknown error")
                buffer["error"] = error_message
                buffer["complete"] = True
                
        except Exception as e:
            self.logger.error(f"❌ Error handling message for session {session_id}: {e}")
            buffer = self.response_buffers.get(session_id)
            if buffer:
                buffer["error"] = str(e)
                buffer["complete"] = True
    
    def _handle_error(self, session_id: str, error: Exception) -> None:
        """Handle WebSocket errors"""
        self.logger.error(f"❌ WebSocket error in session {session_id}: {error}")
        buffer = self.response_buffers.get(session_id)
        if buffer:
            buffer["error"] = str(error)
            buffer["complete"] = True
```

# Example usage with ChatStack
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    # Load API key from .env file
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ OpenAI API key not found. Set OPENAI_API_KEY in .env file.")
        sys.exit(1)
    
    # Create integration
    realtime = RealtimeAPIIntegration(api_key=api_key)
    
    # Initialize a session
    session_id = "test_session"
    realtime.initialize_session(
        session_id=session_id,
        instructions=(
            "You are a helpful insurance assistant. "
            "Answer questions concisely and accurately."
        )
    )
    
    try:
        # Simple text-based interaction loop
        print("\n🤖 ChatStack OpenAI Realtime Integration Demo")
        print("Type 'quit' to exit\n")
        
        while True:
            user_input = input("You: ")
            
            if user_input.lower() in ["quit", "exit", "bye"]:
                break
                
            print("AI: ", end="", flush=True)
            
            # Stream the response
            for chunk in realtime.send_message(session_id, user_input):
                if chunk["type"] == "text":
                    print(chunk["content"], end="", flush=True)
                elif chunk["type"] == "error":
                    print(f"\n❌ Error: {chunk['content']}")
            
            print("\n")
    
    finally:
        # End the session
        realtime.end_session(session_id)