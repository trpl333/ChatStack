import os
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.models import ChatRequest, ChatResponse, MemoryObject
from app.llm import chat as llm_chat, validate_llm_connection
from app.memory import MemoryStore
from app.packer import pack_prompt, should_remember, extract_carry_kit_items, detect_safety_triggers
from app.tools import tool_dispatcher, parse_tool_calls, execute_tool_calls

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global memory store instance
memory_store = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global memory_store
    
    # Startup
    logger.info("Starting NeuroSphere Orchestrator...")
    
    try:
        # Initialize memory store
        memory_store = MemoryStore()
        logger.info("Memory store initialized")
        
        # Validate LLM connection
        if not validate_llm_connection():
            logger.warning("LLM connection validation failed - service may be unavailable")
        
        # Cleanup expired memories
        cleanup_count = memory_store.cleanup_expired()
        logger.info(f"Cleaned up {cleanup_count} expired memories")
        
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down NeuroSphere Orchestrator...")
        if memory_store:
            memory_store.close()

# Create FastAPI app
app = FastAPI(
    title="NeuroSphere Orchestrator",
    description="ChatGPT-style conversational AI with long-term memory and tool calling",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_memory_store() -> MemoryStore:
    """Dependency to get memory store instance."""
    if memory_store is None:
        raise HTTPException(status_code=500, detail="Memory store not initialized")
    return memory_store

# Memory write heuristics
IMPORTANT_TYPES = {"person", "preference", "project", "rule", "moment"}

def should_store_memory(user_text: str, memory_type: str = "") -> bool:
    """
    Determine if content should be stored in long-term memory.
    
    Args:
        user_text: User message content
        memory_type: Type of memory being considered
        
    Returns:
        True if should be stored
    """
    return (
        should_remember(user_text) or 
        memory_type in IMPORTANT_TYPES or
        "remember this" in user_text.lower() or
        "save this" in user_text.lower()
    )

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "NeuroSphere Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "description": "ChatGPT-style AI with memory and tools"
    }

@app.get("/admin")
async def admin_interface():
    """Serve the knowledge base admin interface."""
    return FileResponse("static/admin.html")

