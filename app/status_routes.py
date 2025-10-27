from flask import Blueprint, jsonify, current_app
import json
import os
import time
import requests
import socket

status_bp = Blueprint("status", __name__)

STATUS_FILE = os.environ.get("CHATSTACK_STATUS_FILE", "/var/lib/chatstack/status.json")
STALE_AFTER_SECONDS = int(os.environ.get("CHATSTACK_STATUS_STALE", "90"))

def check_service_health(name, url, port=None):
    """Quick health check for a service"""
    result = {
        "key": name.lower().replace(" ", "_"),
        "name": name,
        "ok": False,
        "http": {"ok": None, "status_code": None, "latency_ms": None},
        "port": {"ok": None},
        "systemd": {"state": None},
        "process": {"count": None},
        "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    # HTTP check
    if url:
        try:
            start = time.perf_counter()
            r = requests.get(url, timeout=2)
            latency = int((time.perf_counter() - start) * 1000)
            result["http"] = {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "latency_ms": latency
            }
            result["ok"] = r.status_code == 200
        except Exception:
            result["http"] = {"ok": False, "status_code": None, "latency_ms": None}
    
    # Port check
    if port:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect(("127.0.0.1", port))
            sock.close()
            result["port"] = {"ok": True}
        except Exception:
            result["port"] = {"ok": False}
    
    return result

def get_dev_fallback_status():
    """Provide fallback status for development (when monitoring script isn't running)"""
    services = {}
    
    # Check Flask (this service)
    services["flask_web"] = {
        "key": "flask_web",
        "name": "Flask Web",
        "ok": True,
        "http": {"ok": True, "status_code": 200, "latency_ms": 5},
        "port": {"ok": True},
        "systemd": {"state": "dev-mode"},
        "process": {"count": 1},
        "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    # Check FastAPI Orchestrator
    services["fastapi_orchestrator"] = check_service_health(
        "FastAPI Orchestrator", 
        "http://127.0.0.1:8001/health",
        8001
    )
    
    # Check AI-Memory Service
    services["ai_memory"] = check_service_health(
        "AI-Memory Service",
        "http://209.38.143.71:8100/health",
        None  # Remote service
    )
    
    return {
        "services": services,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok_count": sum(1 for s in services.values() if s["ok"]),
        "fail_count": sum(1 for s in services.values() if not s["ok"]),
        "total": len(services),
        "mode": "development_fallback",
        "note": "Using live health checks. Deploy status_monitor.py for production monitoring."
    }

@status_bp.route("/api/status")
def api_status():
    """
    Return system status from monitoring file or live checks.
    
    Production: Reads from status.json written by status_monitor.py
    Development: Falls back to live health checks
    """
    try:
        # Try to read from monitoring file first (production)
        if os.path.exists(STATUS_FILE):
            mtime = os.path.getmtime(STATUS_FILE)
            age = time.time() - mtime
            with open(STATUS_FILE, "r") as f:
                data = json.load(f)
            data["_file"] = {"path": STATUS_FILE, "age_seconds": age}
            if age > STALE_AFTER_SECONDS:
                data["_warning"] = f"status file is stale (> {STALE_AFTER_SECONDS}s). Is status_monitor running?"
            data["mode"] = "production_monitoring"
            return jsonify(data)
        
        # Fallback to live checks (development)
        current_app.logger.info("Status file not found, using development fallback")
        data = get_dev_fallback_status()
        return jsonify(data)
        
    except Exception as e:
        current_app.logger.exception("Failed to get status")
        return jsonify({"error": "exception", "message": str(e)}), 500