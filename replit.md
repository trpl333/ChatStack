# NeuroSphere Orchestrator

## Overview

NeuroSphere Orchestrator is a FastAPI-based AI chat application that provides a ChatGPT-style interface with persistent memory capabilities. The system features an AI assistant named "Sam" that maintains conversation continuity through a PostgreSQL vector database, supports tool integrations for external actions, and includes safety modes for content filtering. The orchestrator acts as a middleware layer between users and Language Learning Models (LLMs), enhancing conversations with memory retrieval, prompt engineering, and extensible tool functionality.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: FastAPI with asyncio support for handling concurrent requests
- **Entry Point**: Uvicorn ASGI server configured through main.py
- **Modular Design**: Separated concerns across app modules (llm, memory, packer, tools, models)
- **Lifespan Management**: Async context manager for startup/shutdown procedures and resource cleanup

### Memory System
- **Vector Database**: PostgreSQL with pgvector extension for semantic similarity search
- **Embedding Strategy**: Deterministic hash-based embeddings (placeholder for production embedding service)
- **Memory Types**: Categorized storage (person, preference, project, rule, moment, fact) with TTL support
- **Short-term Memory**: In-memory conversation recaps for maintaining context within sessions
- **Memory Lifecycle**: Automatic cleanup of expired memories and retention policies

### LLM Integration
- **OpenAI-Compatible API**: Configurable base URL and model selection via environment variables
- **Request Management**: Structured message passing with temperature, top_p, and max_tokens controls
- **Error Handling**: Connection validation and timeout management for external LLM services
- **Response Processing**: Token usage tracking and response formatting

### Prompt Engineering
- **System Personas**: File-based system prompts for different AI personalities (Sam, Safety mode)
- **Context Packing**: Intelligent memory retrieval and prompt construction
- **Safety Triggers**: Content filtering and safety mode activation based on context
- **Memory Integration**: Relevant memory injection into conversation context

### Tool System
- **Extensible Architecture**: JSON schema-based tool definitions with parameter validation
- **Tool Dispatcher**: Central routing system for tool execution and response handling
- **Built-in Tools**: Meeting booking, message sending, and other productivity integrations
- **Error Recovery**: Graceful handling of tool failures with fallback responses

### Data Models
- **Pydantic Validation**: Type-safe request/response models with field validation
- **Message Structure**: Role-based message system (system, user, assistant)
- **Memory Objects**: Structured memory representation with metadata and TTL
- **Tool Interfaces**: Standardized tool call and response models

### Safety and Security
- **Content Filtering**: Multi-tier safety system with configurable strictness levels
- **PII Protection**: Automatic detection and masking of personally identifiable information
- **Rate Limiting**: Built-in protections against abuse and resource exhaustion
- **Input Validation**: Comprehensive request validation and sanitization

## External Dependencies

### Database
- **PostgreSQL**: Primary data store with pgvector extension for vector operations
- **pgcrypto**: UUID generation and cryptographic functions
- **Connection Management**: psycopg2 with connection pooling and transaction management

### LLM Services
- **OpenAI-Compatible API**: External LLM endpoint (configurable base URL)
- **Default Model**: Qwen2-7B-Instruct with support for model switching
- **Authentication**: Bearer token support for secured LLM access

### Python Libraries
- **FastAPI**: Web framework with automatic API documentation
- **Uvicorn**: ASGI server for production deployment
- **Pydantic**: Data validation and serialization
- **NumPy**: Vector operations and embedding manipulation
- **Requests**: HTTP client for LLM API communication

### Development and Deployment
- **Environment Configuration**: Extensive environment variable support for deployment flexibility
- **CORS Support**: Cross-origin request handling for web interfaces
- **Logging**: Structured logging with configurable levels
- **Health Checks**: LLM connection validation and system status monitoring

### Optional Integrations
- **Redis**: Recommended for production short-term memory storage
- **Embedding Services**: OpenAI Embeddings, Sentence Transformers for production embedding generation
- **Monitoring**: Application performance monitoring and observability tools