#!/usr/bin/env python3
"""
Production-ready startup script for NeuroSphere Orchestrator
Works with both gunicorn and direct execution
"""
import os
from app.main import app

# Set defaults for production
os.environ.setdefault("LLM_BASE_URL", "http://localhost:8000")  # Mock for demo
os.environ.setdefault("LLM_MODEL", "mock-model")
os.environ.setdefault("EMBED_DIM", "768")

# This file can be used by gunicorn: gunicorn run_app:app
# Or run directly: python run_app.py

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")