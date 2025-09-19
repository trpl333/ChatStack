"""
NeuroSphere Orchestrator - Flask Web Interface with Phone AI
"""
import os
import requests
import json
import io
import base64
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, Response, send_from_directory
from twilio.rest import Client
from twilio.twiml import TwiML
from twilio.twiml.voice_response import VoiceResponse, Gather, Start, Stream
# Temporarily disabled ElevenLabs due to pydantic compatibility issues
# from elevenlabs import ElevenLabs, VoiceSettings
import tempfile
import logging
from config_loader import get_secret, get_setting, get_twilio_config, get_elevenlabs_config, get_llm_config, get_all_config

# Configure logging
logging.basicConfig(level=logging.INFO)

# Dynamic configuration functions for hot reload support
def _get_config():
    """Get all configuration dynamically for hot reload support"""
    twilio_config = get_twilio_config()
    elevenlabs_config = get_elevenlabs_config()
    llm_config = get_llm_config()
    _server_url = get_setting("server_url", "http://localhost:5000")
    
    return {
        "openai_api_key": get_secret("OPENAI_API_KEY"),
        "twilio_account_sid": twilio_config["account_sid"],
        "twilio_auth_token": twilio_config["auth_token"],
        "elevenlabs_api_key": elevenlabs_config["api_key"],
        "database_url": get_secret("DATABASE_URL"),
        "llm_base_url": llm_config["base_url"],
        "llm_model": llm_config["model"],
        "session_secret": get_secret("SESSION_SECRET"),
        "server_url": _server_url.replace("/phone/incoming", "") if _server_url.endswith("/phone/incoming") else _server_url
    }

# Initialize app with session secret (this needs to be set at startup)
_initial_config = _get_config()
SESSION_SECRET = _initial_config["session_secret"]

# Fix LLM_BASE_URL environment variable on startup
try:
    # Clear the existing environment variable so config file value is used
    if "LLM_BASE_URL" in os.environ:
        del os.environ["LLM_BASE_URL"]
        print("🔧 Cleared old LLM_BASE_URL environment variable")
    
    llm_config = get_llm_config()
    # Force use OpenAI endpoint, not old RunPod
    if "neurosphere" in llm_config["base_url"]:
        os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
        print(f"🔧 Corrected LLM_BASE_URL to: https://api.openai.com/v1")
    else:
        os.environ["LLM_BASE_URL"] = llm_config["base_url"]
        print(f"✅ LLM_BASE_URL set to: {llm_config['base_url']}")
except Exception as e:
    print(f"⚠️ Warning: Could not set LLM_BASE_URL: {e}")

# Additional environment defaults
os.environ.setdefault("EMBED_DIM", str(get_setting("embed_dim", 768)))

# FastAPI backend now started separately via workflow command
# Removed in-process startup to prevent port conflicts during gunicorn reloads

# Create Flask app with static folder configuration
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = SESSION_SECRET or "temporary-dev-secret"
if not SESSION_SECRET:
    print("⚠️ Warning: SESSION_SECRET not set, using temporary key")

# Configure Flask to work behind HTTPS proxy (nginx)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

def _get_backend_url():
    """Get LLM backend URL dynamically"""
    config = _get_config()
    return config["llm_base_url"] or "https://5njnf4k2bc5t20-8000.proxy.runpod.net"

def _get_orchestrator_url():
    """Get local FastAPI orchestrator URL for memory and chat"""
    return "http://127.0.0.1:8001"

def _get_twilio_client():
    """Get Twilio client dynamically for hot reload support"""
    config = _get_config()
    return Client(config["twilio_account_sid"], config["twilio_auth_token"])

def _get_elevenlabs_client():
    """Get ElevenLabs client dynamically for hot reload support"""
    try:
        from elevenlabs.client import ElevenLabs
        from config_loader import get_elevenlabs_config
        
        config = get_elevenlabs_config()
        api_key = config.get("api_key")
        
        if not api_key:
            logging.warning("ElevenLabs API key not configured")
            return None
            
        return ElevenLabs(api_key=api_key)
    except Exception as e:
        logging.error(f"Failed to initialize ElevenLabs client: {e}")
        return None

# Check if LLM_BASE_URL is set on startup
if not _initial_config["llm_base_url"]:
    print("⚠️ Warning: LLM_BASE_URL not set, using default")

# Phone call session storage (in production, use Redis or database)
call_sessions = {}

