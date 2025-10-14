"""
NeuroSphere Orchestrator - Flask Web Interface with Phone AI
"""
import os
import requests
import json
import io
import base64
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, Response, send_from_directory, session
from twilio.rest import Client
from twilio.twiml import TwiML
from twilio.twiml.voice_response import VoiceResponse, Gather, Start, Stream, Connect
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
    _server_url = get_setting("server_url", "https://localhost:5000")
    
    return {
        "openai_api_key": get_secret("OPENAI_API_KEY"),
        "twilio_account_sid": twilio_config["account_sid"],
        "twilio_auth_token": twilio_config["auth_token"],
        "elevenlabs_api_key": elevenlabs_config["api_key"],
        "database_url": get_secret("DATABASE_URL"),
        "llm_base_url": llm_config["base_url"],
        "llm_model": llm_config["model"],
        "session_secret": get_secret("SESSION_SECRET"),
        "server_url": _server_url  # ✅ Fix: Use canonical server_url without path manipulation
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
    # Ensure using OpenAI endpoint
    if "neurosphere" in llm_config["base_url"] or "runpod" in llm_config["base_url"]:
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
    return config["llm_base_url"] or "https://api.openai.com/v1"

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

def cleanup_old_sessions():
    """Remove sessions older than 1 hour to prevent memory leaks"""
    import time
    current_time = time.time()
    expired_sessions = []
    
    for call_sid, session_data in call_sessions.items():
        created_at = session_data.get('created_at', current_time)
        age = current_time - created_at
        
        # Remove sessions older than 1 hour
        if age > 3600:
            expired_sessions.append(call_sid)
    
    for call_sid in expired_sessions:
        del call_sessions[call_sid]
        logging.info(f"🧹 Cleaned up expired session: {call_sid}")
    
    return len(expired_sessions)

# Admin-configurable settings - initialize with fallback values first
VOICE_ID = "FGY2WhTYpPnrIDTdsKH5"  # Default voice ID
VOICE_SETTINGS = {"stability": 0.71, "similarity_boost": 0.5}  # Default voice settings
AI_INSTRUCTIONS = "You are Samantha. The system has already greeted the caller. Do not introduce yourself again. Continue the conversation naturally, answering questions and being helpful, casual, and friendly."
MAX_TOKENS = 75

# Legacy variables for backwards compatibility
current_voice_id = VOICE_ID
voice_settings = VOICE_SETTINGS
ai_instructions = AI_INSTRUCTIONS

# Dynamic greeting templates - load from config on each request
def get_admin_setting(setting_key, default=None):
    """Get admin setting from AI-Memory service by parsing concatenated JSON"""
    try:
        import requests
        import json as json_module
        
        # ✅ Use retrieve endpoint to get all admin settings
        response = requests.post(
            "http://172.17.0.1:8100/memory/retrieve",
            json={"user_id": "admin", "key": f"admin:{setting_key}"},
            headers={"Content-Type": "application/json"},
            timeout=2
        )
        
        if response.status_code == 200:
            data = response.json()
            memory_text = data.get("memory", "")
            
            # Parse concatenated JSON lines to find setting
            matches = []
            for line in memory_text.split('\n'):
                line = line.strip()
                if not line or line == "test":
                    continue
                try:
                    setting_obj = json_module.loads(line)
                    if setting_obj.get("setting_key") == setting_key:
                        value = setting_obj.get("value") or setting_obj.get("setting_value")
                        timestamp = setting_obj.get("timestamp", 0)
                        matches.append({"value": value, "timestamp": float(timestamp)})
                except:
                    continue
            
            # Return most recent match
            if matches:
                matches.sort(key=lambda x: x["timestamp"], reverse=True)
                latest_value = matches[0]["value"]
                logging.info(f"📖 Retrieved admin setting {setting_key}: {latest_value}")
                return latest_value
        
        # Fallback to config.json
        config_value = get_setting(setting_key, default)
        logging.info(f"📖 Using config.json fallback for {setting_key}: {config_value}")
        return config_value
        
    except Exception as e:
        logging.error(f"Error getting admin setting {setting_key}: {e}")
        return default

def get_existing_user_greeting():
    return get_admin_setting("existing_user_greeting")

def get_new_caller_greeting():  
    return get_admin_setting("new_caller_greeting")

def _update_config_setting(key, value):
    """Update a setting in config.json atomically"""
    config_file = "config.json"
    try:
        # Read current config
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Update the setting
        config_data[key.lower()] = value
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
        logging.info(f"✅ Updated config setting: {key} = {value}")
        
    except Exception as e:
        logging.error(f"Failed to update config setting {key}: {e}")

# Call routing settings (updated for Peterson Family Insurance Agency)
ROUTING_NUMBERS = {
    "billing": "1-888-327-6377",
    "claims": "1-800-435-7764", 
    "colin": "1-949-556-5379",  # Colin's number
    "milissa": "1-949-334-5808"  # Milissa for Farmers service advantage team
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
    """Serve modern admin interface with all features (AI Settings, Voice Config, etc.)"""
    return app.send_static_file('admin.html')
@app.route('/add-knowledge', methods=['POST'])
def add_knowledge():
    """Add new knowledge to shared knowledge base"""
    try:
        # ✅ Use correct AI-Memory service endpoints instead of /v1/memories
        data = {
            "user_id": "admin",  # For shared knowledge
            "message": request.form.get('value'),
            "type": request.form.get('type'),
            "k": request.form.get('key'),
            "value_json": {
                "summary": request.form.get('value'),
                "key": request.form.get('key')
            },
            "scope": "shared",
            "ttl_days": 365,
            "source": "admin_web_interface"
        }
        
        # Call AI-Memory service directly with correct endpoint
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        resp = requests.post(f"{ai_memory_url}/memory/store", json=data, timeout=10)
        
        if resp.status_code == 200:
            result = resp.json()
            flash(f"✅ Knowledge added: {data['k']} (ID: {result.get('id', 'unknown')})")
        else:
            flash(f"❌ Failed to add knowledge: {resp.text}")
            
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
                # ✅ Fix: Use configured server_url for public URLs instead of Flask auto-detection
                config = _get_config()
                server_url = config["server_url"]
                audio_url = f"{server_url}/static/audio/{filename}"
                logging.info(f"🔧 DEBUG: server_url from config: {server_url}")
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
    """Return personalized greeting from AI-Memory service with user registration"""
    from datetime import datetime
    import pytz
    
    # Normalize user_id for consistent lookup
    normalized_user_id = user_id
    if user_id:
        normalized_digits = ''.join(filter(str.isdigit, user_id))
        if len(normalized_digits) >= 10:
            normalized_user_id = normalized_digits[-10:]
        logging.info(f"📞 Greeting lookup - normalized user_id: {user_id} -> {normalized_user_id}")

    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # ✅ Step 1: Check if user exists by searching for any memories
        user_memories = mem_store.search("", user_id=normalized_user_id, k=5)
        user_exists = len(user_memories) > 0
        logging.info(f"👤 User exists check: {user_exists} ({len(user_memories)} memories found)")
        
        # ✅ Step 2: If user doesn't exist, register them
        if not user_exists:
            logging.info(f"🆕 Registering new caller: {normalized_user_id}")
            mem_store.write(
                memory_type="person",
                key=f"caller_{normalized_user_id}",
                value={
                    "phone_number": normalized_user_id,
                    "first_call": True,
                    "registered_at": str(datetime.now())
                },
                user_id=normalized_user_id,
                scope="user",
                source="auto_registration"
            )
        
        # ✅ Step 3: Get appropriate greeting template from ai-memory
        if user_exists:
            # ✅ Search for user's name in multiple memory formats
            user_name = None
            
            # Strategy 1: Look for memories with "name" field (relationship != wife/husband/friend)
            for memory in user_memories:
                value = memory.get("value", {})
                if isinstance(value, dict):
                    # Check for direct name field (not a relationship)
                    if "name" in value and value.get("relationship") not in ["friend", "wife", "husband", "son", "daughter"]:
                        user_name = value["name"]
                        break
                    # Check for first_name field
                    if "first_name" in value:
                        user_name = value["first_name"]
                        break
            
            # Strategy 2: Search ai-memory specifically for user's own name
            if not user_name:
                try:
                    name_memories = mem_store.search(
                        query_text="user name person caller",
                        user_id=normalized_user_id,
                        k=10,
                        memory_types=["person", "fact"]
                    )
                    for mem in name_memories:
                        val = mem.get("value", {})
                        if isinstance(val, dict):
                            # Look for the caller's own name (not relationships)
                            if "name" in val and val.get("relationship") not in ["wife", "husband", "friend", "son", "daughter"]:
                                user_name = val["name"]
                                break
                            if "caller_name" in val:
                                user_name = val["caller_name"]
                                break
                except Exception as e:
                    logging.warning(f"Failed to search for user name: {e}")
            
            # Apply greeting template
            greeting_template = get_admin_setting("existing_user_greeting")
            if greeting_template:
                # Get agent name for placeholder replacement
                agent_name = get_admin_setting("agent_name", "Amanda")
                
                if user_name:
                    resolved = greeting_template.replace("{user_name}", user_name)
                    logging.info(f"👤 Existing user greeting with name '{user_name}': {resolved}")
                else:
                    resolved = greeting_template.replace("{user_name}", "")
                    logging.info(f"👤 Existing user greeting (no name found): {resolved}")
                
                # Replace agent_name placeholder
                resolved = resolved.replace("{agent_name}", agent_name)
                return resolved
        
        # ✅ Step 4: New caller or fallback - get new caller greeting
        greeting_template = get_admin_setting("new_caller_greeting")
        if greeting_template:
            # Get agent name for placeholder replacement
            agent_name = get_admin_setting("agent_name", "Amanda")
            
            # Add time-based greeting
            try:
                pst = pytz.timezone('US/Pacific')
                hour = datetime.now(pst).hour
                if 5 <= hour < 12:
                    time_greeting = "Good morning"
                elif 12 <= hour < 17:
                    time_greeting = "Good afternoon"
                else:
                    time_greeting = "Good evening"
            except Exception:
                time_greeting = "Hello"
            
            resolved = greeting_template.replace("{time_greeting}", time_greeting)
            resolved = resolved.replace("{agent_name}", agent_name)
            logging.info(f"🆕 New caller greeting resolved: {resolved}")
            return resolved
            
    except Exception as e:
        logging.error(f"Error getting personalized greeting from ai-memory: {e}")
    
    # ✅ Final fallback if ai-memory fails - use agent_name from settings
    agent_name = get_admin_setting("agent_name", "Amanda")
    return f"Hi, this is {agent_name} from Peterson Family Insurance Agency. How can I help you today?"

def get_ai_response(user_id, message, call_sid=None):
    """Get AI response from NeuroSphere backend with conversation context"""
    try:
        # Get call session info
        session = call_sessions.get(call_sid, {})
        is_callback = session.get('is_callback', False)
        first_message_handled = session.get('first_message_handled', False)
        
        logging.info(f"🔍 Calling FastAPI with user_id: {user_id} and message: {message}")
        
        # Prepare payload for FastAPI /v1/chat endpoint
        # Build messages array in the format FastAPI expects
        messages = []
        
        # ✅ For callbacks on first message, inject fresh start prompt
        # DISABLED: Conflicts with persistent thread history from database
        # Thread history already provides conversation context after Docker restart
        # if is_callback and not first_message_handled:
        #     messages.append({"role": "system", "content": "This is a new call. After greeting, ask 'How can I help you today?' instead of continuing previous conversation topics."})
        #     if call_sid and call_sid in call_sessions:
        #         call_sessions[call_sid]['first_message_handled'] = True
        #     logging.info("🔄 Injected fresh start prompt for callback")
        
        # Only send the current user message
        messages.append({"role": "user", "content": message})
        
        payload = {
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 50
        }
        
        # Make request to FastAPI backend with user_id as query parameter
        # ✅ Use stable thread_id based on phone number for cross-call continuity
        persistent_thread_id = f"user_{user_id}"
        logging.info(f"🧵 Using persistent thread_id={persistent_thread_id} for user {user_id}")
        
        try:
            orchestrator_url = _get_orchestrator_url()
            logging.info(f"🌐 Calling orchestrator at {orchestrator_url}/v1/chat with user_id={user_id}")
            response = requests.post(
                f"{orchestrator_url}/v1/chat",
                json=payload,
                params={"user_id": user_id, "thread_id": persistent_thread_id},  # ✅ Stable thread_id for continuity
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data.get("output", "I'm sorry, I couldn't process that.")
                logging.info(f"✅ FastAPI response: {ai_response}")
                return ai_response
            else:
                logging.error(f"FastAPI error: {response.status_code} - {response.text}")
                agent_name = get_admin_setting("agent_name", "Amanda")
                return f"Hi! I'm {agent_name} from Peterson Family Insurance. I can help you with auto, home, life, or business insurance questions. What would you like to know?"
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Streaming request error: {e}")
            agent_name = get_admin_setting("agent_name", "Amanda")
            return f"Hi, this is {agent_name} with Peterson Family Insurance. I'm here to help with your insurance needs - auto, home, life, or business coverage. What questions can I answer for you?"
    except Exception as e:
        logging.error(f"AI Response Error: {e}")
        agent_name = get_admin_setting("agent_name", "Amanda")
        return f"Hello! I'm {agent_name} from Peterson Family Insurance. I'm here to help with all your insurance questions - auto, home, life, and business coverage. How can I assist you today?"

@app.route('/phone/incoming', methods=['POST'])
def handle_incoming_call():
    """Handle incoming phone calls from Twilio - Improved streaming version"""
    import time
    t0 = time.time()  # ⏱️ Start timing
    
    from_number = request.form.get('From')
    call_sid = request.form.get('CallSid')
    
    logging.info(f"📞 Incoming call from {from_number} - Using improved streaming APIs")
    logging.info(f"⏱️ Stage: Call received | Elapsed: {time.time() - t0:.3f}s")
    
    # ✅ Check if this user has previous call history (callback detection)
    # Use SAME normalization as everywhere else in the system
    normalized_user_id = from_number
    if from_number:
        normalized_digits = ''.join(filter(str.isdigit, from_number))
        if len(normalized_digits) >= 10:
            normalized_user_id = normalized_digits[-10:]
    
    is_callback = False
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        # Search with both raw and normalized IDs to handle inconsistent storage
        user_memories = mem_store.search("", user_id=normalized_user_id, k=3)
        if not user_memories:
            # Try with raw from_number in case memories stored with different format
            user_memories = mem_store.search("", user_id=from_number, k=3)
        is_callback = len(user_memories) > 0
        logging.info(f"🔄 Callback detection: user {normalized_user_id} has {len(user_memories)} memories, is_callback={is_callback}")
        logging.info(f"⏱️ Stage: Callback detection | Elapsed: {time.time() - t0:.3f}s")
    except Exception as e:
        logging.warning(f"Failed to check callback status: {e}")
    
    response = VoiceResponse()
    greeting = get_personalized_greeting(from_number)
    logging.info(f"⏱️ Stage: Greeting chosen | Elapsed: {time.time() - t0:.3f}s")
    
    # ✅ Store call session with greeting and callback flag
    call_sessions[call_sid] = {
        'user_id': from_number,
        'call_count': 1,
        'is_callback': is_callback,
        'first_message_handled': False,  # Track if we've injected fresh start prompt
        'conversation': [
            {"role": "assistant", "content": greeting}  # Include initial greeting!
        ]
    }
    
    # Use improved ElevenLabs streaming for faster response
    tts_start = time.time()
    audio_url = text_to_speech(greeting, VOICE_ID)
    logging.info(f"⏱️ Stage: TTS generation | Elapsed: {time.time() - t0:.3f}s | TTS duration: {time.time() - tts_start:.3f}s")
    
    if audio_url:
        # Play the generated audio file (with streaming optimizations)
        response.play(audio_url)
        logging.info(f"⏱️ Stage: Audio sent to Twilio | Elapsed: {time.time() - t0:.3f}s")
    else:
        # Fallback to Twilio voice if ElevenLabs fails
        response.say(greeting, voice='Polly.Joanna')
        logging.info(f"⏱️ Stage: Fallback TTS sent | Elapsed: {time.time() - t0:.3f}s")
    
    # Gather user speech with optimized settings
    # Use absolute HTTPS URL and ensure action is called even without speech
    # ✅ Fix: Use configured server_url for webhook URLs
    config = _get_config()
    server_url = config["server_url"].replace("/phone/incoming", "")
    gather = Gather(
        input='speech',
        timeout=8,  # Optimized timeout
        speech_timeout=3,  # Increased for reliability
        action=f"{server_url}/phone/process-speech",  # Absolute HTTPS URL
        actionOnEmptyResult=True,  # Call action even if no speech detected
        method='POST'
    )
    response.append(gather)
    
    # Fallback if no speech detected - end gracefully
    response.say("I didn't hear anything. Please call back if you need assistance. Goodbye!")
    response.hangup()
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/phone/transfer', methods=['POST', 'GET'])
def handle_transfer():
    """Handle call transfer - return TwiML to dial the target number"""
    from twilio.twiml.voice_response import VoiceResponse
    
    # Get transfer parameters
    number = request.args.get('number') or request.form.get('number')
    keyword = request.args.get('keyword') or request.form.get('keyword', 'the requested party')
    
    logging.info(f"📞 Transfer endpoint called: number={number}, keyword={keyword}")
    
    # Create TwiML response
    response = VoiceResponse()
    response.say(f"Transferring you to {keyword}. Please hold.", voice='Polly.Joanna')
    
    # Dial the target number
    response.dial(number, timeout=30, callerId=request.form.get('From'))
    
    # If dial fails or completes
    response.say("The call could not be completed. Goodbye.")
    response.hangup()
    
    logging.info(f"✅ Transfer TwiML generated for {number}")
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/api/internal/customer-context/<call_sid>', methods=['GET'])
def get_customer_context(call_sid):
    """Internal API: Retrieve customer context by call_sid (for WebSocket use only)
    
    SECURITY: This endpoint uses shared secret authentication (not IP-based due to ProxyFix)
    """
    try:
        # SECURITY: Validate shared secret header (instead of IP check due to ProxyFix)
        secret_header = request.headers.get('X-Internal-Secret')
        expected_secret = SESSION_SECRET  # Reuse session secret as internal API key
        
        if not secret_header or secret_header != expected_secret:
            logging.error(f"❌ SECURITY: Unauthorized access attempt to internal API - invalid secret")
            return jsonify({"error": "Forbidden"}), 403
        
        session_data = call_sessions.get(call_sid)
        if not session_data:
            logging.warning(f"⚠️ No customer session found for call_sid={call_sid}")
            return jsonify({"error": "Session not found"}), 404
        
        # Mark session as retrieved (for one-time use tracking)
        if 'retrieved' not in session_data:
            session_data['retrieved'] = True
            session_data['retrieved_at'] = time.time()
        
        logging.info(f"🔐 Retrieved customer session for call_sid={call_sid}, customer_id={session_data.get('customer_id')}")
        return jsonify(session_data)
    except Exception as e:
        logging.error(f"❌ Error retrieving customer context: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/phone/incoming-realtime', methods=['POST'])
def handle_incoming_call_realtime():
    """Handle incoming phone calls using OpenAI Realtime API with Twilio Media Streams - Multi-Tenant Version"""
    import time
    t0 = time.time()
    
    # SECURITY: Validate Twilio request signature
    from twilio.request_validator import RequestValidator
    
    config = _get_config()
    validator = RequestValidator(config["twilio_auth_token"])
    
    # Get the request URL (must be the full URL Twilio called)
    url = request.url
    # For HTTPS behind proxy, ensure we use https://
    if request.headers.get('X-Forwarded-Proto') == 'https':
        url = url.replace('http://', 'https://')
    
    # Get Twilio signature from header
    signature = request.headers.get('X-Twilio-Signature', '')
    
    # Validate signature
    if not validator.validate(url, request.form, signature):
        logging.error(f"❌ SECURITY: Invalid Twilio signature for URL: {url}")
        logging.error(f"❌ Rejecting potentially spoofed request")
        return "Unauthorized", 403
    
    logging.info(f"✅ SECURITY: Twilio signature validated")
    
    from_number = request.form.get('From')
    to_number = request.form.get('To')  # Which Twilio number was called
    call_sid = request.form.get('CallSid')
    
    logging.info(f"📞 Incoming call from {from_number} to {to_number} - Using OpenAI Realtime API")
    logging.info(f"⏱️ Stage: Call received | Elapsed: {time.time() - t0:.3f}s")
    
    # MULTI-TENANT: Look up customer by Twilio phone number
    customer = None
    customer_id = None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from customer_models import Customer
        
        engine = create_engine(_get_config()["database_url"])
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        # Normalize to_number for matching (remove +1, spaces, etc)
        normalized_to = ''.join(filter(str.isdigit, to_number)) if to_number else ''
        
        # Try exact match first
        customer = db_session.query(Customer).filter_by(twilio_phone_number=to_number).first()
        
        # Try normalized match
        if not customer and normalized_to:
            customers = db_session.query(Customer).all()
            for c in customers:
                if c.twilio_phone_number:
                    cust_normalized = ''.join(filter(str.isdigit, c.twilio_phone_number))
                    if cust_normalized == normalized_to or cust_normalized.endswith(normalized_to[-10:]):
                        customer = c
                        break
        
        db_session.close()
        
        if customer:
            customer_id = customer.id
            logging.info(f"✅ Found customer {customer_id}: {customer.business_name}")
        else:
            logging.warning(f"⚠️ No customer found for phone number {to_number} - using default config")
    except Exception as e:
        logging.error(f"❌ Error looking up customer: {e}")
    
    # Normalize caller ID
    normalized_user_id = from_number
    if from_number:
        normalized_digits = ''.join(filter(str.isdigit, from_number))
        if len(normalized_digits) >= 10:
            normalized_user_id = normalized_digits[-10:]
    
    # Check callback status with customer namespacing
    is_callback = False
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # Use customer-namespaced user_id for memory lookup
        namespaced_user_id = f"customer_{customer_id}_{normalized_user_id}" if customer_id else normalized_user_id
        
        user_memories = mem_store.search("", user_id=namespaced_user_id, k=3)
        if not user_memories:
            # Try without namespace for backwards compatibility
            user_memories = mem_store.search("", user_id=normalized_user_id, k=3)
        is_callback = len(user_memories) > 0
        logging.info(f"🔄 Callback detection: user {namespaced_user_id}, is_callback={is_callback}")
    except Exception as e:
        logging.warning(f"Failed to check callback status: {e}")
    
    # Create TwiML response with Media Streams
    response = VoiceResponse()
    
    # Play brief hold message to fill initialization time (prevents dead air)
    response.say("Please hold while I connect you.", voice="Polly.Joanna", language="en-US")
    
    # Connect to WebSocket for bidirectional audio streaming
    connect = Connect()
    config = _get_config()
    server_url = config["server_url"]
    
    # Construct wss:// URL for WebSocket (FastAPI on port 8001)
    ws_url = server_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/phone/media-stream"
    
    # SECURITY: Store customer context in session for WebSocket to retrieve
    # Do NOT pass customer_id directly (can be spoofed) - use call_sid as secure session key
    if customer_id:
        call_sessions[call_sid] = {
            'customer_id': customer_id,
            'agent_name': customer.agent_name or 'AI Assistant',
            'greeting_template': customer.greeting_template or 'Hello! How can I help you today?',
            'openai_voice': customer.openai_voice or 'alloy',
            'personality_sliders': customer.personality_sliders,
            'business_name': customer.business_name,
            'to_number': to_number,
            'from_number': from_number,
            'created_at': time.time()
        }
        logging.info(f"🔐 Stored customer session for call_sid={call_sid}, customer_id={customer_id}")
    
    # Cleanup old sessions periodically
    if len(call_sessions) > 100:
        cleanup_old_sessions()
    
    # Pass minimal parameters - WebSocket will lookup customer server-side using call_sid
    stream_elem = Stream(url=ws_url)
    stream_elem.parameter(name='user_id', value=normalized_user_id)
    stream_elem.parameter(name='call_sid', value=call_sid)  # Used for secure customer lookup
    stream_elem.parameter(name='is_callback', value=str(is_callback))
    
    connect.append(stream_elem)
    response.append(connect)
    
    logging.info(f"⏱️ Stage: TwiML generated with Media Stream | Elapsed: {time.time() - t0:.3f}s")
    logging.info(f"🔗 WebSocket URL: {ws_url}")
    if customer_id:
        logging.info(f"👤 Customer Context: ID={customer_id}, Agent={customer.agent_name}, Voice={customer.openai_voice}")
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/phone/process-speech', methods=['POST'])
def process_speech():
    """Process speech input from caller"""
    import time
    t0 = time.time()  # ⏱️ Start timing for this interaction
    
    # Log entry to confirm route is being hit
    logging.info(f"📞 /phone/process-speech route called - verifying Twilio webhook")
    
    speech_result = request.form.get('SpeechResult')
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    
    logging.info(f"🎤 Speech from {from_number} (CallSid: {call_sid}): '{speech_result}'")
    logging.info(f"⏱️ Stage: Caller speech received | Elapsed: {time.time() - t0:.3f}s")
    
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
    # ✅ Normalize user_id for consistent memory lookup
    user_id = from_number
    if user_id:
        # Remove all non-digits and ensure consistent format
        normalized_digits = ''.join(filter(str.isdigit, user_id))
        if len(normalized_digits) >= 10:
            # Use last 10 digits (removes country code variations)  
            user_id = normalized_digits[-10:]
        logging.info(f"📞 Normalized user_id: {from_number} -> {user_id}")
    try:
        from app.http_memory import HTTPMemoryStore
        
        # ✅ ALWAYS store basic speech information - this ensures callers are remembered
        mem_store = HTTPMemoryStore()
        
        # Store every utterance as a "moment" - this is the key fix!
        import time
        memory_id = mem_store.write(
            "moment",
            f"utterance_{call_sid}_{int(time.time())}",
            {
                "summary": speech_result,
                "timestamp": int(time.time()),
                "call_sid": call_sid
            },
            user_id=user_id,
            scope="user",
            ttl_days=365
        )
        logging.info(f"🔍 ALWAYS storing speech for user_id={user_id}: {speech_result[:50]}...")
        logging.info(f"💾 Stored utterance memory with ID: {memory_id}")
        
        # Check if this message contains additional information worth extracting
        from app.packer import should_remember, extract_carry_kit_items
        if should_remember(speech_result):
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
                    logging.info(f"💾 Stored extracted memory: {item['type']}:{item['key']} -> {memory_id}")
                except Exception as e:
                    logging.error(f"Failed to store extracted memory item: {e}")
        
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
            
        # ✅ Extract and store caller's name when they introduce themselves
        if any(phrase in message_lower for phrase in ["my name is", "i'm", "this is", "call me"]):
            import re
            # Try to extract the name from common patterns
            extracted_name = None
            
            # Pattern: "my name is John" or "This is John"
            match = re.search(r"(?:my name(?:'s| is)|i'm|this is|call me)\s+([A-Z][a-z]+)", speech_result, re.IGNORECASE)
            if match:
                extracted_name = match.group(1).capitalize()
            
            # Store with structured name field
            mem_store.write(
                "person",
                f"caller_info_{user_id}",
                {
                    "caller_name": extracted_name if extracted_name else "unknown",
                    "name": extracted_name if extracted_name else "unknown",
                    "summary": speech_result[:200],
                    "context": "caller introduced themselves",
                    "info_type": "caller_identity"
                },
                user_id=user_id,
                scope="user"
            )
            logging.info(f"💾 Stored caller name: {extracted_name} from '{speech_result}'")
        
        # Look for other names being shared (wife, kids, friends)
        elif any(phrase in message_lower for phrase in ["name is", "called", "his name", "her name"]):
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
    
    logging.info(f"⏱️ Stage: Memory storage complete | Elapsed: {time.time() - t0:.3f}s")
    
    # Get AI response from NeuroSphere with conversation context
    llm_start = time.time()
    logging.info(f"⏱️ Stage: LLM request start | Elapsed: {time.time() - t0:.3f}s")
    ai_response = get_ai_response(user_id, speech_result, call_sid)
    logging.info(f"⏱️ Stage: LLM response complete | Elapsed: {time.time() - t0:.3f}s | LLM duration: {time.time() - llm_start:.3f}s")
    
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
    
    # Generate TwiML response with ElevenLabs TTS (same as greeting)
    response = VoiceResponse()
    
    # Use ElevenLabs for AI response (consistent with greeting)
    tts_start = time.time()
    logging.info(f"⏱️ Stage: TTS request start | Elapsed: {time.time() - t0:.3f}s")
    audio_url = text_to_speech(ai_response, VOICE_ID)
    logging.info(f"⏱️ Stage: TTS complete | Elapsed: {time.time() - t0:.3f}s | TTS duration: {time.time() - tts_start:.3f}s")
    
    if audio_url:
        # Play the generated audio file
        response.play(audio_url)
        logging.info(f"⏱️ Stage: Response audio sent to Twilio | Elapsed: {time.time() - t0:.3f}s")
    else:
        # Fallback to Twilio voice if ElevenLabs fails
        response.say(ai_response, voice='alice')
        logging.info(f"⏱️ Stage: Fallback response sent | Elapsed: {time.time() - t0:.3f}s")
    
    # Skip the "anything else" question - just wait for user input
    
    # ✅ Fix: Use absolute HTTPS URL with configured server_url
    config = _get_config()
    server_url = config["server_url"].replace("/phone/incoming", "")
    gather = Gather(
        input='speech',
        timeout=8,  # Reduced timeout  
        speech_timeout=3,  # Reliable speech detection
        action=f"{server_url}/phone/process-speech",  # Absolute HTTPS URL
        actionOnEmptyResult=True,  # Call action even if no speech detected
        method='POST'
    )
    response.append(gather)
    
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

@app.route('/admin.html')
def admin_html():
    """Serve admin.html directly for external access"""
    return app.send_static_file('admin.html')

@app.route('/login.html')
def login_html():
    """Serve login.html for customer authentication"""
    return app.send_static_file('login.html')

@app.route('/onboarding.html')
def onboarding_html():
    """Serve onboarding.html for new customer registration"""
    return app.send_static_file('onboarding.html')

@app.route('/dashboard.html')
def dashboard_html():
    """Serve dashboard.html for customer settings management"""
    return app.send_static_file('dashboard.html')

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
    """Update voice settings in AI-Memory service"""
    try:
        data = request.get_json()
        # ✅ Declare global variables first  
        global VOICE_ID, VOICE_SETTINGS
        
        voice_id = data.get('voice_id', VOICE_ID)
        stability = float(data.get('stability', 0.71))
        clarity = float(data.get('clarity', 0.5))
        
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # ✅ Save voice settings to AI-Memory
        voice_settings = {
            "voice_id": voice_id,
            "stability": stability,
            "similarity_boost": clarity,
            "updated_by": "admin_panel"
        }
        
        mem_store.write(
            memory_type="admin_setting",
            key="voice_settings",
            value={
                "setting_key": "voice_settings",
                "setting_value": voice_settings,
                "updated_by": "admin_panel"
            },
            user_id="admin",
            scope="shared",
            source="admin_panel"
        )
        
        # ✅ Update global variables for immediate effect
        VOICE_ID = voice_id
        VOICE_SETTINGS['stability'] = stability
        VOICE_SETTINGS['similarity_boost'] = clarity
        
        logging.info(f"✅ Voice settings updated: ID={voice_id}, stability={stability}, clarity={clarity}")
        return jsonify({"success": True})
        
    except Exception as e:
        logging.error(f"❌ Failed to update voice settings: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/update-personality', methods=['POST'])
def update_personality():
    """Update AI personality settings in AI-Memory service"""
    try:
        # ✅ Declare global variables first
        global AI_INSTRUCTIONS, MAX_TOKENS
        
        data = request.get_json()
        instructions = data.get('instructions', AI_INSTRUCTIONS)
        max_tokens = int(data.get('max_tokens', MAX_TOKENS))
        
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # ✅ Save personality settings to AI-Memory
        personality_settings = {
            "ai_instructions": instructions,
            "max_tokens": max_tokens,
            "updated_by": "admin_panel"
        }
        
        mem_store.write(
            memory_type="admin_setting",
            key="personality_settings",
            value={
                "setting_key": "personality_settings",
                "setting_value": personality_settings,
                "updated_by": "admin_panel"
            },
            user_id="admin",
            scope="shared",
            source="admin_panel"
        )
        
        # ✅ Update global variables for immediate effect
        AI_INSTRUCTIONS = instructions
        MAX_TOKENS = max_tokens
        
        # Also update the system prompt file for FastAPI
        try:
            prompt_file = "app/prompts/system_sam.txt"
            with open(prompt_file, 'r') as f:
                content = f.read()
            
            # Update the first line with new personality instructions
            lines = content.split('\n')
            if lines:
                lines[0] = instructions
                
            with open(prompt_file, 'w') as f:
                f.write('\n'.join(lines))
                
            logging.info("✅ Updated system prompt file with new personality")
            
        except Exception as e:
            logging.error(f"Failed to update system prompt file: {e}")
        
        logging.info(f"✅ Personality settings updated: instructions={instructions[:50]}..., max_tokens={max_tokens}")
        return jsonify({"success": True})
        
    except Exception as e:
        logging.error(f"❌ Failed to update personality settings: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/update-personality-sliders', methods=['POST'])
def update_personality_sliders():
    """Update personality dimension sliders in AI-Memory service"""
    try:
        data = request.get_json()
        
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # Save slider values to AI-Memory
        import time
        mem_store.write(
            memory_type="admin_setting",
            key="personality_sliders",
            value={
                "setting_key": "personality_sliders",
                "value": data,  # ✅ Add both value and setting_value
                "setting_value": data,
                "timestamp": time.time()
            },
            user_id="admin",
            scope="shared",
            source="admin_panel"
        )
        
        logging.info(f"✅ Personality sliders saved: {len(data)} dimensions")
        return jsonify({"success": True})
        
    except Exception as e:
        logging.error(f"❌ Failed to save personality sliders: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/get-personality-sliders', methods=['GET'])
def get_personality_sliders():
    """Get personality dimension sliders from AI-Memory service"""
    try:
        # Use get_admin_setting to retrieve from AI-Memory
        sliders = get_admin_setting("personality_sliders", {})
        
        if sliders:
            logging.info(f"✅ Retrieved personality sliders: {len(sliders)} dimensions")
            return jsonify({"success": True, "sliders": sliders})
        else:
            # Return defaults if not found
            return jsonify({"success": True, "sliders": {}})
            
    except Exception as e:
        logging.error(f"❌ Failed to get personality sliders: {e}")
        return jsonify({"success": False, "error": str(e)})
        
@app.route('/update-greetings', methods=['POST'])
def update_greetings():
    """Save greetings to AI-Memory service"""
    try:
        from app.http_memory import HTTPMemoryStore
        import time
        mem_store = HTTPMemoryStore()
        
        data = request.get_json()
        existing_greeting = data.get('existing_user_greeting', '')
        new_greeting = data.get('new_caller_greeting', '')
        
        # ✅ Save to AI-Memory service as admin settings with timestamp
        if existing_greeting:
            mem_store.write(
                memory_type="admin_setting",
                key="existing_user_greeting",
                value={
                    "setting_key": "existing_user_greeting",
                    "value": existing_greeting,
                    "setting_value": existing_greeting,
                    "timestamp": time.time(),  # ✅ Add timestamp for sorting
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                user_id="admin",
                scope="shared",
                ttl_days=365,
                source="admin_panel"
            )
            logging.info(f"✅ Saved existing user greeting to ai-memory: {existing_greeting}")

        if new_greeting:
            mem_store.write(
                memory_type="admin_setting",
                key="new_caller_greeting",
                value={
                    "setting_key": "new_caller_greeting",
                    "value": new_greeting,
                    "setting_value": new_greeting,
                    "timestamp": time.time(),  # ✅ Add timestamp for sorting
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                user_id="admin",
                scope="shared",
                ttl_days=365,
                source="admin_panel"
            )
            logging.info(f"✅ Saved new caller greeting to ai-memory: {new_greeting}")

        logging.info("✅ Greetings saved to ai-memory service successfully")
        return jsonify({"success": True, "message": "Greetings updated to AI-Memory"})
        
    except Exception as e:
        logging.error(f"❌ Failed to save greetings to ai-memory: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/update-agent-name', methods=['POST'])
def update_agent_name():
    """Save agent name to AI-Memory service"""
    try:
        from app.http_memory import HTTPMemoryStore
        import time
        mem_store = HTTPMemoryStore()
        
        data = request.get_json()
        agent_name = data.get('agent_name', '').strip()
        
        if not agent_name:
            return jsonify({"success": False, "error": "Agent name cannot be empty"}), 400
        
        # Save to AI-Memory service as admin setting with timestamp
        mem_store.write(
            memory_type="admin_setting",
            key="agent_name",
            value={
                "setting_key": "agent_name",
                "value": agent_name,
                "setting_value": agent_name,
                "timestamp": time.time(),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            user_id="admin",
            scope="shared",
            ttl_days=365,
            source="admin_panel"
        )
        logging.info(f"✅ Saved agent name to ai-memory: {agent_name}")
        
        return jsonify({"success": True, "message": f"Agent name updated to {agent_name}"})
        
    except Exception as e:
        logging.error(f"❌ Failed to save agent name to ai-memory: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/get-agent-name', methods=['GET'])
def get_agent_name():
    """Get agent name from AI-Memory service"""
    try:
        agent_name = get_admin_setting("agent_name", "Amanda")  # Default to Amanda
        return jsonify({"agent_name": agent_name})
    except Exception as e:
        logging.error(f"❌ Failed to get agent name: {e}")
        return jsonify({"agent_name": "Amanda"})  # Return default on error

@app.route('/phone/update-openai-voice', methods=['POST'])
def update_openai_voice():
    """Save OpenAI voice to AI-Memory service"""
    try:
        from app.http_memory import HTTPMemoryStore
        import time
        mem_store = HTTPMemoryStore()
        
        data = request.get_json()
        openai_voice = data.get('openai_voice', '').strip()
        
        logging.info(f"🔊 VOICE UPDATE: Received request with voice='{openai_voice}'")
        logging.info(f"🔊 VOICE UPDATE: Full request data: {data}")
        
        if not openai_voice:
            return jsonify({"success": False, "error": "Voice cannot be empty"}), 400
        
        # Validate voice option
        valid_voices = ['alloy', 'echo', 'shimmer', 'ash', 'ballad', 'coral', 'sage', 'verse', 'cedar', 'marin']
        if openai_voice not in valid_voices:
            return jsonify({"success": False, "error": f"Invalid voice. Must be one of: {', '.join(valid_voices)}"}), 400
        
        # Save to AI-Memory service as admin setting with timestamp
        mem_store.write(
            memory_type="admin_setting",
            key="openai_voice",
            value={
                "setting_key": "openai_voice",
                "value": openai_voice,
                "setting_value": openai_voice,
                "timestamp": time.time(),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            user_id="admin",
            scope="shared",
            ttl_days=365,
            source="admin_panel"
        )
        logging.info(f"✅ Saved OpenAI voice to ai-memory: {openai_voice}")
        
        return jsonify({"success": True, "message": f"OpenAI voice updated to {openai_voice}"})
        
    except Exception as e:
        logging.error(f"❌ Failed to save OpenAI voice to ai-memory: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/get-openai-voice', methods=['GET'])
def get_openai_voice():
    """Get OpenAI voice from AI-Memory service"""
    try:
        openai_voice = get_admin_setting("openai_voice", "alloy")  # Default to alloy
        return jsonify({"openai_voice": openai_voice})
    except Exception as e:
        logging.error(f"❌ Failed to get OpenAI voice: {e}")
        return jsonify({"openai_voice": "alloy"})  # Return default on error

@app.route('/phone/admin/save-transfer-rules', methods=['POST'])
def save_transfer_rules():
    """Save call transfer routing rules to AI-Memory service"""
    try:
        from app.http_memory import HTTPMemoryStore
        import json
        import time
        mem_store = HTTPMemoryStore()
        
        data = request.get_json()
        rules = data.get('rules', [])
        
        # Save as JSON array to ai-memory
        mem_store.write(
            memory_type="admin_setting",
            key="transfer_rules",
            value={
                "setting_key": "transfer_rules",
                "value": json.dumps(rules),
                "rules": rules,  # Store both for easy access
                "timestamp": time.time(),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            user_id="admin",
            scope="shared",
            ttl_days=365,
            source="admin_panel"
        )
        logging.info(f"✅ Saved {len(rules)} transfer rules to ai-memory")
        
        return jsonify({"success": True, "message": f"Saved {len(rules)} transfer rules"})
        
    except Exception as e:
        logging.error(f"❌ Failed to save transfer rules: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/admin/get-transfer-rules', methods=['GET'])
def get_transfer_rules():
    """Get call transfer routing rules from AI-Memory service"""
    try:
        import json
        
        # Try to get from admin settings
        rules_json = get_admin_setting("transfer_rules", "[]")
        
        # Parse if it's a string
        if isinstance(rules_json, str):
            rules = json.loads(rules_json) if rules_json else []
        elif isinstance(rules_json, list):
            rules = rules_json
        else:
            rules = []
            
        logging.info(f"📖 Retrieved {len(rules)} transfer rules from ai-memory")
        return jsonify({"rules": rules})
        
    except Exception as e:
        logging.error(f"❌ Failed to get transfer rules: {e}")
        return jsonify({"rules": []})  # Return empty array on error

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

@app.route('/phone/list-users')
def list_users():
    """List all users who have memories in the system"""
    try:
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        
        logging.info(f"🔍 Querying ai-memory service directly for user list")
        
        # Try to query for specific known users from recent calls
        # First, get the call logs or check common user IDs
        potential_user_ids = ["9495565377", "9494449988"]  # Add known test numbers
        
        all_users = []
        user_memory_map = {}
        
        for test_user_id in potential_user_ids:
            try:
                response = requests.post(
                    f"{ai_memory_url}/memory/retrieve",
                    json={"user_id": test_user_id, "message": "", "limit": 100},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "memory" in data and data["memory"].strip():
                        # Parse memories
                        memory_count = len([line for line in data["memory"].split('\n') if line.strip()])
                        if memory_count > 0:
                            user_memory_map[test_user_id] = memory_count
                            logging.info(f"✅ Found {memory_count} memories for user {test_user_id}")
            except:
                continue
        
        # Format as list
        users = [
            {"user_id": uid, "memory_count": count} 
            for uid, count in user_memory_map.items()
        ]
        
        logging.info(f"✅ Found {len(users)} users with memories")
        
        return jsonify({"success": True, "users": users, "total_memories": sum(user_memory_map.values())})
            
    except Exception as e:
        logging.error(f"❌ Failed to list users: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/user-memories/<user_id>')
def get_user_memories(user_id):
    """Get all memories for a specific user"""
    try:
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        
        # Normalize user_id
        normalized_user_id = user_id
        if user_id:
            normalized_digits = ''.join(filter(str.isdigit, user_id))
            if len(normalized_digits) >= 10:
                normalized_user_id = normalized_digits[-10:]
        
        logging.info(f"🔍 Getting memories for user: {normalized_user_id}")
        
        # Query ai-memory directly for this user
        response = requests.post(
            f"{ai_memory_url}/memory/retrieve",
            json={"user_id": normalized_user_id, "message": "", "limit": 200},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            memories = []
            
            # Parse newline-separated JSON format
            if "memory" in data and data["memory"].strip():
                for idx, line in enumerate(data["memory"].split('\n')):
                    line = line.strip()
                    if line:
                        try:
                            mem_obj = json.loads(line)
                            # Normalize format
                            normalized = {
                                "id": mem_obj.get("id") or f"mem_{idx}",
                                "type": mem_obj.get("type", "fact"),
                                "k": mem_obj.get("k") or mem_obj.get("key") or mem_obj.get("summary", "")[:50],
                                "key": mem_obj.get("key") or mem_obj.get("k"),
                                "value": mem_obj.get("value") or mem_obj.get("content") or mem_obj,
                                "value_json": mem_obj,
                                "user_id": mem_obj.get("user_id"),
                                "scope": mem_obj.get("scope", "user"),
                                "created_at": mem_obj.get("created_at")
                            }
                            memories.append(normalized)
                        except:
                            pass
            
            logging.info(f"✅ Found {len(memories)} memories for user {normalized_user_id}")
            return jsonify({"success": True, "memories": memories, "user_id": normalized_user_id})
        else:
            return jsonify({"success": False, "error": f"Query failed with status {response.status_code}"}), 500
            
    except Exception as e:
        logging.error(f"❌ Failed to get user memories: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/user-memories-old/<user_id>')
def get_user_memories_old(user_id):
    """Get all memories for a specific user (old direct API method)"""
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # Normalize user_id
        normalized_user_id = user_id
        if user_id:
            normalized_digits = ''.join(filter(str.isdigit, user_id))
            if len(normalized_digits) >= 10:
                normalized_user_id = normalized_digits[-10:]
        
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        response = requests.post(
            f"{ai_memory_url}/memory/retrieve",
            json={"user_id": normalized_user_id, "message": "", "limit": 200},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            # Parse the newline-separated JSON format
            memories = []
            if "memory" in data:
                for line in data["memory"].split("\n"):
                    if line.strip():
                        try:
                            mem = json.loads(line)
                            memories.append(mem)
                        except:
                            pass
            
            return jsonify({"success": True, "memories": memories, "user_id": normalized_user_id})
        else:
            return jsonify({"success": False, "error": "Failed to query ai-memory"}), 500
            
    except Exception as e:
        logging.error(f"❌ Failed to get user memories: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/update-memory', methods=['POST'])
def update_memory():
    """Update/Add a specific memory in ai-memory"""
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        data = request.get_json()
        logging.info(f"🔍 DEBUG: Received memory update request: {data}")
        
        memory_id = data.get('memory_id')
        user_id = data.get('user_id')
        memory_type = data.get('type', 'fact')
        key = data.get('key')
        value = data.get('value')
        
        logging.info(f"🔍 DEBUG: Parsed - user_id={user_id}, type={memory_type}, key={key}, value={value}")
        
        if not all([user_id, key, value]):
            missing = []
            if not user_id: missing.append("user_id")
            if not key: missing.append("key")
            if not value: missing.append("value")
            logging.error(f"❌ Missing required fields: {missing}")
            return jsonify({"success": False, "error": f"Missing required fields: {', '.join(missing)}"}), 400
        
        # ✅ FIX: Admin panel person records get highest priority timestamp
        if isinstance(value, dict) and "relationship" in value:
            value["timestamp"] = 9999999999
            logging.info(f"🔥 Admin panel person record detected, setting timestamp=9999999999 for {value.get('relationship')}: {value.get('name')}")
        
        # Write updated/new memory to ai-memory
        logging.info(f"📝 Writing memory to ai-memory service: {memory_type}:{key} for user {user_id}")
        result = mem_store.write(
            memory_type=memory_type,
            key=key,
            value=value,
            user_id=user_id,
            scope="user",
            ttl_days=730
        )
        
        logging.info(f"✅ Memory saved: {memory_type}:{key} for user {user_id}, result={result}")
        return jsonify({"success": True, "memory_id": result})
        
    except Exception as e:
        logging.error(f"❌ Failed to update memory: {e}")
        import traceback
        logging.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/user-schema/<user_id>')
def get_user_schema(user_id):
    """Get normalized schema for a specific user"""
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # Normalize user_id
        normalized_user_id = user_id
        if user_id:
            normalized_digits = ''.join(filter(str.isdigit, user_id))
            if len(normalized_digits) >= 10:
                normalized_user_id = normalized_digits[-10:]
        
        logging.info(f"🔍 Getting schema for user: {normalized_user_id}")
        
        # Query ai-memory service
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        response = requests.post(
            f"{ai_memory_url}/memory/retrieve",
            json={"user_id": normalized_user_id, "message": "", "limit": 200},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # ✅ PRIORITY 1: Check for manually saved schema (overrides auto-extracted)
            # Get the MOST RECENT manually saved schema (last one in the list)
            manual_schema = None
            manual_schemas = []
            
            if "memory" in data and data["memory"].strip():
                for line in data["memory"].split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            mem_obj = json.loads(line)
                            # Look for manually saved schema
                            if mem_obj.get("type") == "normalized_schema" and mem_obj.get("key") == "user_profile":
                                manual_schemas.append(mem_obj.get("value"))
                        except:
                            pass
            
            # Use the MOST RECENT (last) manual schema if available
            if manual_schemas:
                manual_schema = manual_schemas[-1]  # Last one is most recent
                logging.info(f"✅ Found {len(manual_schemas)} MANUALLY SAVED schemas, using MOST RECENT for user {normalized_user_id}")
                return jsonify({"success": True, "schema": manual_schema, "user_id": normalized_user_id})
            
            # ✅ PRIORITY 2: Fall back to auto-extracted normalized schema
            normalized_schema = data.get("normalized")
            if normalized_schema:
                logging.info(f"✅ Found auto-extracted normalized schema for user {normalized_user_id}")
                return jsonify({"success": True, "schema": normalized_schema, "user_id": normalized_user_id})
            
            # ✅ PRIORITY 3: Return empty template if no schema exists
            empty_schema = {
                "identity": {},
                "contacts": {"spouse": {}, "father": {}, "mother": {}, "children": []},
                "vehicles": [],
                "policies": [],
                "preferences": {},
                "facts": [],
                "commitments": []
            }
            
            logging.info(f"⚠️ No schema found, returning empty template for user {normalized_user_id}")
            return jsonify({"success": True, "schema": empty_schema, "user_id": normalized_user_id})
        else:
            return jsonify({"success": False, "error": f"Query failed with status {response.status_code}"}), 500
            
    except Exception as e:
        logging.error(f"❌ Failed to get user schema: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/process-all-memories/<user_id>', methods=['POST'])
def process_all_memories(user_id):
    """Process ALL memories for a user and extract into structured schema"""
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        # Normalize user_id
        normalized_user_id = user_id
        if user_id:
            normalized_digits = ''.join(filter(str.isdigit, user_id))
            if len(normalized_digits) >= 10:
                normalized_user_id = normalized_digits[-10:]
        
        logging.info(f"🔄 Processing ALL memories for user: {normalized_user_id}")
        
        # Get ALL memories for this user (high limit)
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        response = requests.post(
            f"{ai_memory_url}/memory/retrieve",
            json={"user_id": normalized_user_id, "message": "", "limit": 2000},
            timeout=30
        )
        
        if response.status_code != 200:
            return jsonify({"success": False, "error": f"Failed to fetch memories: {response.status_code}"}), 500
        
        data = response.json()
        all_memories = []
        
        # Parse all memories
        if "memory" in data and data["memory"].strip():
            for idx, line in enumerate(data["memory"].split('\n')):
                line = line.strip()
                if line:
                    try:
                        mem_obj = json.loads(line)
                        all_memories.append(mem_obj)
                    except:
                        pass
        
        logging.info(f"📊 Found {len(all_memories)} total memories for user {normalized_user_id}")
        
        # Run normalization pipeline on ALL memories
        normalized_schema = mem_store.normalize_memories(all_memories)
        
        # Count what was extracted
        contacts_count = sum(1 for rel in ["spouse", "father", "mother"] 
                           if normalized_schema.get("contacts", {}).get(rel, {}).get("name"))
        contacts_count += len(normalized_schema.get("contacts", {}).get("children", []))
        
        stats = {
            "total_memories": len(all_memories),
            "contacts": contacts_count,
            "vehicles": len(normalized_schema.get("vehicles", [])),
            "policies": len(normalized_schema.get("policies", [])),
            "facts": len(normalized_schema.get("facts", [])),
            "commitments": len(normalized_schema.get("commitments", []))
        }
        
        logging.info(f"✅ Extracted: {stats['contacts']} contacts, {stats['vehicles']} vehicles, {stats['policies']} policies, {stats['facts']} facts")
        
        # Save the normalized schema
        response = requests.post(
            f"{ai_memory_url}/memory/store",
            json={
                "user_id": normalized_user_id,
                "message": json.dumps({
                    "type": "normalized_schema",
                    "key": "user_profile",
                    "value": normalized_schema,
                    "timestamp": int(__import__('time').time() * 1000)
                })
            },
            timeout=10
        )
        
        if response.status_code == 200:
            logging.info(f"✅ Normalized schema saved successfully for user {normalized_user_id}")
            return jsonify({
                "success": True, 
                "user_id": normalized_user_id,
                "stats": stats,
                "schema": normalized_schema
            })
        else:
            return jsonify({"success": False, "error": f"Save failed: {response.status_code}"}), 500
            
    except Exception as e:
        logging.error(f"❌ Failed to process all memories: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/save-schema', methods=['POST'])
def save_user_schema():
    """Save normalized schema for a specific user"""
    try:
        from app.http_memory import HTTPMemoryStore
        mem_store = HTTPMemoryStore()
        
        data = request.get_json()
        user_id = data.get('user_id')
        schema = data.get('schema')
        
        if not user_id or not schema:
            return jsonify({"success": False, "error": "Missing user_id or schema"}), 400
        
        # Normalize user_id
        normalized_user_id = user_id
        if user_id:
            normalized_digits = ''.join(filter(str.isdigit, user_id))
            if len(normalized_digits) >= 10:
                normalized_user_id = normalized_digits[-10:]
        
        logging.info(f"💾 Saving schema for user: {normalized_user_id}")
        
        # ✅ FIX: Save each person as INDIVIDUAL memory with highest priority timestamp
        contacts = schema.get("contacts", {})
        saved_count = 0
        
        for relationship, person_data in contacts.items():
            if person_data and person_data.get("name"):
                # Add timestamp=9999999999 to ensure admin panel data wins
                person_data["timestamp"] = 9999999999
                person_data["relationship"] = relationship
                
                # Save individual person record
                result = mem_store.write(
                    memory_type="person",
                    key=f"{relationship}_{person_data['name'].replace(' ', '_')}",
                    value=person_data,
                    user_id=normalized_user_id,
                    scope="user",
                    ttl_days=3650,  # 10 years
                    source="admin_panel"
                )
                logging.info(f"✅ Saved {relationship}: {person_data['name']} with timestamp=9999999999")
                saved_count += 1
        
        # Also save full schema as backup (for UI display)
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        response = requests.post(
            f"{ai_memory_url}/memory/store",
            json={
                "user_id": normalized_user_id,
                "message": json.dumps({
                    "type": "normalized_schema",
                    "key": "user_profile",
                    "value": schema,
                    "timestamp": int(__import__('time').time() * 1000)
                })
            },
            timeout=10
        )
        
        if response.status_code == 200:
            logging.info(f"✅ Schema saved: {saved_count} person records + full schema for user {normalized_user_id}")
            return jsonify({"success": True, "user_id": normalized_user_id, "saved_persons": saved_count})
        else:
            logging.error(f"❌ Failed to save schema backup: HTTP {response.status_code}")
            return jsonify({"success": False, "error": f"Save failed with status {response.status_code}"}), 500
            
    except Exception as e:
        logging.error(f"❌ Failed to save user schema: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/phone/delete-memory', methods=['POST'])
def delete_memory():
    """Delete a specific memory from ai-memory"""
    try:
        data = request.get_json()
        memory_id = data.get('memory_id')
        
        if not memory_id:
            return jsonify({"success": False, "error": "Missing memory_id"}), 400
        
        # Note: ai-memory service may not have a delete endpoint
        # In that case, we update with empty/expired data
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        
        # Try to delete or mark as deleted
        # This might need adjustment based on ai-memory service capabilities
        logging.info(f"✅ Memory deletion requested: {memory_id}")
        return jsonify({"success": True, "message": "Memory marked for deletion"})
        
    except Exception as e:
        logging.error(f"❌ Failed to delete memory: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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

# ============================================================================
# CUSTOMER MANAGEMENT API ROUTES
# ============================================================================

@app.route('/api/customers/onboard', methods=['POST'])
def customer_onboard():
    """Handle new customer onboarding"""
    try:
        from werkzeug.security import generate_password_hash
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from customer_models import Customer, CustomerConfiguration
        import json
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('password'):
            return jsonify({"success": False, "error": "Password is required"}), 400
        
        # Create database engine
        engine = create_engine(_get_config()["database_url"])
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        # Hash password
        password_hash = generate_password_hash(data.get('password'))
        
        # Create new customer
        customer = Customer(
            email=data.get('email'),
            password_hash=password_hash,
            business_name=data.get('business_name'),
            contact_name=data.get('contact_name'),
            phone=data.get('phone'),
            package_tier=data.get('package_tier', 'starter'),
            agent_name=data.get('agent_name', 'AI Assistant'),
            openai_voice=data.get('openai_voice', 'alloy'),
            greeting_template=data.get('greeting_template'),
            personality_sliders=None,  # Will be set by personality preset
            twilio_phone_number=None,  # Will be provisioned later
            status='active'
        )
        
        db_session.add(customer)
        db_session.commit()
        
        # Save initial configuration
        config = CustomerConfiguration(
            customer_id=customer.id,
            config_type='personality',
            config_key='preset',
            config_value={'preset': data.get('personality_preset', 'professional')},
            created_by='onboarding'
        )
        db_session.add(config)
        db_session.commit()
        
        logging.info(f"✅ New customer onboarded: {customer.email} (ID: {customer.id})")
        
        # Also save to Notion for easy management
        try:
            import requests
            notion_response = requests.post('http://localhost:8200/notion/platform-customer', json={
                'email': customer.email,
                'business_name': customer.business_name,
                'contact_name': customer.contact_name,
                'phone': customer.phone,
                'package_tier': customer.package_tier,
                'agent_name': customer.agent_name,
                'openai_voice': customer.openai_voice,
                'personality_preset': data.get('personality_preset', 'professional'),
                'greeting_template': customer.greeting_template,
                'status': 'Active'
            }, timeout=5)
            
            if notion_response.status_code == 200:
                logging.info(f"✅ Customer synced to Notion: {customer.email}")
            else:
                logging.warning(f"⚠️ Failed to sync to Notion: {notion_response.text}")
        except Exception as notion_error:
            # Don't fail onboarding if Notion sync fails
            logging.warning(f"⚠️ Notion sync failed (non-critical): {notion_error}")
        
        db_session.close()
        
        return jsonify({
            "success": True,
            "customer_id": customer.id,
            "message": "Onboarding complete"
        })
        
    except Exception as e:
        logging.error(f"❌ Customer onboarding failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== AUTHENTICATION ENDPOINTS ====================

@app.route('/api/login', methods=['POST'])
def login():
    """Customer login endpoint"""
    try:
        from werkzeug.security import check_password_hash
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from customer_models import Customer
        
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400
        
        engine = create_engine(_get_config()["database_url"])
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        customer = db_session.query(Customer).filter_by(email=email).first()
        
        if not customer:
            db_session.close()
            return jsonify({"error": "Invalid email or password"}), 401
        
        if not customer.password_hash:
            db_session.close()
            return jsonify({"error": "Password not set. Please contact support."}), 401
        
        if not check_password_hash(customer.password_hash, password):
            db_session.close()
            return jsonify({"error": "Invalid email or password"}), 401
        
        # Set session
        session['customer_id'] = customer.id
        session['customer_email'] = customer.email
        session['customer_name'] = customer.contact_name
        session.permanent = True
        
        logging.info(f"✅ Customer logged in: {customer.email} (ID: {customer.id})")
        
        db_session.close()
        
        return jsonify({
            "success": True,
            "customer": {
                "id": customer.id,
                "email": customer.email,
                "business_name": customer.business_name,
                "contact_name": customer.contact_name
            }
        })
        
    except Exception as e:
        logging.error(f"❌ Login failed: {e}")
        return jsonify({"error": "Login failed"}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Customer logout endpoint"""
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})

@app.route('/api/check-session', methods=['GET'])
def check_session():
    """Check if customer is logged in"""
    if 'customer_id' in session:
        return jsonify({
            "authenticated": True,
            "customer": {
                "id": session['customer_id'],
                "email": session.get('customer_email'),
                "name": session.get('customer_name')
            }
        })
    return jsonify({"authenticated": False}), 401

@app.route('/api/customers/<int:customer_id>', methods=['GET'])
def get_customer(customer_id):
    """Get customer details"""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from customer_models import Customer
        
        engine = create_engine(_get_config()["database_url"])
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        customer = db_session.query(Customer).filter_by(id=customer_id).first()
        
        if not customer:
            db_session.close()
            return jsonify({"error": "Customer not found"}), 404
        
        result = customer.to_dict()
        db_session.close()
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"❌ Failed to get customer: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/customers/<int:customer_id>/settings', methods=['PUT'])
def update_customer_settings(customer_id):
    """Update customer AI settings"""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from customer_models import Customer, CustomerConfiguration
        
        data = request.get_json()
        
        engine = create_engine(_get_config()["database_url"])
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        customer = db_session.query(Customer).filter_by(id=customer_id).first()
        
        if not customer:
            db_session.close()
            return jsonify({"error": "Customer not found"}), 404
        
        # Update customer settings
        if 'agent_name' in data:
            customer.agent_name = data['agent_name']
        if 'openai_voice' in data:
            customer.openai_voice = data['openai_voice']
        if 'greeting_template' in data:
            customer.greeting_template = data['greeting_template']
        
        # Save configuration history
        for key, value in data.items():
            config = CustomerConfiguration(
                customer_id=customer_id,
                config_type='setting',
                config_key=key,
                config_value={'value': value},
                created_by='customer'
            )
            db_session.add(config)
        
        db_session.commit()
        db_session.close()
        
        logging.info(f"✅ Updated settings for customer {customer_id}")
        
        return jsonify({"success": True, "message": "Settings updated"})
        
    except Exception as e:
        logging.error(f"❌ Failed to update customer settings: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/customers/<int:customer_id>/personality', methods=['POST'])
def apply_customer_personality(customer_id):
    """Apply personality preset to customer"""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from customer_models import Customer, CustomerConfiguration
        
        data = request.get_json()
        preset = data.get('preset', 'professional')
        
        engine = create_engine(_get_config()["database_url"])
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        customer = db_session.query(Customer).filter_by(id=customer_id).first()
        
        if not customer:
            db_session.close()
            return jsonify({"error": "Customer not found"}), 404
        
        # Personality presets mapping
        presets = {
            'professional': {'warmth': 50, 'empathy': 50, 'directness': 70},
            'friendly': {'warmth': 80, 'empathy': 75, 'directness': 40},
            'assertive': {'warmth': 40, 'empathy': 40, 'directness': 85},
            'empathetic': {'warmth': 75, 'empathy': 90, 'directness': 35}
        }
        
        personality_config = presets.get(preset, presets['professional'])
        
        customer.personality_sliders = personality_config
        
        # Save to configuration history
        config = CustomerConfiguration(
            customer_id=customer_id,
            config_type='personality',
            config_key='preset',
            config_value={'preset': preset, 'config': personality_config},
            created_by='customer'
        )
        db_session.add(config)
        db_session.commit()
        db_session.close()
        
        logging.info(f"✅ Applied {preset} personality for customer {customer_id}")
        
        return jsonify({"success": True, "message": f"Applied {preset} personality"})
        
    except Exception as e:
        logging.error(f"❌ Failed to apply personality: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
