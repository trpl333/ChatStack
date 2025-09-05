#!/usr/bin/env python3
"""
Start script for NeuroSphere Orchestrator
"""
import os
import uvicorn

# Set LLM configuration for RunPod endpoint
os.environ.setdefault("LLM_BASE_URL", "https://5njnf4k2bc5t20-8000.proxy.runpod.net")
os.environ.setdefault("LLM_MODEL", "Qwen/Qwen2-7B-Instruct")  # RunPod model with namespace
os.environ.setdefault("EMBED_DIM", "768")

# Set Digital Ocean database URL
os.environ.setdefault("DATABASE_URL", "postgresql://doadmin:AVNS_uS8rBktm7cJo7ToivuD@ai-memory-do-user-17983093-0.e.db.ondigitalocean.com:25060/defaultdb?sslmode=require")

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