# Admin-configurable settings
VOICE_ID = "dnRitNTYKgyEUEizTqqH"  # Sol's voice (configurable via admin)
# Voice settings - configurable via admin
voice_settings = {"stability": 0.71, "similarity_boost": 0.5}
ai_instructions = "You are Samantha from Peterson Family Insurance Agency. Be casual and friendly."
current_voice_id = "dnRitNTYKgyEUEizTqqH"  # Sol's voice
VOICE_SETTINGS = voice_settings  # For backwards compatibility
MAX_TOKENS = 75  # Allow longer, more natural responses
AI_INSTRUCTIONS = "You are Samantha, a friendly assistant at Peterson Family Insurance Agency."  # Admin-configurable

# Custom greeting templates (admin-configurable)
EXISTING_USER_GREETING = "Hi, this is Samantha from Peterson Family Insurance Agency. Is this {user_name}?"
NEW_CALLER_GREETING = "Good {time_greeting}! This is Samantha - how's your day going? I'm here at Peterson Family Insurance, and I'd love to help you out with whatever you need!"

# Call routing settings (updated for Peterson Family Insurance Agency)
ROUTING_NUMBERS = {
    "billing": "1-888-327-6377",
    "claims": "1-800-435-7764", 
    "colin": "1-888-327-6377",  # Colin's number
    "milissa": "1-888-327-6377"  # Milissa for Farmers service advantage team
}
ROUTING_KEYWORDS = {
    "billing": ["billing", "payment", "premium", "pay bill", "account balance", "autopay"],
    "claims": ["claim", "accident", "damage", "injury", "file claim", "incident"],
    "colin": ["colin", "ask for colin", "speak to colin"],
    "farmers_service": ["farmers service advantage", "service advantage team"],
    "transfer": ["speak to human", "transfer me", "representative", "agent", "manager"]
}

