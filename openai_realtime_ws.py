"""
OpenAI Realtime API WebSocket Client
Connects to OpenAI's Realtime API using WebSockets for server-to-server applications.
"""

import os
import json
import logging
import threading
import time
import queue
import websocket
from dotenv import load_dotenv
from typing import Dict, Optional, Callable, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OpenAIRealtimeClient:
    """Client for OpenAI's Realtime API using WebSockets"""
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 model: str = "gpt-realtime",
                 on_message_callback: Optional[Callable] = None,
                 on_error_callback: Optional[Callable] = None):
        """
        Initialize the OpenAI Realtime WebSocket client
        
        Args:
            api_key: OpenAI API key (if None, will try to load from env)
            model: The Realtime model to use
            on_message_callback: Callback function for handling messages
            on_error_callback: Callback function for handling errors
        """
        load_dotenv()  # Load environment variables
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set it in .env file or pass directly.")
        
        self.model = model
        self.ws = None
        self.ws_thread = None
        self.connected = False
        self.message_queue = queue.Queue()
        
        self.on_message_callback = on_message_callback
        self.on_error_callback = on_error_callback

    def connect(self) -> None:
        """
        Establish WebSocket connection to OpenAI Realtime API
        """
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        self.ws = websocket.WebSocketApp(
            url,
            header=[f"{k}: {v}" for k, v in headers.items()],
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        # Start WebSocket in a separate thread
        self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.ws_thread.start()
        
        # Wait for connection to establish
        timeout = 10
        start_time = time.time()
        while not self.connected and time.time() - start_time < timeout:
            time.sleep(0.1)
        
        if not self.connected:
            raise ConnectionError(f"Failed to connect to OpenAI Realtime API within {timeout} seconds")
    
    def _run_websocket(self) -> None:
        """Run the WebSocket connection in a loop with ping/pong enabled"""
        self.ws.run_forever(ping_interval=30, ping_timeout=10)
    
    def _on_open(self, ws) -> None:
        """Callback when WebSocket connection is established"""
        logger.info("🔌 Connected to OpenAI Realtime API")
        self.connected = True
        
        # Initialize session with default configuration
        self.update_session(
            instructions="I am a helpful AI assistant.",
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
                    },
                    "voice": "alloy",
                }
            }
        )
    
    def _on_message(self, ws, message) -> None:
        """Callback when a message is received from WebSocket"""
        try:
            data = json.loads(message)
            logger.debug(f"Received event: {data['type'] if 'type' in data else 'unknown'}")
            
            # Add to message queue
            self.message_queue.put(data)
            
            # Call custom message handler if provided
            if self.on_message_callback:
                self.on_message_callback(data)
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message[:100]}...")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _on_error(self, ws, error) -> None:
        """Callback when an error occurs"""
        logger.error(f"WebSocket error: {error}")
        if self.on_error_callback:
            self.on_error_callback(error)
    
    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Callback when WebSocket connection is closed"""
        logger.info(f"WebSocket connection closed: {close_status_code}, {close_msg}")
        self.connected = False
    
    def send_event(self, event: Dict[str, Any]) -> None:
        """
        Send an event to the OpenAI Realtime API
        
        Args:
            event: Event dictionary to send
        """
        if not self.connected or not self.ws:
            raise ConnectionError("WebSocket is not connected")
        
        try:
            self.ws.send(json.dumps(event))
            logger.debug(f"Sent event: {event['type'] if 'type' in event else 'unknown'}")
        except Exception as e:
            logger.error(f"Error sending event: {e}")
    
    def update_session(self, 
                      instructions: Optional[str] = None, 
                      prompt_id: Optional[str] = None,
                      prompt_version: Optional[str] = None,
                      prompt_variables: Optional[Dict[str, Any]] = None,
                      output_modalities: Optional[list] = None,
                      audio_settings: Optional[Dict[str, Any]] = None) -> None:
        """
        Update the Realtime session configuration
        
        Args:
            instructions: System instructions for the model
            prompt_id: ID of a stored prompt to use
            prompt_version: Version of the prompt to use
            prompt_variables: Variables to use in the prompt
            output_modalities: List of output modalities (e.g. ["text", "audio"])
            audio_settings: Audio configuration settings
        """
        session_config = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self.model,
            }
        }
        
        # Add instructions if provided
        if instructions:
            session_config["session"]["instructions"] = instructions
        
        # Add prompt configuration if provided
        if prompt_id:
            prompt_config = {"id": prompt_id}
            if prompt_version:
                prompt_config["version"] = prompt_version
            if prompt_variables:
                prompt_config["variables"] = prompt_variables
            session_config["session"]["prompt"] = prompt_config
        
        # Add output modalities if provided
        if output_modalities:
            session_config["session"]["output_modalities"] = output_modalities
        
        # Add audio settings if provided
        if audio_settings:
            session_config["session"]["audio"] = audio_settings
        
        # Send the session update
        self.send_event(session_config)
    
    def send_audio(self, audio_data: bytes) -> None:
        """
        Send audio data to the Realtime API
        
        Args:
            audio_data: PCM audio data as bytes
        """
        audio_event = {
            "type": "audio.data",
            "data": {
                "audio_data": audio_data.hex() if isinstance(audio_data, bytes) else audio_data,
                "end_of_audio": False
            }
        }
        self.send_event(audio_event)
    
    def send_text(self, text: str) -> None:
        """
        Send text input to the Realtime API
        
        Args:
            text: Text input to send
        """
        text_event = {
            "type": "text.data",
            "data": {
                "text": text
            }
        }
        self.send_event(text_event)
    
    def create_response(self, 
                       conversation_id: str = "default", 
                       modalities: list = None,
                       instructions: Optional[str] = None,
                       temperature: float = 1.0,
                       max_tokens: int = 800) -> None:
        """
        Request a response from the model
        
        Args:
            conversation_id: ID for the conversation
            modalities: List of response modalities (e.g. ["text", "audio"])
            instructions: Optional instructions for this response
            temperature: Temperature for response generation
            max_tokens: Maximum number of tokens to generate
        """
        if modalities is None:
            modalities = ["text"]
            
        response_event = {
            "type": "response.create",
            "response": {
                "conversation": conversation_id,
                "modalities": modalities,
                "temperature": temperature,
                "max_output_tokens": max_tokens
            }
        }
        
        if instructions:
            response_event["response"]["instructions"] = instructions
            
        self.send_event(response_event)
    
    def add_conversation_item(self, role: str, content: str, type_="message") -> None:
        """
        Add an item to the conversation history
        
        Args:
            role: Role of the item ("user" or "assistant")
            content: Content of the item
            type_: Type of the item (default: "message")
        """
        if role == "user":
            item = {
                "type": "conversation.item.create",
                "item": {
                    "type": type_,
                    "role": role,
                    "content": [
                        {
                            "type": "input_text",
                            "text": content
                        }
                    ]
                }
            }
        else:
            item = {
                "type": "conversation.item.create",
                "item": {
                    "type": type_,
                    "role": role,
                    "content": [
                        {
                            "type": "text",
                            "text": content
                        }
                    ]
                }
            }
        
        self.send_event(item)
    
    def close(self) -> None:
        """Close the WebSocket connection"""
        if self.ws:
            self.ws.close()
            self.connected = False
```

# Example usage:

client = OpenAIRealtimeClient()
client.connect()

# Update session with custom instructions
client.update_session(
    instructions="You are a helpful assistant who answers questions concisely.",
    output_modalities=["text", "audio"],
    audio_settings={
        "output": {
            "voice": "alloy"
        }
    }
)

# Send a text message
client.send_text("Hello, what can you tell me about climate change?")

# Or process some audio
# with open("audio_sample.pcm", "rb") as f:
#     audio_data = f.read()
#     client.send_audio(audio_data)

# Wait for response in a separate thread
def process_messages():
    while True:
        try:
            message = client.message_queue.get(timeout=1)
            print(f"Received: {message}")
            client.message_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error processing message: {e}")
            break

# Thread for processing messages
import threading
message_thread = threading.Thread(target=process_messages, daemon=True)
message_thread.start()

# Keep the main thread running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Closing connection...")
    client.close()