@app.get("/health")
async def health_check(mem_store: MemoryStore = Depends(get_memory_store)):
    """Health check endpoint."""
    try:
        # Check memory store
        stats = mem_store.get_memory_stats()
        
        # Check LLM connection
        llm_status = validate_llm_connection()
        
        return {
            "status": "healthy" if llm_status else "degraded",
            "memory_store": "connected",
            "llm_service": "connected" if llm_status else "unavailable",
            "total_memories": stats.get("total_memories", 0)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.post("/v1/chat", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    thread_id: str = "default",
    user_id: Optional[str] = None,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """
    Main chat completion endpoint with memory and tool calling.
    
    Args:
        request: Chat request with messages and parameters
        thread_id: Conversation thread identifier
        mem_store: Memory store dependency
        
    Returns:
        Chat response with output and metadata
    """
    try:
        logger.info(f"Chat request: {len(request.messages)} messages, thread={thread_id}")
        
        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")
        
        # Get the latest user message
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")
        
        # Check for safety triggers
        safety_mode = request.safety_mode or detect_safety_triggers(user_message)
        if safety_mode:
            logger.info("Safety mode activated")
        
        # Process carry-kit items for memory storage
        if should_store_memory(user_message):
            carry_kit_items = extract_carry_kit_items(user_message)
            for item in carry_kit_items:
                try:
                    memory_id = mem_store.write(
                        item["type"],
                        item["key"], 
                        item["value"],
                        user_id=None,
                        scope="user",
                        ttl_days=item.get("ttl_days", 365)
                    )
                    logger.info(f"Stored carry-kit item: {item['type']}:{item['key']} -> {memory_id}")
                except Exception as e:
                    logger.error(f"Failed to store carry-kit item: {e}")
        
        # Retrieve relevant memories (user-specific + shared)
        retrieved_memories = mem_store.search(user_message, user_id=user_id, k=6)
        logger.info(f"Retrieved {len(retrieved_memories)} relevant memories")
        
        # Convert messages to dict format for processing
        message_dicts = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        # Pack prompt with system context, memories, and conversation
        final_messages = pack_prompt(
            message_dicts,
            retrieved_memories,
            safety_mode=safety_mode,
            thread_id=thread_id
        )
        
        # Call LLM
        logger.info("Calling LLM...")
        assistant_output, usage_stats = llm_chat(
            final_messages,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens
        )
        
        # Parse and execute tool calls if present
        tool_results = []
        tool_calls = parse_tool_calls(assistant_output)
        if tool_calls:
            logger.info(f"Executing {len(tool_calls)} tool calls")
            tool_results = execute_tool_calls(tool_calls)
            
            # Append tool results to assistant output
            if tool_results:
                result_summaries = []
                for result in tool_results:
                    if result["success"]:
                        result_summaries.append(result["result"])
                    else:
                        result_summaries.append(f"Tool error: {result['error']}")
                
                if result_summaries:
                    assistant_output += "\n\n" + "\n".join(result_summaries)
        
        # Store important information from the conversation
        if should_store_memory(assistant_output, "moment"):
            try:
                mem_store.write(
                    "moment",
                    f"conversation_{hash(user_message) % 100000}",
                    {
                        "user_message": user_message[:500],
                        "assistant_response": assistant_output[:500],
                        "summary": f"Conversation about: {user_message[:100]}..."
                    },
                    ttl_days=90  # Shorter TTL for conversation moments
                )
            except Exception as e:
                logger.error(f"Failed to store conversation moment: {e}")
        
        # Prepare response
        response = ChatResponse(
            output=assistant_output,
            used_memories=[mem["id"] for mem in retrieved_memories],
            prompt_tokens=usage_stats.get("prompt_tokens", 0),
            completion_tokens=usage_stats.get("completion_tokens", 0),
            total_tokens=usage_stats.get("total_tokens", 0),
            memory_count=len(retrieved_memories)
        )
        
        logger.info(f"Chat completed: {response.total_tokens} tokens, {len(retrieved_memories)} memories used")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

@app.get("/v1/memories")
async def get_memories(
    limit: int = 50,
    memory_type: Optional[str] = None,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get stored memories with optional filtering."""
    try:
        # Simple query to get recent memories
        query = "general" if not memory_type else memory_type
        memories = mem_store.search(query, k=limit)
        
        return {
            "memories": memories,
            "count": len(memories),
            "stats": mem_store.get_memory_stats()
        }
    except Exception as e:
        logger.error(f"Failed to get memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memories")

@app.post("/v1/memories")
async def store_memory(
    memory: MemoryObject,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Manually store a memory object."""
    try:
        memory_id = mem_store.write(
            memory.type,
            memory.key,
            memory.value,
            user_id=None,
            scope="user",
            ttl_days=memory.ttl_days,
            source=memory.source
        )
        
        return {
            "success": True,
            "memory_id": memory_id,
            "message": f"Memory stored: {memory.type}:{memory.key}"
        }
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store memory")

@app.delete("/v1/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Delete a specific memory by ID."""
    try:
        success = mem_store.delete_memory(memory_id)
        
        if success:
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        else:
            raise HTTPException(status_code=404, detail="Memory not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete memory")

# User Memory Management Endpoints
@app.post("/v1/memories/user")
async def store_user_memory(
    memory: MemoryObject,
    user_id: str,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Store a memory for a specific user."""
    try:
        memory_id = mem_store.write(
            memory.type,
            memory.key,
            memory.value,
            user_id=user_id,
            scope="user",
            ttl_days=memory.ttl_days,
            source=memory.source or "api"
        )
        
        return {
            "success": True,
            "memory_id": memory_id,
            "user_id": user_id,
            "message": f"User memory stored: {memory.type}:{memory.key}"
        }
    except Exception as e:
        logger.error(f"Failed to store user memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store user memory")

@app.post("/v1/memories/shared")
async def store_shared_memory(
    memory: MemoryObject,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Store a shared memory available to all users."""
    try:
        memory_id = mem_store.write(
            memory.type,
            memory.key,
            memory.value,
            user_id=None,
            scope="shared",
            ttl_days=memory.ttl_days,
            source=memory.source or "admin"
        )
        
        return {
            "success": True,
            "memory_id": memory_id,
            "scope": "shared",
            "message": f"Shared memory stored: {memory.type}:{memory.key}"
        }
    except Exception as e:
        logger.error(f"Failed to store shared memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store shared memory")

@app.get("/v1/memories/user/{user_id}")
async def get_user_memories(
    user_id: str,
    query: str = "",
    limit: int = 10,
    include_shared: bool = True,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get memories for a specific user."""
    try:
        if query:
            memories = mem_store.search(
                query, 
                user_id=user_id, 
                k=limit,
                include_shared=include_shared
            )
        else:
            # Get recent memories for user
            memories = mem_store.get_user_memories(user_id, limit=limit, include_shared=include_shared)
        
        return {
            "user_id": user_id,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        logger.error(f"Failed to get user memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user memories")

@app.get("/v1/memories/shared")
async def get_shared_memories(
    query: str = "",
    limit: int = 20,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get shared memories available to all users."""
    try:
        if query:
            memories = mem_store.search(
                query, 
                user_id=None, 
                k=limit,
                include_shared=True
            )
            # Filter to only shared memories
            memories = [m for m in memories if m.get("scope") in ("shared", "global")]
        else:
            memories = mem_store.get_shared_memories(limit=limit)
        
        return {
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        logger.error(f"Failed to get shared memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve shared memories")

@app.get("/v1/tools")
async def get_available_tools():
    """Get list of available tools and their schemas."""
    return {
        "tools": tool_dispatcher.get_available_tools(),
        "count": len(tool_dispatcher.tools)
    }

@app.post("/v1/tools/{tool_name}")
async def execute_tool(tool_name: str, parameters: dict):
    """Execute a specific tool with given parameters."""
    try:
        result = tool_dispatcher.dispatch(tool_name, parameters)
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