# HTML templates
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NeuroSphere Knowledge Base Manager</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <style>
        .hero { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .card { box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
        .form-control, .btn { border-radius: 0.375rem; }
    </style>
</head>
<body>
    <div class="hero text-white py-5">
        <div class="container">
            <h1 class="display-4 fw-bold">🧠 NeuroSphere Knowledge Base</h1>
            <p class="lead">Manage your AI's shared knowledge for all users</p>
        </div>
    </div>
    
    <div class="container my-5">
        <div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h3>📚 Add Knowledge</h3>
                    </div>
                    <div class="card-body">
                        <form method="POST" action="/add-knowledge">
                            <div class="mb-3">
                                <label class="form-label">Type</label>
                                <select class="form-select" name="type" required>
                                    <option value="fact">Fact</option>
                                    <option value="rule">Rule</option>
                                    <option value="procedure">Procedure</option>
                                    <option value="requirement">Requirement</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Key/Title</label>
                                <input type="text" class="form-control" name="key" placeholder="e.g., California minimum coverage" required>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Knowledge Content</label>
                                <textarea class="form-control" name="value" rows="4" placeholder="Enter the detailed information..." required></textarea>
                            </div>
                            <button type="submit" class="btn btn-primary">Add Knowledge</button>
                        </form>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h3>👤 User Memory Lookup</h3>
                    </div>
                    <div class="card-body">
                        <form method="GET" action="/user-memories">
                            <div class="mb-3">
                                <label class="form-label">User ID</label>
                                <input type="text" class="form-control" name="user_id" placeholder="Enter user ID to view their memories">
                            </div>
                            <button type="submit" class="btn btn-info">View User Memories</button>
                        </form>
                    </div>
                </div>
                
                <div class="card mt-4">
                    <div class="card-header">
                        <h3>🔍 Knowledge Search</h3>
                    </div>
                    <div class="card-body">
                        <form method="GET" action="/search-knowledge">
                            <div class="mb-3">
                                <input type="text" class="form-control" name="query" placeholder="Search knowledge..." value="{{ request.args.get('query', '') }}">
                            </div>
                            <button type="submit" class="btn btn-success">Search</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        
        {% if knowledge_results %}
        <div class="card mt-5">
            <div class="card-header">
                <h3>🗂️ Knowledge Base ({{ knowledge_results|length }} items)</h3>
            </div>
            <div class="card-body">
                {% for item in knowledge_results %}
                <div class="border-bottom pb-3 mb-3">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h6><span class="badge bg-secondary">{{ item.type }}</span> {{ item.key }}</h6>
                            <p class="mb-1">{{ item.value }}</p>
                            <small class="text-muted">Score: {{ "%.3f"|format(item.score or 0) }}</small>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
        
        {% if user_memories %}
        <div class="card mt-5">
            <div class="card-header">
                <h3>👤 User {{ user_id }} Memories</h3>
            </div>
            <div class="card-body">
                {% for memory in user_memories %}
                <div class="border-bottom pb-3 mb-3">
                    <h6><span class="badge bg-primary">{{ memory.type }}</span> {{ memory.key }}</h6>
                    <p class="mb-1">{{ memory.value }}</p>
                    <small class="text-muted">Scope: {{ memory.scope or 'user' }} | Score: {{ "%.3f"|format(memory.score or 0) }}</small>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>
    
    {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="toast-container position-fixed bottom-0 end-0 p-3">
                {% for message in messages %}
                <div class="toast show" role="alert">
                    <div class="toast-body bg-success text-white">{{ message }}</div>
                </div>
                {% endfor %}
            </div>
        {% endif %}
    {% endwith %}
</body>
</html>
"""

@app.route('/')
def home():
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    """Main admin interface"""
    knowledge_results = []
    user_memories = []
    user_id = request.args.get('user_id')
    query = request.args.get('query')
    
    # Search knowledge if query provided
    if query:
        try:
            resp = requests.get(f"{_get_orchestrator_url()}/v1/memories", params={"limit": 50}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                knowledge_results = data.get("memories", [])
                # Filter by query
                knowledge_results = [m for m in knowledge_results if query.lower() in m.get("key", "").lower() or query.lower() in m.get("value", "").lower()]
        except:
            flash("⚠️ Could not search knowledge base")
    
    # Get user memories if user_id provided  
    if user_id:
        try:
            # Get user memories using the proper API
            resp = requests.get(f"{_get_orchestrator_url()}/v1/memories", 
                               params={"user_id": user_id, "limit": 50}, timeout=10)
            if resp.status_code == 200:
                # This would return debug info about memories
                pass
        except:
            pass
    
    return render_template_string(ADMIN_TEMPLATE, 
                                knowledge_results=knowledge_results, 
                                user_memories=user_memories,
                                user_id=user_id)

@app.route('/add-knowledge', methods=['POST'])
def add_knowledge():
    """Add new knowledge to shared knowledge base"""
    try:
        data = {
            "type": request.form.get('type'),
            "key": request.form.get('key'),
            "value": request.form.get('value'),
            "ttl_days": 365,
            "source": "admin_web_interface"
        }
        
        resp = requests.post(f"{_get_orchestrator_url()}/v1/memories", json=data, timeout=10)
        
        if resp.status_code == 200:
            flash(f"✅ Knowledge added: {data['key']}")
        else:
            flash("❌ Failed to add knowledge")
            
    except Exception as e:
        flash(f"❌ Error: {str(e)}")
    
    return redirect(url_for('admin'))

@app.route('/search-knowledge')
def search_knowledge():
    """Redirect search to admin with query"""
    return redirect(url_for('admin', query=request.args.get('query', '')))

@app.route('/user-memories')
def user_memories():
    """Redirect to admin with user_id"""
    return redirect(url_for('admin', user_id=request.args.get('user_id', '')))

# ============ WEBSOCKET FOR REAL-TIME STREAMING ============

@app.route('/twilio-info', methods=['GET'])
def twilio_websocket_info():
    """Info endpoint for Twilio WebSocket - actual WebSocket handled separately"""
    return jsonify({
        "status": "WebSocket endpoint available",
        "url": "wss://voice.theinsurancedoctors.com/twilio",
        "protocol": "Twilio Media Streams",
        "features": ["Real-time audio streaming", "Sub-1s response times"]
    })

# ============ PHONE AI ENDPOINTS ============

def text_to_speech(text, voice_id=None):
    """Convert text to speech using ElevenLabs"""
    try:
        from elevenlabs import VoiceSettings
        import os
        import time
        
        client = _get_elevenlabs_client()
        if not client:
            logging.info("ElevenLabs client not available - using Twilio voice fallback")
            return None
            
        # Use provided voice_id or fall back to current_voice_id
        voice_to_use = voice_id or current_voice_id
        
        # Generate audio with ElevenLabs streaming API for faster response
        audio_stream = client.text_to_speech.stream(
            voice_id=voice_to_use,
            text=text,
            model_id="eleven_flash_v2_5",  # Faster model for streaming
            voice_settings=VoiceSettings(
                stability=VOICE_SETTINGS.get("stability", 0.71),
                similarity_boost=VOICE_SETTINGS.get("similarity_boost", 0.5),
                style=VOICE_SETTINGS.get("style", 0.0),
                use_speaker_boost=True
            )
        )
        
        # Create timestamp for unique filename
        timestamp = str(int(time.time()))
        filename = f"response_{timestamp}.mp3"
        
        # Ensure static/audio directory exists
        static_folder = app.static_folder or 'static'
        audio_dir = os.path.join(static_folder, 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        
        # Save streaming audio file - process chunks as they arrive
        audio_path = os.path.join(audio_dir, filename)
        try:
            with open(audio_path, 'wb') as f:
                bytes_written = 0
                for chunk in audio_stream:
                    if isinstance(chunk, (bytes, bytearray, memoryview)):
                        f.write(chunk)
                        bytes_written += len(chunk)
                    elif hasattr(chunk, 'encode'):
                        encoded = chunk.encode()
                        f.write(encoded)
                        bytes_written += len(encoded)
                    else:
                        data = bytes(chunk)
                        f.write(data)
                        bytes_written += len(data)
                
                # Ensure all streaming data is written to disk
                f.flush()
                os.fsync(f.fileno())
                logging.info(f"Streaming TTS: wrote {bytes_written} bytes to {filename}")
            
            # Verify file exists and has content before returning URL
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                # Return URL for Twilio to play
                from flask import url_for
                audio_url = url_for('static', filename=f'audio/{filename}', _external=True)
                logging.info(f"ElevenLabs TTS generated: {audio_url} ({os.path.getsize(audio_path)} bytes)")
                return audio_url
            else:
                logging.error(f"Audio file not properly saved: {audio_path}")
                return None
                
        except Exception as write_error:
            logging.error(f"Failed to write audio file {audio_path}: {write_error}")
            return None
        
    except Exception as e:
        logging.error(f"ElevenLabs TTS failed: {e}")
        return None

def get_personalized_greeting(user_id):
    """Get personalized greeting with user confirmation"""
    try:
        # Use HTTP memory service instead of direct database access
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # Search for any user name, not just "John"
        memories = mem_store.search("name", user_id=user_id, k=10)
        
        user_name = None
        # Look for user's name in stored memories
        for memory in memories:
            value = memory.get("value", {})
            if isinstance(value, dict):
                # Check for direct name field
                if "name" in value and value.get("relationship") not in ["friend", "wife", "husband"]:
                    user_name = value["name"]
                    break
                # Check for name in summary field
                elif "summary" in value and "name is" in value["summary"].lower():
                    summary = value["summary"]
                    # Extract name from patterns like "My name is Jack Peterson"
                    import re
                    name_match = re.search(r'name is (\w+(?:\s+\w+)?)', summary, re.IGNORECASE)
                    if name_match:
                        user_name = name_match.group(1)
                        break
        
        if user_name:
            return EXISTING_USER_GREETING.format(user_name=user_name)
            
    except Exception as e:
        logging.error(f"Error getting personalized greeting: {e}")
    
    # Default greeting for new or unknown callers with time-based greeting
    try:
        from datetime import datetime
        import pytz
        
        # Get current time (assuming Pacific Time for the business)
        pst = pytz.timezone('US/Pacific')
        current_time = datetime.now(pst)
        hour = current_time.hour
        
        if 5 <= hour < 12:
            time_greeting = "Good morning"
        elif 12 <= hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"
    except ImportError:
        # Fallback if pytz not available
        time_greeting = "Hello"
    
    return NEW_CALLER_GREETING.format(time_greeting=time_greeting)

def get_ai_response(user_id, message, call_sid=None):
    """Get AI response from NeuroSphere backend with conversation context"""
    try:
        # Keep it simple - no conversation history to avoid confusion
        # Just process the current message directly
        
        # Call FastAPI backend with user identification - this handles memory integration automatically
        conversation_history = call_sessions.get(call_sid, {}).get('conversation', [])
        
        logging.info(f"🔍 Calling FastAPI with user_id: {user_id} and message: {message}")
        
        # Prepare payload for FastAPI /v1/chat endpoint
        # Build messages array in the format FastAPI expects
        messages = []
        
        # Add recent conversation history
        if conversation_history:
            messages.extend(conversation_history[-6:])  # Last 6 messages for context
            
        # Add current user message
        messages.append({"role": "user", "content": message})
        
        payload = {
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 50
        }
        
        # Make request to FastAPI backend with user_id as query parameter
        try:
            orchestrator_url = _get_orchestrator_url()
            logging.info(f"🌐 Calling orchestrator at {orchestrator_url}/v1/chat with user_id={user_id}")
            response = requests.post(
                f"{orchestrator_url}/v1/chat",
                json=payload,
                params={"user_id": user_id, "thread_id": call_sid},  # Pass user_id and thread_id for memory 
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data.get("output", "I'm sorry, I couldn't process that.")
                logging.info(f"✅ FastAPI response: {ai_response}")
                return ai_response
            else:
                logging.error(f"FastAPI error: {response.status_code} - {response.text}")
                return "Hi! I'm Samantha from Peterson Family Insurance. I can help you with auto, home, life, or business insurance questions. What would you like to know?"
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Streaming request error: {e}")
            return "Hi, this is Samantha with Peterson Family Insurance. I'm here to help with your insurance needs - auto, home, life, or business coverage. What questions can I answer for you?"
    except Exception as e:
        logging.error(f"AI Response Error: {e}")
        return "Hello! I'm Samantha from Peterson Family Insurance. I'm here to help with all your insurance questions - auto, home, life, and business coverage. How can I assist you today?"

@app.route('/phone/incoming', methods=['POST'])
def handle_incoming_call():
    """Handle incoming phone calls from Twilio - Improved streaming version"""
    from_number = request.form.get('From')
    call_sid = request.form.get('CallSid')
    
    # Store call session with conversation history
    call_sessions[call_sid] = {
        'user_id': from_number,
        'call_count': 1,
        'conversation': []
    }
    
    logging.info(f"📞 Incoming call from {from_number} - Using improved streaming APIs")
    
    response = VoiceResponse()
    greeting = get_personalized_greeting(from_number)
    
    # Use improved ElevenLabs streaming for faster response
    audio_url = text_to_speech(greeting, VOICE_ID)
    if audio_url:
        # Play the generated audio file (with streaming optimizations)
        response.play(audio_url)
    else:
        # Fallback to Twilio voice if ElevenLabs fails
        response.say(greeting, voice='alice')
    
    # Gather user speech with optimized settings
    # Use absolute HTTPS URL and ensure action is called even without speech
    from flask import url_for
    gather = Gather(
        input='speech',
        timeout=8,  # Optimized timeout
        speech_timeout=3,  # Increased for reliability
        action=url_for('process_speech', _external=True),  # Absolute HTTPS URL
        actionOnEmptyResult=True,  # Call action even if no speech detected
        method='POST'
    )
    response.append(gather)
    
    # Fallback if no speech detected - RETRY instead of hangup
    response.say("I didn't catch that. Let me try again.")
    response.redirect('/phone/incoming')  # Retry the call instead of hanging up
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/phone/process-speech', methods=['POST'])
def process_speech():
    """Process speech input from caller"""
    # Log entry to confirm route is being hit
    logging.info(f"📞 /phone/process-speech route called - verifying Twilio webhook")
    
    speech_result = request.form.get('SpeechResult')
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    
    logging.info(f"🎤 Speech from {from_number} (CallSid: {call_sid}): '{speech_result}'")
    
    if not speech_result:
        response = VoiceResponse()
        # Use ElevenLabs for error message too
        try:
            error_audio = text_to_speech("Sorry, I didn't catch that. Could you repeat?")
            if error_audio:
                error_path = f"static/audio/error_{call_sid}.mp3"
                with open(error_path, "wb") as f:
                    for chunk in error_audio:
                        f.write(chunk)
                error_url = f"https://{request.host}/{error_path}"
                response.play(error_url)
            else:
                response.say("I didn't catch that. Could you please repeat?")
        except Exception as e:
            logging.error(f"Error TTS Error: {e}")
            response.say("I didn't catch that. Could you please repeat?")
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=3,
            action='/phone/process-speech',
            method='POST'
        )
        response.append(gather)
        
        # If still no speech, offer transfer or retry
        response.say("I'm having trouble hearing you. Let me transfer you to someone who can help.")
        response.dial('+19497071290')  # Transfer to main number
        return str(response), 200, {'Content-Type': 'text/xml'}
    
    logging.info(f"🎤 Speech from {from_number}: {speech_result}")
    
    # Save new information to memory before generating response
    user_id = from_number
    try:
        from app.http_memory import HTTPMemoryStore
        from app.packer import should_remember, extract_carry_kit_items
        
        # Check if this message contains information worth remembering
        if should_remember(speech_result):
            from app.http_memory import HTTPMemoryStore
            mem_store = HTTPMemoryStore()
            carry_kit_items = extract_carry_kit_items(speech_result)
            
            for item in carry_kit_items:
                try:
                    memory_id = mem_store.write(
                        item["type"],
                        item["key"], 
                        item["value"],
                        user_id=user_id,
                        scope="user",
                        ttl_days=item.get("ttl_days", 365)
                    )
                    logging.info(f"💾 Stored memory: {item['type']}:{item['key']} -> {memory_id}")
                except Exception as e:
                    logging.error(f"Failed to store memory item: {e}")
        
        # Also look for specific information that should be learned
        message_lower = speech_result.lower()
        mem_store = HTTPMemoryStore()
        
        # Store shopping/task information
        if any(phrase in message_lower for phrase in ["need to get", "going to", "have to get", "need from"]):
            if any(place in message_lower for place in ["costco", "store", "shopping", "market"]):
                mem_store.write(
                    "task",
                    f"shopping_task_{hash(speech_result) % 1000}",
                    {
                        "summary": f"John needs to: {speech_result}",
                        "context": "shopping/errands",
                        "task_type": "shopping"
                    },
                    user_id=user_id,
                    scope="user"
                )
                logging.info(f"💾 Stored shopping task: {speech_result}")
        
        # Food preferences (like pizza)
        if any(phrase in message_lower for phrase in ["i like", "my favorite", "love", "prefer"]):
            if any(food in message_lower for food in ["pizza", "mushroom", "pepperoni", "cheese", "sausage"]):
                mem_store.write(
                    "preference",
                    f"food_preference_{hash(speech_result) % 1000}",
                    {
                        "summary": f"John likes {speech_result.replace('I like', '').replace('my favorite', '').strip()}",
                        "category": "food",
                        "preference_type": "food_preference"
                    },
                    user_id=user_id,
                    scope="user"
                )
                logging.info(f"💾 Stored food preference: {speech_result}")
        
        # Store any mention of plans or activities
        if any(phrase in message_lower for phrase in ["going to", "planning to", "need to", "have to"]):
            mem_store.write(
                "task",
                f"activity_plan_{hash(speech_result) % 1000}",
                {
                    "summary": speech_result[:200],
                    "context": "plans and activities",
                    "task_type": "general"
                },
                user_id=user_id,
                scope="user"
            )
            logging.info(f"💾 Stored activity plan: {speech_result}")
        
        # Birthday information
        if ("birthday" in message_lower or "born" in message_lower):
            if "jack" in message_lower or "colin" in message_lower:
                name = "Jack" if "jack" in message_lower else "Colin"
                mem_store.write(
                    "fact",
                    f"{name.lower()}_birthday_inquiry",
                    {
                        "summary": f"User asked about {name}'s birthday",
                        "context": speech_result,
                        "name": name,
                        "relationship": "son"
                    },
                    user_id=user_id,
                    scope="user"
                )
                logging.info(f"💾 Stored birthday inquiry for {name}")
        
        # Look for new family information  
        if any(phrase in message_lower for phrase in ["my son", "my daughter", "my child", "brother-in-law", "my brother"]):
            mem_store.write(
                "person",
                f"family_info_{hash(speech_result) % 1000}",
                {
                    "summary": speech_result[:200],
                    "context": "family information shared during call",
                    "relationship": "family"
                },
                user_id=user_id,
                scope="user"
            )
            logging.info(f"💾 Stored family information: {speech_result}")
            
        # Look for names being shared
        if any(phrase in message_lower for phrase in ["name is", "called", "his name", "her name"]):
            mem_store.write(
                "person",
                f"name_info_{hash(speech_result) % 1000}",
                {
                    "summary": speech_result[:200],
                    "context": "name shared during call",
                    "info_type": "name_reference"
                },
                user_id=user_id,
                scope="user"
            )
            logging.info(f"💾 Stored name information: {speech_result}")
            
        # Look for books/reading interests
        if any(phrase in message_lower for phrase in ["book", "read", "reading", "novel", "author"]):
            mem_store.write(
                "preference",
                f"reading_interest_{hash(speech_result) % 1000}",
                {
                    "summary": speech_result[:200],
                    "context": "books and reading interests",
                    "preference_type": "reading"
                },
                user_id=user_id,
                scope="user"
            )
            logging.info(f"💾 Stored reading interest: {speech_result}")
                    
    except Exception as e:
        logging.error(f"Memory saving error: {e}")
    
    # Get AI response from NeuroSphere with conversation context
    ai_response = get_ai_response(user_id, speech_result, call_sid)
    
    # Store conversation history
    if call_sid in call_sessions:
        call_sessions[call_sid]['conversation'].extend([
            {"role": "user", "content": speech_result},
            {"role": "assistant", "content": ai_response}
        ])
        # Keep only last 10 exchanges (20 messages)
        if len(call_sessions[call_sid]['conversation']) > 20:
            call_sessions[call_sid]['conversation'] = call_sessions[call_sid]['conversation'][-20:]
    
    logging.info(f"🤖 AI Response: {ai_response}")
    
    # Generate TwiML response with Twilio's built-in voice
    response = VoiceResponse()
    response.say(ai_response, voice='alice')
    
    # Skip the "anything else" question - just wait for user input
    
    # Use absolute HTTPS URL and ensure action is called even without speech
    gather = Gather(
        input='speech',
        timeout=8,  # Reduced timeout  
        speech_timeout=3,  # Reliable speech detection
        action=url_for('process_speech', _external=True),  # Absolute HTTPS URL
        actionOnEmptyResult=True,  # Call action even if no speech detected
        method='POST'
    )
    response.append(gather)
    
    # If no response, end call politely without hanging up abruptly
    response.say("Thanks for calling Peterson Family Insurance! Have a great day!")
    response.pause(length=1)  # Brief pause before ending naturally
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/phone/status', methods=['POST'])
def call_status():
    """Handle call status updates"""
    call_sid = request.form.get('CallSid')
    call_status = request.form.get('CallStatus')
    from_number = request.form.get('From')
    
    logging.info(f"📞 Call {call_sid} from {from_number}: {call_status}")
    
    # Clean up session when call ends
    if call_status in ['completed', 'failed', 'busy', 'no-answer']:
        call_sessions.pop(call_sid, None)
    
    return '', 200

@app.route('/phone/test')
def test_phone_system():
    """Test endpoint to verify phone system is working"""
    return jsonify({
        "status": "Phone AI system ready",
        "endpoints": {
            "incoming": "/phone/incoming",
            "speech": "/phone/process-speech", 
            "status": "/phone/status"
        },
        "twilio_configured": bool(_get_config()["twilio_account_sid"]),
        "elevenlabs_configured": bool(_get_config()["elevenlabs_api_key"]),
        "backend_url": _get_backend_url()
    })

@app.route('/static/audio/<path:filename>')
def serve_audio(filename):
    """Serve audio files with proper headers for external access"""
    import os
    try:
        audio_path = os.path.join('static/audio', filename)
        if os.path.exists(audio_path):
            def generate():
                with open(audio_path, 'rb') as f:
                    data = f.read(1024)
                    while data:
                        yield data
                        data = f.read(1024)
            
            return Response(generate(), mimetype='audio/mpeg', 
                          headers={'Content-Disposition': f'inline; filename={filename}'})
        else:
            logging.error(f"Audio file not found: {audio_path}")
            return "Audio file not found", 404
    except Exception as e:
        logging.error(f"Error serving audio file {filename}: {e}")
        return "Audio file error", 500

# ============ ADMIN API ENDPOINTS ============

@app.route('/admin-control')
def admin_control():
    """Serve the admin control interface"""
    try:
        import os
        file_path = os.path.join(os.path.dirname(__file__), 'static', 'admin-control.html')
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Admin control interface not found", 404


@app.route('/admin.html')
def admin_html():
    """Serve admin.html directly for external access"""
    return app.send_static_file('admin.html')

@app.route('/test-voice', methods=['POST'])
def test_voice():
    """Test voice configuration"""
    try:
        data = request.get_json()
        voice_id = data.get('voice_id', VOICE_ID)
        text = data.get('text', "This is a test of the voice settings.")
        
        # Generate test audio
        audio = text_to_speech(text, voice_id)
        if audio:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Voice generation failed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/test-ai', methods=['POST'])
def test_ai():
    """Test AI response"""
    try:
        data = request.get_json()
        message = data.get('message', 'Hello')
        
        response = get_ai_response("test-user", message)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

@app.route('/update-voice', methods=['POST'])
def update_voice():
    """Update voice settings"""
    global VOICE_ID, VOICE_SETTINGS
    try:
        data = request.get_json()
        VOICE_ID = data.get('voice_id', VOICE_ID)
        VOICE_SETTINGS['stability'] = float(data.get('stability', 0.71))
        VOICE_SETTINGS['similarity_boost'] = float(data.get('clarity', 0.5))
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/update-personality', methods=['POST'])
def update_personality():
    """Update AI personality settings"""
    global AI_INSTRUCTIONS, MAX_TOKENS
    try:
        data = request.get_json()
        AI_INSTRUCTIONS = data.get('instructions', AI_INSTRUCTIONS)
        MAX_TOKENS = int(data.get('max_tokens', MAX_TOKENS))
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/update-greetings', methods=['POST'])
def update_greetings():
    """Update custom greeting templates"""
    global EXISTING_USER_GREETING, NEW_CALLER_GREETING
    try:
        data = request.get_json()
        EXISTING_USER_GREETING = data.get('existing_user_greeting', EXISTING_USER_GREETING)
        NEW_CALLER_GREETING = data.get('new_caller_greeting', NEW_CALLER_GREETING)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/update-routing', methods=['POST'])
def update_routing():
    """Update call routing settings"""
    global ROUTING_NUMBERS, ROUTING_KEYWORDS
    try:
        data = request.get_json()
        ROUTING_NUMBERS['billing'] = data.get('billing_number', ROUTING_NUMBERS['billing'])
        ROUTING_NUMBERS['claims'] = data.get('claims_number', ROUTING_NUMBERS['claims'])
        ROUTING_NUMBERS['support'] = data.get('support_number', ROUTING_NUMBERS['support'])
        
        # Update keywords
        if data.get('billing_keywords'):
            ROUTING_KEYWORDS['billing'] = [kw.strip() for kw in data.get('billing_keywords', '').split(',') if kw.strip()]
        if data.get('claims_keywords'):
            ROUTING_KEYWORDS['claims'] = [kw.strip() for kw in data.get('claims_keywords', '').split(',') if kw.strip()]
        if data.get('transfer_keywords'):
            ROUTING_KEYWORDS['transfer'] = [kw.strip() for kw in data.get('transfer_keywords', '').split(',') if kw.strip()]
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/update-llm', methods=['POST'])
def update_llm():
    """Update LLM backend endpoint dynamically with cross-process synchronization"""
    try:
        data = request.get_json()
        new_url = data.get('llm_base_url')
        
        if not new_url:
            return jsonify({"success": False, "error": "No LLM base URL provided"})
        
        # Validate URL format
        if not new_url.startswith('https://'):
            return jsonify({"success": False, "error": "LLM URL must start with https://"})
        
        # Update environment variable for immediate effect in Flask process
        os.environ['LLM_BASE_URL'] = new_url
        
        # Update config.json file for cross-process consistency
        config_file = "config.json"
        try:
            # Read current config
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            # Update LLM base URL
            config_data['llm_base_url'] = new_url
            from datetime import datetime
            config_data['last_updated'] = datetime.now().strftime("%Y-%m-%d")
            
            # Write updated config atomically
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='.', prefix='config_', suffix='.tmp') as tmp_f:
                json.dump(config_data, tmp_f, indent=2)
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
                temp_filename = tmp_f.name
            
            # Atomic move to replace original config
            os.rename(temp_filename, config_file)
            
            logging.info(f"✅ Updated config.json with new LLM endpoint: {new_url}")
            
        except Exception as config_error:
            logging.error(f"Failed to update config.json: {config_error}")
            # Don't fail the whole request if config file update fails
            # Environment variable update still provides immediate effect for Flask
        
        # Log the change
        logging.info(f"✅ LLM backend updated to: {new_url} (env + config.json)")
        
        return jsonify({
            "success": True, 
            "message": f"LLM backend updated to {new_url} (both processes will use new endpoint)",
            "llm_endpoint": new_url
        })
        
    except Exception as e:
        logging.error(f"Failed to update LLM backend: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/admin-status')
def admin_status():
    """Get current system status and all configuration sources"""
    try:
        from app.http_memory import HTTPMemoryStore
        from config_loader import get_all_config, get_internal_setting, get_internal_ports
        
        mem_store = HTTPMemoryStore()
        
        # Count total memories (simplified)
        memories = mem_store.search("", k=1000)
        memory_count = len(memories)
        
        # Get all configuration from all sources
        all_config = get_all_config()
        internal_ports = get_internal_ports()
        
        return jsonify({
            "status": "healthy",
            "memory_count": memory_count,
            "voice_id": VOICE_ID,
            "max_tokens": MAX_TOKENS,
            "model": _get_config()["llm_model"],
            "llm_endpoint": os.environ.get("LLM_BASE_URL", _get_config()["llm_base_url"]),
            "configuration": {
                "sources": {
                    "environment_variables": {k: v for k, v in all_config.items() if k.startswith('env.')},
                    "config_json": {k: v for k, v in all_config.items() if k.startswith('config.')},
                    "config_internal": {k: v for k, v in all_config.items() if k.startswith('internal.')}
                },
                "summary": {
                    "llm_base_url": _get_config()["llm_base_url"],
                    "llm_model": _get_config()["llm_model"],
                    "server_url": _get_config()["server_url"],
                    "environment": all_config.get('config.environment', 'unknown'),
                    "version": all_config.get('config.version', 'unknown'),
                    "ports": internal_ports
                }
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "model": _get_config()["llm_model"] if _get_config() else "unknown",
            "memory_count": "Error",
            "voice_id": VOICE_ID,
            "max_tokens": MAX_TOKENS
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
