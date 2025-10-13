#!/bin/bash
# Start both Flask and FastAPI services

# Start Flask (gunicorn) on port 5000 in background
gunicorn --bind 0.0.0.0:5000 --reuse-port --reload main:app &

# Start FastAPI (uvicorn) on port 8001 in foreground
uvicorn app.main:app --host 0.0.0.0 --port 8001
