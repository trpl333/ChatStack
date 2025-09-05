#!/usr/bin/env python3
"""
Start script for NeuroSphere Orchestrator
"""
import os
import uvicorn

# Set default LLM configuration for local testing
os.environ.setdefault("LLM_BASE_URL", "http://localhost:8000")  # Mock endpoint
os.environ.setdefault("LLM_MODEL", "mock-model")
os.environ.setdefault("EMBED_DIM", "768")

# Import app after setting environment variables
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Starting NeuroSphere Orchestrator...")
    print(f"Server will be available at: http://0.0.0.0:{port}")
    print(f"LLM Base URL: {os.environ.get('LLM_BASE_URL')}")
    print(f"Database URL: {os.environ.get('DATABASE_URL', 'Not set')}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        log_level="info",
        reload=True
    )