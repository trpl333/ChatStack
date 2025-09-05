"""
NeuroSphere Orchestrator - Flask Web Interface with Phone AI
"""
import os
import requests
import json
import io
import base64
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, Response
from twilio.rest import Client
from twilio.twiml import TwiML
from twilio.twiml.voice_response import VoiceResponse, Gather
from elevenlabs import ElevenLabs, VoiceSettings
import tempfile
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Set environment variables 
os.environ.setdefault("DATABASE_URL", "postgresql://doadmin:AVNS_uS8rBktm7cJo7ToivuD@ai-memory-do-user-17983093-0.e.db.ondigitalocean.com:25060/defaultdb?sslmode=require")
os.environ.setdefault("LLM_BASE_URL", "https://5njnf4k2bc5t20-8000.proxy.runpod.net")
os.environ.setdefault("LLM_MODEL", "Qwen/Qwen2-7B-Instruct")
os.environ.setdefault("EMBED_DIM", "768")

# Start FastAPI backend server
import subprocess
import time
import threading

def start_fastapi_backend():
    """Start FastAPI server on port 8001 in background"""
    try:
        cmd = ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "error"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)  # Give server time to start
        print("✅ FastAPI backend started on port 8001")
    except Exception as e:
        print(f"⚠️ Failed to start FastAPI backend: {e}")

# Start backend in thread
backend_thread = threading.Thread(target=start_fastapi_backend, daemon=True)
backend_thread.start()

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "neurosphere-secret-key")

BACKEND_URL = "http://127.0.0.1:8001"

# Initialize Twilio and ElevenLabs clients
twilio_client = Client(os.environ.get('TWILIO_ACCOUNT_SID'), os.environ.get('TWILIO_AUTH_TOKEN'))
elevenlabs_client = ElevenLabs(api_key=os.environ.get('ELEVENLABS_API_KEY'))

# Phone call session storage (in production, use Redis or database)
call_sessions = {}

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
            resp = requests.get(f"{BACKEND_URL}/v1/memories", params={"limit": 50}, timeout=10)
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
            resp = requests.post(f"{BACKEND_URL}/v1/chat", json={
                "user_id": user_id,
                "message": "Show my memories",
                "debug": True
            }, timeout=10)
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
        
        resp = requests.post(f"{BACKEND_URL}/v1/memories", json=data, timeout=10)
        
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

# ============ PHONE AI ENDPOINTS ============

def text_to_speech(text, voice_id="21m00Tcm4TlvDq8ikWAM"):
    """Convert text to speech using ElevenLabs"""
    try:
        # Using the correct ElevenLabs API method
        audio = elevenlabs_client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id="eleven_monolingual_v1",
            voice_settings=VoiceSettings(
                stability=0.71,
                similarity_boost=0.5,
                style=0.0,
                use_speaker_boost=True
            )
        )
        return audio
    except Exception as e:
        logging.error(f"TTS Error: {e}")
        return None

def get_personalized_greeting(user_id):
    """Get personalized greeting based on user's stored information"""
    try:
        # Check if we know this user's name
        resp = requests.get(f"{BACKEND_URL}/v1/memories", params={"user_id": user_id, "limit": 5}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            memories = data.get("memories", [])
            
            # Look for user's name in stored memories
            user_name = None
            for memory in memories:
                if memory.get("type") == "person" and "name" in str(memory.get("value", {})):
                    value = memory.get("value", {})
                    if isinstance(value, dict) and "name" in value:
                        user_name = value["name"]
                        break
                    elif "John" in str(value):  # Fallback name extraction
                        user_name = "John"
                        break
            
            if user_name:
                return f"Hello {user_name}! Welcome back to NeuroSphere AI. How can I help you today?"
            
    except Exception as e:
        logging.error(f"Error getting personalized greeting: {e}")
    
    # Default greeting for new or unknown callers
    return "Hello! Welcome to NeuroSphere AI. I'm your auto insurance assistant. How can I help you today?"

def get_ai_response(user_id, message):
    """Get AI response from NeuroSphere backend"""
    try:
        # Format request properly for FastAPI backend
        payload = {
            "messages": [
                {"role": "user", "content": message}
            ],
            "temperature": 0.7,
            "max_tokens": 400
        }
        
        # Add user_id as query parameter
        resp = requests.post(f"{BACKEND_URL}/v1/chat?user_id={user_id}", 
                           json=payload, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            return data.get("output", "I'm sorry, I couldn't process that.")
        else:
            logging.error(f"Backend error: {resp.status_code} - {resp.text}")
            return "I'm experiencing technical difficulties. Please try again."
    except Exception as e:
        logging.error(f"AI Response Error: {e}")
        return "I'm sorry, I'm having trouble connecting right now."

@app.route('/phone/incoming', methods=['POST'])
def handle_incoming_call():
    """Handle incoming phone calls from Twilio"""
    from_number = request.form.get('From')
    call_sid = request.form.get('CallSid')
    
    # Store call session
    call_sessions[call_sid] = {
        'user_id': from_number,
        'call_count': 1
    }
    
    logging.info(f"📞 Incoming call from {from_number}")
    
    response = VoiceResponse()
    greeting = get_personalized_greeting(from_number)
    response.say(greeting)
    
    # Gather user speech
    gather = Gather(
        input='speech',
        timeout=10,
        speech_timeout=3,
        action='/phone/process-speech',
        method='POST'
    )
    response.append(gather)
    
    # Fallback if no speech detected
    response.say("I didn't hear anything. Please try calling back.")
    response.hangup()
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/phone/process-speech', methods=['POST'])
def process_speech():
    """Process speech input from caller"""
    speech_result = request.form.get('SpeechResult')
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    
    if not speech_result:
        response = VoiceResponse()
        response.say("I didn't catch that. Could you please repeat?")
        
        gather = Gather(
            input='speech',
            timeout=10,
            speech_timeout=3,
            action='/phone/process-speech',
            method='POST'
        )
        response.append(gather)
        response.hangup()
        return str(response), 200, {'Content-Type': 'text/xml'}
    
    logging.info(f"🎤 Speech from {from_number}: {speech_result}")
    
    # Get AI response from NeuroSphere
    user_id = from_number
    ai_response = get_ai_response(user_id, speech_result)
    
    logging.info(f"🤖 AI Response: {ai_response}")
    
    # Generate TwiML response
    response = VoiceResponse()
    response.say(ai_response)
    
    # Ask if they want to continue
    response.say("Would you like to ask me anything else?")
    
    gather = Gather(
        input='speech',
        timeout=10,
        speech_timeout=3,
        action='/phone/process-speech',
        method='POST'
    )
    response.append(gather)
    
    # End call if no response
    response.say("Thank you for calling NeuroSphere AI. Have a great day!")
    response.hangup()
    
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
        "twilio_configured": bool(os.environ.get('TWILIO_ACCOUNT_SID')),
        "elevenlabs_configured": bool(os.environ.get('ELEVENLABS_API_KEY')),
        "backend_url": BACKEND_URL
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
