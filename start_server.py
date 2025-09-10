#!/usr/bin/env python3
"""
Start script for NeuroSphere Orchestrator
"""
import os
import uvicorn
from config_loader import get_setting, get_llm_config, get_secret

# Set LLM configuration from centralized config
llm_config = get_llm_config()
os.environ.setdefault("LLM_MODEL", llm_config["model"])
os.environ.setdefault("EMBED_DIM", str(get_setting("embed_dim", 768)))

# Set Digital Ocean database URL
# Database URL loaded from environment variables

# Import app after setting environment variables
from app.main import app

if __name__ == "__main__":
    port = int(get_setting("port", 5000))
    print("Starting NeuroSphere Orchestrator...")
    print(f"Server will be available at: http://0.0.0.0:{port}")
    print(f"LLM Base URL: {llm_config['base_url']}")
    print(f"Database: {'Connected' if get_secret('DATABASE_URL') else 'Not configured'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        log_level="info",
        reload=True
    )