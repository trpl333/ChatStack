import os
import time
import logging
from typing import List, Optional, Deque, Tuple, Dict, Any
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from config_loader import get_secret, get_setting
from app.models import ChatRequest, ChatResponse, MemoryObject
from app.llm import chat as llm_chat, chat_realtime_stream, _get_llm_config, validate_llm_connection
from app.http_memory import HTTPMemoryStore
from app.packer import pack_prompt, should_remember, extract_carry_kit_items, detect_safety_triggers
from app.tools import tool_dispatcher, parse_tool_calls, execute_tool_calls

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------
memory_store: Optional[HTTPMemoryStore] = None

# In-process rolling history per thread (survives across calls in same container)
# 500 msgs ~= ~250 user/assistant turns. Consolidation triggers at 400.
THREAD_HISTORY: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=500))

# Track which threads have been loaded from database
THREAD_LOADED: Dict[str, bool] = {}

def load_thread_history(thread_id: str, mem_store: HTTPMemoryStore, user_id: Optional[str] = None):
    """Load thread history from ai-memory database if not already loaded"""
    if THREAD_LOADED.get(thread_id):
        return  # Already loaded
    
    try:
        # Search for stored thread history
        history_key = f"thread_history:{thread_id}"
        results = mem_store.search(history_key, user_id=user_id, k=1)
        
        if results:
            value = results[0].get("value", {})
            if isinstance(value, dict) and "messages" in value:
                messages = value["messages"]
                # Restore to in-memory deque
                THREAD_HISTORY[thread_id] = deque(
                    [(msg["role"], msg["content"]) for msg in messages],
                    maxlen=500
                )
                logger.info(f"🔄 Loaded {len(messages)} messages from database for thread {thread_id}")
            else:
                logger.info(f"🧵 No stored history found for thread {thread_id}")
        
        THREAD_LOADED[thread_id] = True
    except Exception as e:
        logger.warning(f"Failed to load thread history: {e}")
        THREAD_LOADED[thread_id] = True  # Mark as attempted to avoid retry loops

def save_thread_history(thread_id: str, mem_store: HTTPMemoryStore, user_id: Optional[str] = None):
    """Save thread history to ai-memory database for persistence"""
    try:
        history = THREAD_HISTORY.get(thread_id)
        if not history:
            return
        
        # Convert deque to list of dicts
        messages = [{"role": role, "content": content} for role, content in history]
        
        # Store in ai-memory
        history_key = f"thread_history:{thread_id}"
        mem_store.write(
            memory_type="thread_recap",
            key=history_key,
            value={"messages": messages, "count": len(messages)},
            user_id=user_id,
            scope="user",
            ttl_days=7  # Keep for 7 days
        )
        logger.info(f"💾 Saved {len(messages)} messages to database for thread {thread_id}")
    except Exception as e:
        logger.warning(f"Failed to save thread history: {e}")

# Feature flags
ENABLE_RECAP = True           # write/read tiny durable recap to AI-Memory
DISCOURAGE_GUESSING = True    # add a system rail when no memories are retrieved

# -----------------------------------------------------------------------------
# Lifespan
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory_store
    logger.info("Starting NeuroSphere Orchestrator...")
    try:
        memory_store = HTTPMemoryStore()
        if memory_store.available:
            logger.info("✅ Memory store initialized")
            try:
                cleanup_count = memory_store.cleanup_expired()
                logger.info(f"🧹 Cleaned up {cleanup_count} expired memories")
            except Exception as e:
                logger.warning(f"Cleanup expired failed (non-fatal): {e}")
        else:
            logger.warning("⚠️ Memory store running in degraded mode (database unavailable)")

        if not validate_llm_connection():
            logger.warning("⚠️ LLM connection validation failed - service may be unavailable")

        yield
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        logger.info("Starting app in degraded mode...")
    finally:
        logger.info("Shutting down NeuroSphere Orchestrator...")
        try:
            if memory_store:
                memory_store.close()
        except Exception:
            pass

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(
    title="NeuroSphere Orchestrator",
    description="ChatGPT-style conversational AI with long-term memory and tool calling",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_memory_store() -> HTTPMemoryStore:
    if memory_store is None:
        raise HTTPException(status_code=503, detail="Memory store not initialized - service degraded")
    if not memory_store.available:
        raise HTTPException(status_code=503, detail="Memory store unavailable - service degraded")
    return memory_store

IMPORTANT_TYPES = {"person", "preference", "project", "rule", "moment"}

def should_store_memory(user_text: str, memory_type: str = "") -> bool:
    return (
        should_remember(user_text)
        or memory_type in IMPORTANT_TYPES
        or "remember this" in user_text.lower()
        or "save this" in user_text.lower()
    )

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "service": "NeuroSphere Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "description": "ChatGPT-style AI with memory and tools",
    }

