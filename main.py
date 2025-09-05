"""
NeuroSphere Orchestrator - Flask Web Interface
"""
import os
import requests
import json
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
