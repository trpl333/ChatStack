# Peterson Family Insurance AI Phone System

## Overview
This project is an AI-powered phone system for Peterson Family Insurance, utilizing "Samantha" as the AI agent. The system, built on NeuroSphere Orchestrator, is a FastAPI-based solution designed for intelligent call handling with persistent memory. It aims for a rapid response time of 2-2.5 seconds. Key capabilities include maintaining conversation continuity via a PostgreSQL vector database, integrating external tools for actions, and employing safety modes for content filtering. The orchestrator serves as middleware between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations through memory retrieval, prompt engineering, and extensible tool functionality.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The system employs a hybrid Flask + FastAPI backend. A Flask orchestrator (`main.py`) handles Twilio webhooks and spawns the FastAPI backend (`app/main.py`), which manages the core `/v1/chat` endpoint and LLM integration.

### Core Components:
- **LLM Integration**: Communicates with an OpenAI-compatible API endpoint (defaulting to Qwen2-7B-Instruct) for AI responses, with structured message passing and error handling.
- **Memory System**: Utilizes PostgreSQL with the `pgvector` extension for semantic search, storing categorized memories (person, preference, project, rule, moment, fact) with TTL support. Short-term memory is managed for in-session context.
- **Prompt Engineering**: Employs file-based system prompts for AI personalities, intelligent context packing from memory, and safety triggers for content filtering.
- **Tool System**: An extensible, JSON schema-based architecture for external tool execution (e.g., meeting booking, message sending) with a central dispatcher and error recovery.
- **Data Models**: Pydantic for type-safe validation of request/response models, including role-based messages and structured memory objects.
- **Safety & Security**: Features multi-tier content filtering, PII protection, rate limiting, and comprehensive input validation.

### UI/UX Decisions:
- Minimal UI for administrative functions via an `/admin` endpoint.
- Focus on seamless voice interaction, with audio files served for natural voice synthesis.

### Technical Implementations:
- **Python Frameworks**: Flask and FastAPI.
- **Database**: PostgreSQL with `pgvector` for vector embeddings and `pgcrypto` for UUIDs.
- **Containerization**: Docker for deployment, with `docker-compose.yml` for orchestration.
- **Web Server**: Nginx for HTTPS termination, proxying requests to the Flask and FastAPI services.
- **Deployment**: Primarily on DigitalOcean Droplets with a RunPod GPU for LLM inference.

## External Dependencies

### Services:
- **Twilio**: For voice call management and incoming call webhooks.
- **RunPod LLM**: Primary LLM service (specific endpoint: `https://a40.neurospherevoice.com/v1/chat/completions`).
- **ElevenLabs**: For natural voice synthesis and text-to-speech conversion.
- **AI-Memory Service**: An external service for conversation memory persistence (`http://209.38.143.71:8100`).

### Databases:
- **PostgreSQL**: Used with `pgvector` extension for conversation memory and semantic search.

### Libraries (Key Examples):
- **FastAPI** & **Uvicorn**: Web framework and ASGI server.
- **Pydantic**: Data validation.
- **NumPy**: Vector operations.
- **Requests**: HTTP client.
- **psycopg2**: PostgreSQL adapter.

### Optional Integrations (Planned/Recommended):
- **Redis**: For production short-term memory.
- **Embedding Services**: Such as OpenAI Embeddings or Sentence Transformers for production embedding generation.