@app.get("/admin")
async def admin_interface():
    return FileResponse("static/admin.html")

@app.get("/health")
async def health_check(mem_store: HTTPMemoryStore = Depends(get_memory_store)):
    try:
        memory_status = "connected" if mem_store.available else "unavailable"
        total_memories = 0
        if mem_store.available:
            try:
                stats = mem_store.get_memory_stats()
                total_memories = stats.get("total", 0)
            except Exception as e:
                logger.error(f"Memory stats failed: {e}")
                memory_status = "error"

        llm_status = validate_llm_connection()

        return {
            "status": "healthy" if (mem_store.available and llm_status) else "degraded",
            "memory_store": memory_status,
            "llm_service": "connected" if llm_status else "unavailable",
            "total_memories": total_memories,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# -----------------------------------------------------------------------------
# Chat with persistent thread history + optional recap
# -----------------------------------------------------------------------------
@app.post("/v1/chat", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    thread_id: str = "default",
    user_id: Optional[str] = None,
    mem_store: HTTPMemoryStore = Depends(get_memory_store),
):
    """
    Main chat completion endpoint with rolling thread history, durable recap,
    long-term memory retrieval, and tool calling.
    """
    try:
        logger.info(f"Chat request: {len(request.messages)} messages, thread={thread_id}")

        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Latest user message
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")

        # Safety rails
        safety_mode = request.safety_mode or detect_safety_triggers(user_message)
        if safety_mode:
            logger.info("🛡️ Safety mode activated")

        # Opportunistic carry-kit write
        if should_remember(user_message):
            for item in extract_carry_kit_items(user_message):
                try:
                    memory_id = mem_store.write(
                        item["type"], item["key"], item["value"],
                        user_id=user_id, scope="user", ttl_days=item.get("ttl_days", 365)
                    )
                    logger.info(f"🧠 Stored carry-kit for user {user_id}: {item['type']}:{item['key']} -> {memory_id}")
                except Exception as e:
                    logger.error(f"Carry-kit write failed: {e}")

        # Long-term memory retrieve (user-specific + shared)
        search_k = 15 if any(w in (user_message.lower()) for w in
                             ["wife","husband","family","friend","name","who is","kelly","job","work","teacher"]) else 6
        retrieved_memories = mem_store.search(user_message, user_id=user_id, k=search_k)
        logger.info(f"🔎 Retrieved {len(retrieved_memories)} relevant memories")
        
        # 🔍 DEBUG: Log what memories were actually retrieved
        if retrieved_memories:
            logger.info(f"🔍 DEBUG: Top 5 memories retrieved:")
            for i, mem in enumerate(retrieved_memories[:5]):
                mem_key = mem.get('key', 'no-key')
                mem_type = mem.get('type', 'no-type')
                mem_value_preview = str(mem.get('value', {}))[:100]
                logger.info(f"  [{i+1}] {mem_type}:{mem_key} = {mem_value_preview}")

        # Build current request messages
        message_dicts = [{"role": m.role, "content": m.content} for m in request.messages]

        # ✅ Load thread history from database if not already loaded
        if thread_id:
            load_thread_history(thread_id, mem_store, user_id)

        # Prepend rolling thread history (persistent across container restarts)
        if thread_id and THREAD_HISTORY.get(thread_id):
            hist = [{"role": r, "content": c} for (r, c) in THREAD_HISTORY[thread_id]]
            # Take last ~40 messages to keep prompt lean
            hist = hist[-40:]
            message_dicts = hist + message_dicts
            logger.info(f"🧵 Prepended {len(hist)} messages from THREAD_HISTORY[{thread_id}]")
        else:
            logger.info(f"🧵 No history found for thread_id={thread_id}")

        # Optional durable recap from AI-Memory (1 paragraph)
        if ENABLE_RECAP and thread_id and user_id:
            try:
                rec = mem_store.search(f"thread:{thread_id}:recap", user_id=user_id, k=1)
                if rec:
                    v = rec[0].get("value") or {}
                    summary = v.get("summary")
                    if summary:
                        message_dicts = [{"role":"system","content":f"Conversation recap:\n{summary}"}] + message_dicts
            except Exception as e:
                logger.warning(f"Recap load failed: {e}")

        # Add anti-guessing rail when we have no retrieved memories
        if DISCOURAGE_GUESSING and not retrieved_memories:
            message_dicts = [{"role":"system","content":
                "If you are not given a fact in retrieved memories or the current messages, say you don't know rather than guessing."}] + message_dicts
        
        # 🔍 DEBUG: Log complete message list being sent to LLM
        logger.info(f"🔍 DEBUG: Sending {len(message_dicts)} total messages to LLM:")
        for i, msg in enumerate(message_dicts[-10:]):  # Last 10 messages
            role = msg.get('role', 'unknown')
            content_preview = msg.get('content', '')[:80]
            logger.info(f"  [{i}] {role}: {content_preview}")

        # Final pack with system context + retrieved memories
        final_messages = pack_prompt(
            message_dicts,
            retrieved_memories,
            safety_mode=safety_mode,
            thread_id=thread_id
        )

        # Select path based on model
        logger.info("Calling LLM...")
        config = _get_llm_config()
        logger.info(f"🟢 Model in config: {config['model']}")

        if "realtime" in config["model"].lower():
            logger.info("🚀 Using realtime LLM")
            tokens = []
            for token in chat_realtime_stream(
                final_messages,
                temperature=request.temperature or 0.7,
                max_tokens=request.max_tokens or 800
            ):
                tokens.append(token)
            assistant_output = "".join(tokens).strip()
            usage_stats = {
                "prompt_tokens": sum(len(m.get("content","").split()) for m in final_messages),
                "completion_tokens": len(assistant_output.split()),
                "total_tokens": 0
            }
            usage_stats["total_tokens"] = usage_stats["prompt_tokens"] + usage_stats["completion_tokens"]
        else:
            logger.info("🧠 Using standard chat LLM")
            assistant_output, usage_stats = llm_chat(
                final_messages,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens
            )

        # Tool calling (if present)
        tool_results = []
        tool_calls = parse_tool_calls(assistant_output)
        if tool_calls:
            logger.info(f"🛠️ Executing {len(tool_calls)} tool calls")
            tool_results = execute_tool_calls(tool_calls)
            if tool_results:
                summaries = []
                for r in tool_results:
                    summaries.append(r["result"] if r["success"] else f"Tool error: {r['error']}")
                if summaries:
                    assistant_output += "\n\n" + "\n".join(summaries)

        # Rolling in-process history append
        try:
            if thread_id:
                last_user = next((m for m in reversed(request.messages) if m.role == "user"), None)
                if last_user:
                    THREAD_HISTORY[thread_id].append(("user", last_user.content))
                    logger.info(f"🧵 Appended USER message to THREAD_HISTORY[{thread_id}]: {last_user.content[:50]}")
                THREAD_HISTORY[thread_id].append(("assistant", assistant_output))
                logger.info(f"🧵 Appended ASSISTANT message to THREAD_HISTORY[{thread_id}]: {assistant_output[:50]}")
                logger.info(f"🧵 Total messages in THREAD_HISTORY[{thread_id}]: {len(THREAD_HISTORY[thread_id])}")
                
                # ✅ Save thread history to database for persistence across restarts
                save_thread_history(thread_id, mem_store, user_id)
        except Exception as e:
            logger.warning(f"THREAD_HISTORY append failed: {e}")

        # Opportunistic durable recap write (tiny)
        if ENABLE_RECAP and thread_id and user_id:
            try:
                last_user = next((m for m in reversed(request.messages) if m.role == "user"), None)
                snippet_user = (last_user.content if last_user else "")[:300]
                snippet_assistant = assistant_output[:400]
                recap = f"{snippet_user} || {snippet_assistant}"
                mem_store.write(
                    "thread_recap",
                    key=f"thread:{thread_id}:recap",
                    value={"summary": recap, "updated_at": time.time()},
                    user_id=user_id,
                    scope="user",
                    source="recap"
                )
            except Exception as e:
                logger.warning(f"Recap write failed: {e}")

        # Store important info as short-lived "moment"
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
                    user_id=user_id,
                    scope="user",
                    ttl_days=90
                )
            except Exception as e:
                logger.error(f"Failed to store conversation moment: {e}")

        # Response
        response = ChatResponse(
            output=assistant_output,
            used_memories=[str(mem.get("id")) for mem in retrieved_memories if isinstance(mem, dict) and mem.get("id")],
            prompt_tokens=usage_stats.get("prompt_tokens", 0),
            completion_tokens=usage_stats.get("completion_tokens", 0),
            total_tokens=usage_stats.get("total_tokens", 0),
            memory_count=len(retrieved_memories),
        )
        logger.info(f"✅ Chat completed: {response.total_tokens} tokens, memories used={len(retrieved_memories)}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

# OpenAI-style alias
@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions_alias(
    request: Request,
    thread_id: str = "default",
    user_id: Optional[str] = None,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        body = await request.json()
        chat_req = ChatRequest(**body)
        return await chat_completion(
            chat_req, thread_id=thread_id, user_id=user_id, mem_store=mem_store
        )
    except Exception as e:
        logger.error(f"Alias /v1/chat/completions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Alias failed: {str(e)}")

# -----------------------------------------------------------------------------
# Memory APIs (unchanged interfaces)
# -----------------------------------------------------------------------------
@app.get("/v1/memories")
async def get_memories(
    limit: int = 50,
    memory_type: Optional[str] = None,
    user_id: Optional[str] = None,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        if user_id:
            memories = mem_store.get_user_memories(user_id, limit=limit, include_shared=True)
        else:
            query = "general" if not memory_type else memory_type
            memories = mem_store.search(query, k=limit)
        return {"memories": memories, "count": len(memories), "stats": mem_store.get_memory_stats()}
    except Exception as e:
        logger.error(f"Failed to get memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memories")

@app.post("/v1/memories")
async def store_memory(
    memory: MemoryObject,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        memory_id = mem_store.write(
            memory.type, memory.key, memory.value,
            user_id=None, scope="shared",
            ttl_days=memory.ttl_days, source=memory.source
        )
        return {"success": True, "id": memory_id, "memory_id": memory_id,
                "message": f"Memory stored: {memory.type}:{memory.key}"}
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store memory")

@app.delete("/v1/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        success = mem_store.delete_memory(memory_id)
        if success:
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        raise HTTPException(status_code=404, detail="Memory not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete memory")

@app.post("/v1/memories/user")
async def store_user_memory(
    memory: MemoryObject,
    user_id: str,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        memory_id = mem_store.write(
            memory.type, memory.key, memory.value,
            user_id=user_id, scope="user",
            ttl_days=memory.ttl_days, source=memory.source or "api"
        )
        return {"success": True, "memory_id": memory_id, "user_id": user_id,
                "message": f"User memory stored: {memory.type}:{memory.key}"}
    except Exception as e:
        logger.error(f"Failed to store user memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store user memory")

@app.post("/v1/memories/shared")
async def store_shared_memory(
    memory: MemoryObject,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        memory_id = mem_store.write(
            memory.type, memory.key, memory.value,
            user_id=None, scope="shared",
            ttl_days=memory.ttl_days, source=memory.source or "admin"
        )
        return {"success": True, "memory_id": memory_id, "scope": "shared",
                "message": f"Shared memory stored: {memory.type}:{memory.key}"}
    except Exception as e:
        logger.error(f"Failed to store shared memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store shared memory")

@app.get("/v1/memories/user/{user_id}")
async def get_user_memories(
    user_id: str,
    query: str = "",
    limit: int = 10,
    include_shared: bool = True,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        if query:
            memories = mem_store.search(query, user_id=user_id, k=limit, include_shared=include_shared)
        else:
            memories = mem_store.get_user_memories(user_id, limit=limit, include_shared=include_shared)
        return {"user_id": user_id, "memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Failed to get user memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user memories")

@app.get("/v1/memories/shared")
async def get_shared_memories(
    query: str = "",
    limit: int = 20,
    mem_store: HTTPMemoryStore = Depends(get_memory_store)
):
    try:
        if query:
            memories = mem_store.search(query, user_id=None, k=limit, include_shared=True)
            memories = [m for m in memories if m.get("scope") in ("shared", "global")]
        else:
            memories = mem_store.get_shared_memories(limit=limit)
        return {"memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Failed to get shared memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve shared memories")

@app.get("/v1/tools")
async def get_available_tools():
    return {"tools": tool_dispatcher.get_available_tools(), "count": len(tool_dispatcher.tools)}

@app.post("/v1/tools/{tool_name}")
async def execute_tool(tool_name: str, parameters: dict):
    try:
        return tool_dispatcher.dispatch(tool_name, parameters)
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")

# -----------------------------------------------------------------------------
# Entrypoint (dev)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(get_setting("port", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
