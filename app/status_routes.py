from flask import Blueprint, jsonify, current_app
import json
import os
import time

status_bp = Blueprint("status", __name__)

STATUS_FILE = os.environ.get("CHATSTACK_STATUS_FILE", "/var/lib/chatstack/status.json")
STALE_AFTER_SECONDS = int(os.environ.get("CHATSTACK_STATUS_STALE", "90"))

@status_bp.route("/api/status")
def api_status():
    try:
        if not os.path.exists(STATUS_FILE):
            return jsonify({"error": "status_file_not_found", "path": STATUS_FILE}), 404
        mtime = os.path.getmtime(STATUS_FILE)
        age = time.time() - mtime
        with open(STATUS_FILE, "r") as f:
            data = json.load(f)
        data["_file"] = {"path": STATUS_FILE, "age_seconds": age}
        if age > STALE_AFTER_SECONDS:
            data["_warning"] = f"status file is stale (> {STALE_AFTER_SECONDS}s). Is status_monitor running?"
        return jsonify(data)
    except Exception as e:
        current_app.logger.exception("Failed to read status file")
        return jsonify({"error": "exception", "message": str(e)}), 500