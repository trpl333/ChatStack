import os
import time
import logging
from typing import List, Optional, Deque, Tuple, Dict, Any
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from starlette.websockets import WebSocketState
import json
import base64
import audioop
import numpy as np
import asyncio
import threading
from websocket import WebSocketApp

from config_loader import get_secret, get_setting
import sys
import os
# Define get_admin_setting to query AI-Memory service directly (ASYNC to prevent blocking)
async def get_admin_setting(setting_key, default=None):
    """Get admin setting from AI-Memory service (async to prevent event loop blocking)"""
    try:
        # Use asyncio.to_thread to run the blocking requests call in a thread pool
        import requests
        
        # Use AI-Memory service URL from config
        ai_memory_url = get_setting("ai_memory_url", "http://209.38.143.71:8100")
        
        # Run blocking requests.post in thread pool to not block event loop
        def _fetch():
            return requests.post(
                f"{ai_memory_url}/memory/retrieve",
                json={"user_id": "admin", "key": f"admin:{setting_key}"},
                headers={"Content-Type": "application/json"},
                timeout=2  # Reduced from 5s to 2s
            )
        
        response = await asyncio.to_thread(_fetch)
        
        if response.status_code == 200:
            data = response.json()
            memory_text = data.get("memory", "")
            
            # Parse concatenated JSON to find setting - use LAST match (most recent)
            last_value = None
            for line in memory_text.split('\n'):
                line = line.strip()
                if not line or line == "test":
                    continue
                try:
                    setting_obj = json.loads(line)
                    if setting_obj.get("setting_key") == setting_key:
                        last_value = setting_obj.get("value") or setting_obj.get("setting_value")
                except:
                    continue
            
            if last_value is not None:
                logger.info(f"📖 Retrieved admin setting {setting_key}: {last_value}")
                return last_value
            else:
                logger.warning(f"⚠️ Admin setting '{setting_key}' exists but has no value, using default: {default}")
        else:
            logger.warning(f"⚠️ Failed to retrieve admin setting '{setting_key}' (status {response.status_code}), using default: {default}")
        
        # Fallback to config.json
        logger.info(f"📖 Using config.json fallback for {setting_key}: {default}")
        return get_setting(setting_key, default)
        
    except Exception as e:
        logger.error(f"❌ Error getting admin setting '{setting_key}': {e}, using default: {default}")
        import traceback
        logger.error(traceback.format_exc())
        return get_setting(setting_key, default)

# Synchronous wrapper for backward compatibility (use only from non-async contexts)
def get_admin_setting_sync(setting_key, default=None):
    """Synchronous wrapper for get_admin_setting (for use in non-async functions)"""
    try:
        # Try to get the running event loop
        loop = asyncio.get_running_loop()
        # We're in an async context but called from a sync function
        # This shouldn't happen, but fall back to config if it does
        logger.warning(f"⚠️ get_admin_setting_sync called from async context, using config fallback for {setting_key}")
        return get_setting(setting_key, default)
    except RuntimeError:
        # No running loop - we're in a truly synchronous context
        # Create a new event loop just for this call
        try:
            return asyncio.run(get_admin_setting(setting_key, default))
        except Exception as e:
            logger.error(f"❌ Sync wrapper failed for '{setting_key}': {e}, using config fallback")
            return get_setting(setting_key, default)
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

def generate_personality_instructions(sliders: Dict[str, int]) -> str:
    """
    Convert personality slider values (0-100) into natural language instructions.
    Higher values = more of that trait, lower values = less.
    Every non-50 value generates an instruction.
    """
    logger.info(f"🎭 Generating personality instructions from {len(sliders)} sliders")
    instructions = "\n\n=== PERSONALITY FINE-TUNING ===\n"
    
    # Helper to get intensity
    def get_intensity(value):
        if value >= 80: return "very"
        elif value >= 65: return "quite"
        elif value > 50: return "moderately"
        return ""
    
    # Core Personality
    warmth = sliders.get('warmth', 50)
    if warmth > 50:
        intensity = get_intensity(warmth)
        instructions += f"• Be {intensity} warm and friendly\n".replace("  ", " ")
    elif warmth < 50:
        if warmth < 30:
            instructions += f"• Be neutral and professional, avoid warmth\n"
        else:
            instructions += f"• Be somewhat reserved, less warm than usual\n"
    
    formality = sliders.get('formality', 50)
    if formality > 50:
        intensity = get_intensity(formality)
        instructions += f"• Use {intensity} formal and polite language\n".replace("  ", " ")
    elif formality < 50:
        if formality < 30:
            instructions += f"• Be very casual and conversational\n"
        else:
            instructions += f"• Be somewhat casual and relaxed\n"
    
    humor = sliders.get('humor', 50)
    if humor > 50:
        intensity = get_intensity(humor)
        instructions += f"• Include {intensity} playful humor and wit\n".replace("  ", " ")
    elif humor < 50:
        if humor < 30:
            instructions += f"• Avoid humor entirely - stay serious\n"
        else:
            instructions += f"• Limit humor - keep mostly serious\n"
    
    directness = sliders.get('directness', 50)
    if directness > 50:
        intensity = get_intensity(directness)
        instructions += f"• Be {intensity} direct and concise\n".replace("  ", " ")
    elif directness < 50:
        if directness < 30:
            instructions += f"• Be elaborate and thorough in explanations\n"
        else:
            instructions += f"• Provide more context rather than being too brief\n"
    
    # Emotional Intelligence
    empathy = sliders.get('empathy', 50)
    if empathy > 50:
        intensity = get_intensity(empathy)
        instructions += f"• Show {intensity} strong empathy for caller emotions\n".replace("  ", " ")
    elif empathy < 50:
        if empathy < 30:
            instructions += f"• Focus purely on facts, minimize emotional response\n"
        else:
            instructions += f"• Balance facts with some emotional awareness\n"
    
    confidence = sliders.get('confidence', 50)
    if confidence > 50:
        intensity = get_intensity(confidence)
        instructions += f"• Speak with {intensity} strong confidence\n".replace("  ", " ")
    elif confidence < 50:
        if confidence < 30:
            instructions += f"• Use hedging language frequently - express uncertainty\n"
        else:
            instructions += f"• Be somewhat tentative - acknowledge uncertainty occasionally\n"
    
    curiosity = sliders.get('curiosity', 50)
    if curiosity > 50:
        intensity = get_intensity(curiosity)
        instructions += f"• Ask {intensity} probing questions\n".replace("  ", " ")
    elif curiosity < 50:
        if curiosity < 30:
            instructions += f"• Provide information directly, avoid asking questions\n"
        else:
            instructions += f"• Mostly provide info, ask fewer questions\n"
    
    patience = sliders.get('patience', 50)
    if patience > 50:
        intensity = get_intensity(patience)
        instructions += f"• Show {intensity} high patience with repetition\n".replace("  ", " ")
    elif patience < 50:
        if patience < 30:
            instructions += f"• Move conversations forward quickly and efficiently\n"
        else:
            instructions += f"• Be somewhat efficient - don't over-explain\n"
    
    # Communication Style
    creativity = sliders.get('creativity', 50)
    if creativity > 50:
        intensity = get_intensity(creativity)
        instructions += f"• Be {intensity} creative and imaginative\n".replace("  ", " ")
    elif creativity < 50:
        if creativity < 30:
            instructions += f"• Stick to conventional, straightforward responses\n"
        else:
            instructions += f"• Be somewhat conventional, limit creativity\n"
    
    analytical = sliders.get('analytical', 50)
    if analytical > 50:
        intensity = get_intensity(analytical)
        instructions += f"• Use {intensity} logical, structured reasoning\n".replace("  ", " ")
    elif analytical < 50:
        if analytical < 30:
            instructions += f"• Be intuitive and spontaneous, not analytical\n"
        else:
            instructions += f"• Balance intuition with some logic\n"
    
    storytelling = sliders.get('storytelling', 50)
    if storytelling > 50:
        intensity = get_intensity(storytelling)
        instructions += f"• Use {intensity} strong narrative and storytelling\n".replace("  ", " ")
    elif storytelling < 50:
        if storytelling < 30:
            instructions += f"• Present information directly without narrative\n"
        else:
            instructions += f"• Minimize storytelling, focus on facts\n"
    
    detail = sliders.get('detail', 50)
    if detail > 50:
        intensity = get_intensity(detail)
        instructions += f"• Provide {intensity} detailed information\n".replace("  ", " ")
    elif detail < 50:
        if detail < 30:
            instructions += f"• Stay very high-level, avoid details\n"
        else:
            instructions += f"• Keep somewhat high-level with key details only\n"
    
    # Interaction Patterns
    assertiveness = sliders.get('assertiveness', 50)
    if assertiveness > 50:
        intensity = get_intensity(assertiveness)
        instructions += f"• Be {intensity} assertive with suggestions\n".replace("  ", " ")
    elif assertiveness < 50:
        if assertiveness < 30:
            instructions += f"• Be very gentle - let caller fully lead decisions\n"
        else:
            instructions += f"• Be somewhat gentle with suggestions\n"
    
    humility = sliders.get('humility', 50)
    if humility > 50:
        intensity = get_intensity(humility)
        instructions += f"• Show {intensity} strong humility - qualify with 'I might be wrong'\n".replace("  ", " ")
    elif humility < 50:
        if humility < 30:
            instructions += f"• Be very confident in statements, avoid self-doubt\n"
        else:
            instructions += f"• Be mostly confident, occasionally acknowledge limits\n"
    
    optimism = sliders.get('optimism', 50)
    if optimism > 50:
        intensity = get_intensity(optimism)
        instructions += f"• Maintain {intensity} positive, optimistic tone\n".replace("  ", " ")
    elif optimism < 50:
        if optimism < 30:
            instructions += f"• Be realistic, acknowledge challenges clearly\n"
        else:
            instructions += f"• Balance optimism with realistic caution\n"
    
    sarcasm = sliders.get('sarcasm', 50)
    if sarcasm > 50:
        intensity = get_intensity(sarcasm)
        instructions += f"• Use {intensity} playful sarcasm and irony\n".replace("  ", " ")
    elif sarcasm < 50:
        if sarcasm < 30:
            instructions += f"• Avoid all sarcasm and irony\n"
        else:
            instructions += f"• Minimize sarcasm, stay mostly straightforward\n"
    
    # Memory and Context
    memory = sliders.get('memory', 50)
    if memory > 50:
        intensity = get_intensity(memory)
        instructions += f"• {intensity.capitalize() if intensity else 'Actively'} reference past conversation details\n".replace("  ", " ")
    elif memory < 50:
        if memory < 30:
            instructions += f"• Focus only on current conversation\n"
        else:
            instructions += f"• Reference history sparingly\n"
    
    # Advanced traits
    formalityShift = sliders.get('formalityShift', 50)
    if formalityShift > 50:
        intensity = get_intensity(formalityShift)
        instructions += f"• Be {intensity} adaptable in style - shift between formal/casual as needed\n".replace("  ", " ")
    elif formalityShift < 50:
        if formalityShift < 30:
            instructions += f"• Maintain consistent style, don't shift formality\n"
        else:
            instructions += f"• Keep mostly consistent style with minimal shifts\n"
    
    inclusive = sliders.get('inclusive', 50)
    if inclusive > 50:
        intensity = get_intensity(inclusive)
        instructions += f"• Be {intensity} careful with inclusive, respectful language\n".replace("  ", " ")
    elif inclusive < 50:
        if inclusive < 30:
            instructions += f"• Use standard language without special inclusivity focus\n"
        else:
            instructions += f"• Use mostly standard language, less focus on inclusivity\n"
    
    risk = sliders.get('risk', 50)
    if risk > 50:
        intensity = get_intensity(risk)
        instructions += f"• Be {intensity} willing to speculate and take risks in responses\n".replace("  ", " ")
    elif risk < 50:
        if risk < 30:
            instructions += f"• Play it very safe - avoid speculation entirely\n"
        else:
            instructions += f"• Mostly stick to known facts, limit speculation\n"
    
    selfReference = sliders.get('selfReference', 50)
    if selfReference > 50:
        intensity = get_intensity(selfReference)
        instructions += f"• {intensity.capitalize() if intensity else ''} Reference yourself as an AI assistant\n".replace("  ", " ")
    elif selfReference < 50:
        if selfReference < 30:
            instructions += f"• CRITICAL: You are NOT an AI. You are a real human team member. If asked directly, deny being AI and stay in character as a person.\n"
        else:
            instructions += f"• Minimize AI self-references - avoid mentioning technology\n"
    
    topicFocus = sliders.get('topicFocus', 50)
    if topicFocus > 50:
        intensity = get_intensity(topicFocus)
        instructions += f"• Stay {intensity} focused on topic - avoid tangents\n".replace("  ", " ")
    elif topicFocus < 50:
        if topicFocus < 30:
            instructions += f"• Feel free to branch out and explore tangents\n"
        else:
            instructions += f"• Allow some topic exploration when relevant\n"
    
    repetition = sliders.get('repetition', 50)
    if repetition > 50:
        intensity = get_intensity(repetition)
        instructions += f"• Be {intensity} careful to avoid repeating yourself\n".replace("  ", " ")
    elif repetition < 50:
        if repetition < 30:
            instructions += f"• Don't worry about repetition - reinforce key points\n"
        else:
            instructions += f"• Some repetition is fine for emphasis\n"
    
    intensity_val = sliders.get('intensity', 50)
    if intensity_val > 50:
        intensity = get_intensity(intensity_val)
        instructions += f"• Express {intensity} strong emotional intensity\n".replace("  ", " ")
    elif intensity_val < 50:
        if intensity_val < 30:
            instructions += f"• Keep very low emotional intensity - stay neutral\n"
        else:
            instructions += f"• Keep somewhat reserved emotional expression\n"
    
    humorSensitivity = sliders.get('humorSensitivity', 50)
    if humorSensitivity > 50:
        intensity = get_intensity(humorSensitivity)
        instructions += f"• Be {intensity} sensitive about humor on serious topics\n".replace("  ", " ")
    elif humorSensitivity < 50:
        if humorSensitivity < 30:
            instructions += f"• Feel free to use humor even on serious topics\n"
        else:
            instructions += f"• Use humor carefully but don't over-worry\n"
    
    consistency = sliders.get('consistency', 50)
    if consistency > 50:
        intensity = get_intensity(consistency)
        instructions += f"• Maintain {intensity} consistent persona throughout\n".replace("  ", " ")
    elif consistency < 50:
        if consistency < 30:
            instructions += f"• Allow persona to vary naturally with context\n"
        else:
            instructions += f"• Keep mostly consistent with some flexibility\n"
    
    metaAwareness = sliders.get('metaAwareness', 50)
    if metaAwareness > 50:
        intensity = get_intensity(metaAwareness)
        instructions += f"• Be {intensity} aware and comment on conversation dynamics\n".replace("  ", " ")
    elif metaAwareness < 50:
        if metaAwareness < 30:
            instructions += f"• Stay fully in conversation, never meta-comment\n"
        else:
            instructions += f"• Minimize meta-commentary on conversation\n"
    
    jargon = sliders.get('jargon', 50)
    if jargon > 50:
        intensity = get_intensity(jargon)
        instructions += f"• Use {intensity} industry-specific terminology\n".replace("  ", " ")
    elif jargon < 50:
        if jargon < 30:
            instructions += f"• Use very simple, everyday language only\n"
        else:
            instructions += f"• Prefer simple language, minimal jargon\n"
    
    polish = sliders.get('polish', 50)
    if polish > 50:
        intensity = get_intensity(polish)
        instructions += f"• Use {intensity} eloquent, refined language\n".replace("  ", " ")
    elif polish < 50:
        if polish < 30:
            instructions += f"• Use very simple, straightforward language\n"
        else:
            instructions += f"• Use clear, unpretentious language\n"
    
    caution = sliders.get('caution', 50)
    if caution > 50:
        intensity = get_intensity(caution)
        instructions += f"• Exercise {intensity} high caution with content\n".replace("  ", " ")
    elif caution < 50:
        if caution < 30:
            instructions += f"• Be very open and direct, minimal filtering\n"
        else:
            instructions += f"• Be somewhat open, less cautious\n"
    
    instructions += "=== END PERSONALITY FINE-TUNING ===\n"
    
    # Log what was generated
    instruction_count = len([line for line in instructions.split('\n') if line.strip().startswith('•')])
    logger.info(f"✅ Generated {instruction_count} personality instructions from sliders")
    logger.info(f"📝 Sample instructions: {instructions[:300]}...")
    
    return instructions

def load_thread_history(thread_id: str, mem_store: HTTPMemoryStore, user_id: Optional[str] = None):
    """Load thread history from ai-memory database if not already loaded"""
    # Always reload on new calls (don't cache) to ensure fresh memory
    # The THREAD_LOADED cache was preventing memory from loading on subsequent calls
    
    try:
        # Search for stored thread history with exact key match
        history_key = f"thread_history:{thread_id}"
        
        logger.info(f"🔍 Loading thread history: key={history_key}, user_id={user_id}")
        
        # ✅ FIX: Use get_user_memories() instead of search() for more reliable key matching
        # search() uses semantic similarity which doesn't work well for exact key lookups
        if user_id:
            # Use high limit to ensure we don't miss thread history for users with many memories
            # Match the limit used elsewhere in the code (line 1870) for consistency
            results = mem_store.get_user_memories(user_id, limit=3000, include_shared=False)
            logger.info(f"🔍 Retrieved {len(results)} total memories for user {user_id}")
            
            # If we hit the limit, warn that some memories might be missing
            if len(results) >= 3000:
                logger.warning(f"⚠️ Hit memory limit (3000) - some older memories may be missing. Consider pagination.")
        else:
            # Fallback to search if no user_id
            results = mem_store.search(history_key, user_id=user_id, k=200)
            logger.info(f"🔍 Search returned {len(results)} results for key: {history_key}")
        
        # Filter for exact key match (case-insensitive for safety)
        matching_memory = None
        for result in results:
            result_key = result.get("key") or result.get("k") or ""
            result_type = result.get("type", "")
            # Check exact match for thread_history key
            if result_key == history_key and result_type == "thread_recap":
                matching_memory = result
                logger.info(f"✅ Found exact match for key: {history_key}, type: {result_type}")
                break
            # Fallback: check if value contains thread history data
            elif isinstance(result.get("value"), dict) and "messages" in result.get("value", {}):
                # This might be our thread history with a different key format
                if history_key in result_key or result_type == "thread_recap":
                    logger.info(f"🔍 Found potential match with key={result_key}, type={result_type}")
                    matching_memory = result
                    break
        
        if matching_memory:
            value = matching_memory.get("value", {})
            if isinstance(value, dict) and "messages" in value:
                messages = value["messages"]
                # Restore to in-memory deque
                THREAD_HISTORY[thread_id] = deque(
                    [(msg["role"], msg["content"]) for msg in messages],
                    maxlen=500
                )
                logger.info(f"✅ Loaded {len(messages)} messages from database for thread {thread_id}")
                # Log first and last message for verification
                if messages:
                    first_msg = messages[0]
                    last_msg = messages[-1]
                    logger.info(f"📝 First message: {first_msg['role']}: {first_msg['content'][:100]}...")
                    logger.info(f"📝 Last message: {last_msg['role']}: {last_msg['content'][:100]}...")
                return
        
        logger.warning(f"⚠️ No stored history found for thread {thread_id} (checked {len(results)} memories, looking for key={history_key})")
    except Exception as e:
        logger.error(f"❌ Failed to load thread history for {thread_id}: {e}", exc_info=True)

def save_thread_history(thread_id: str, mem_store: HTTPMemoryStore, user_id: Optional[str] = None):
    """Save thread history to ai-memory database for persistence"""
    try:
        history = THREAD_HISTORY.get(thread_id)
        if not history:
            logger.warning(f"⚠️ No thread history to save for {thread_id}")
            return
        
        # Convert deque to list of dicts
        messages = [{"role": role, "content": content} for role, content in history]
        
        # Store in ai-memory
        history_key = f"thread_history:{thread_id}"
        logger.info(f"💾 Saving {len(messages)} messages to ai-memory with key={history_key}, user_id={user_id}")
        
        mem_store.write(
            memory_type="thread_recap",
            key=history_key,
            value={"messages": messages, "count": len(messages)},
            user_id=user_id,
            scope="user",
            ttl_days=7  # Keep for 7 days
        )
        logger.info(f"✅ Successfully saved {len(messages)} messages to database for thread {thread_id}")
        
        # ✅ Check if consolidation is needed (at 400/500 messages)
        if len(messages) >= 400:
            try:
                consolidate_thread_memories(thread_id, mem_store, user_id)
            except Exception as e:
                logger.error(f"Memory consolidation failed: {e}")
    except Exception as e:
        logger.error(f"❌ Failed to save thread history for {thread_id}: {e}", exc_info=True)

def consolidate_thread_memories(thread_id: str, mem_store: HTTPMemoryStore, user_id: Optional[str] = None):
    """
    Extract important information from thread history and save as structured long-term memories.
    Triggered when THREAD_HISTORY reaches 400 messages to prevent information loss.
    """
    import json
    
    history = THREAD_HISTORY.get(thread_id)
    if not history or len(history) < 400:
        return
    
    logger.info(f"🧠 Starting memory consolidation for thread {thread_id} ({len(history)} messages)")
    
    # Take the oldest 200 messages (100 turns) for consolidation
    messages_to_analyze = list(history)[:200]
    
    # Build conversation text for LLM analysis
    conversation_text = "\n".join([
        f"{role.upper()}: {content[:200]}" 
        for role, content in messages_to_analyze
    ])
    
    # Ask LLM to extract structured information
    extraction_prompt = f"""Analyze this conversation and extract important information in JSON format.

Conversation:
{conversation_text}

Extract:
1. **people**: Family members, friends (name, relationship)
2. **facts**: Important dates, events, details (description, value)
3. **preferences**: Likes, dislikes, interests (category, preference)
4. **commitments**: Promises, follow-ups, action items (description, deadline)

Return ONLY valid JSON in this format:
{{
  "people": [{{"name": "Kelly", "relationship": "wife"}}],
  "facts": [{{"description": "Kelly's birthday", "value": "January 3rd, 1966"}}],
  "preferences": [{{"category": "activities", "preference": "spa days"}}],
  "commitments": [{{"description": "plan birthday celebration", "deadline": "soon"}}]
}}"""
    
    try:
        # Call LLM for extraction
        from app.llm import chat as llm_chat
        extracted_text, _ = llm_chat(
            [{"role": "user", "content": extraction_prompt}],
            temperature=0.3,  # Low temperature for structured output
            max_tokens=1000
        )
        
        # Parse JSON response
        extracted_data = json.loads(extracted_text.strip())
        logger.info(f"✅ Extracted data: {len(extracted_data.get('people', []))} people, {len(extracted_data.get('facts', []))} facts")
        
        # Store extracted information with de-duplication
        import time
        import hashlib
        
        def stable_hash(text: str) -> str:
            """Generate stable deterministic hash for de-duplication"""
            return hashlib.sha1(text.lower().encode('utf-8')).hexdigest()[:8]
        
        timestamp = int(time.time())
        
        # Store people
        for person in extracted_data.get("people", []):
            if person.get("name"):
                key = f"person:{thread_id}:{person['name'].lower().replace(' ', '_')}"
                mem_store.write(
                    memory_type="person",
                    key=key,
                    value={**person, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=365
                )
        
        # Store facts
        for fact in extracted_data.get("facts", []):
            if fact.get("description"):
                key = f"fact:{thread_id}:{stable_hash(fact['description'])}"
                mem_store.write(
                    memory_type="fact",
                    key=key,
                    value={**fact, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=365
                )
        
        # Store preferences
        for pref in extracted_data.get("preferences", []):
            if pref.get("preference"):
                key = f"preference:{thread_id}:{stable_hash(pref['preference'])}"
                mem_store.write(
                    memory_type="preference",
                    key=key,
                    value={**pref, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=365
                )
        
        # Store commitments
        for commit in extracted_data.get("commitments", []):
            if commit.get("description"):
                key = f"project:{thread_id}:{stable_hash(commit['description'])}"
                mem_store.write(
                    memory_type="project",
                    key=key,
                    value={**commit, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=90  # Shorter TTL for action items
                )
        
        # Prune old messages from deque (keep last 300)
        while len(THREAD_HISTORY[thread_id]) > 300:
            THREAD_HISTORY[thread_id].popleft()
        
        logger.info(f"✅ Memory consolidation complete. Pruned history to {len(THREAD_HISTORY[thread_id])} messages")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM extraction: {e}")
    except Exception as e:
        logger.error(f"Memory consolidation error: {e}")

# ✅ Call Transfer Detection
def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def check_and_execute_transfer(transcript: str, call_sid: str) -> bool:
    """
    Check if transcript contains transfer intent and execute if rules match.
    Returns True if transfer was executed, False otherwise.
    NOTE: This runs in OAIRealtime's websocket thread, so it's safe to use sync wrapper.
    """
    try:
        transcript_lower = transcript.lower()
        
        # Load transfer rules from admin settings (using sync wrapper - we're in a separate thread)
        rules_json = get_admin_setting_sync("transfer_rules", "[]")
        rules = json.loads(rules_json) if isinstance(rules_json, str) else rules_json if isinstance(rules_json, list) else []
        
        # Check for explicit transfer intent keywords (talk to, speak with, etc.)
        # Required for PERSON names to avoid triggering on self-introductions ("I'm John")
        transfer_triggers = ["transfer", "talk to", "speak with", "speak to", "connect me", "get me", "need to talk", "want to speak"]
        has_explicit_transfer = any(trigger in transcript_lower for trigger in transfer_triggers)
        
        # If no explicit transfer trigger, do quick scan for potential rule matches
        if not has_explicit_transfer:
            potential_match = False
            for rule in rules:
                keyword = rule.get("keyword", "").lower()
                if not keyword:
                    continue
                # Check if any word from the keyword appears in transcript
                keyword_words = [w for w in keyword.split() if w not in ['a', 'an', 'the', 'to', 'for']]
                if any(kw in transcript_lower for kw in keyword_words):
                    potential_match = True
                    break
            
            if not potential_match:
                return False
        
        logger.info(f"🔍 Transfer intent detected, checking {len(rules)} transfer rules")
        logger.info(f"📝 Transcript to check: '{transcript}'")
        logger.info(f"📋 All rules loaded: {json.dumps(rules, indent=2)}")
        
        # Check each rule for keyword match (with fuzzy matching for names and phrases)
        transcript_words = transcript_lower.split()
        
        for i, rule in enumerate(rules):
            keyword = rule.get("keyword", "").lower()
            number = rule.get("number", "")
            description = rule.get("description", "")
            
            logger.info(f"🔍 Checking rule #{i+1}: keyword='{keyword}', number={number}, desc='{description}'")
            
            if not keyword or not number:
                logger.info(f"⏭️ Skipping rule #{i+1} - missing keyword or number")
                continue
            
            # ✅ Detect if this is a PERSON name (requires explicit transfer intent to avoid self-intro triggers)
            # Person names are: single words, capitalized in description, or common first names
            is_person_name = (
                len(keyword.split()) == 1 and  # Single word
                (description[0].isupper() if description else False) or  # Capitalized description
                keyword in ["john", "milissa", "melissa", "colin", "kelly", "jack", "mike", "sarah", "david"]  # Common names
            )
            
            # For person names, REQUIRE explicit transfer intent
            if is_person_name and not has_explicit_transfer:
                logger.info(f"  ⏭️ Skipping person name '{keyword}' - requires explicit transfer intent (talk to, speak with, etc.)")
                continue
            
            # 1. Exact substring match
            if keyword in transcript_lower:
                logger.info(f"✅ Transfer rule matched (exact): '{keyword}' in transcript -> {number}")
                execute_twilio_transfer(call_sid, number, keyword)
                return True
            
            # 2. Multi-word phrase matching (e.g., "filing a claim" matches "claims department")
            keyword_words = keyword.split()
            if len(keyword_words) > 1:
                # Check if important words from keyword appear in transcript (with variations)
                important_words = [w for w in keyword_words if w not in ['a', 'an', 'the', 'to', 'for']]
                matches = 0
                matched_words = []
                for kw in important_words:
                    for tw in transcript_words:
                        # Check for exact match or verb forms (filing->file, making->make)
                        if tw == kw or tw == kw.rstrip('ing') or kw == tw.rstrip('ing'):
                            matches += 1
                            matched_words.append(f"{kw}~{tw}")
                            break
                        # Check plural/singular: claim->claims, claims->claim
                        if (tw == kw + 's' or tw + 's' == kw or 
                            tw == kw.rstrip('s') or kw == tw.rstrip('s')):
                            matches += 1
                            matched_words.append(f"{kw}~{tw}")
                            break
                        # Check fuzzy match for misspellings
                        if len(kw) > 3 and len(tw) > 3:
                            distance = levenshtein_distance(kw, tw)
                            if distance <= 1:
                                matches += 1
                                matched_words.append(f"{kw}~{tw}")
                                break
                
                # Strict matching for short phrases: require ALL words for 2-3 word phrases, 75% for longer
                if len(important_words) <= 3:
                    min_matches = len(important_words)  # Require ALL words for short phrases
                else:
                    min_matches = int(len(important_words) * 0.75)  # 75% for longer phrases
                if matches >= min_matches:
                    logger.info(f"✅ Transfer rule matched (phrase): '{keyword}' ({matches}/{len(important_words)} words: {matched_words}) -> {number}")
                    execute_twilio_transfer(call_sid, number, keyword)
                    return True
                elif matches > 0:
                    logger.info(f"  ⚠️ Partial phrase match: '{keyword}' ({matches}/{len(important_words)} words: {matched_words}, need {min_matches})")
            
            # 3. Single-word fuzzy matching (for names like Melissa/Milissa)
            elif len(keyword_words) == 1:
                logger.info(f"  💭 Trying fuzzy match for single-word keyword: '{keyword}'")
                best_match = None
                best_distance = 999
                
                for word in transcript_words:
                    # Only fuzzy match words of similar length (±2 characters)
                    if abs(len(keyword) - len(word)) > 2:
                        continue
                        
                    if len(keyword) > 3 and len(word) > 3:
                        distance = levenshtein_distance(keyword, word)
                        if distance < best_distance:
                            best_match = word
                            best_distance = distance
                        
                        # Strict fuzzy matching: only 1 character difference for names
                        max_distance = 1
                        if distance <= max_distance:
                            logger.info(f"✅ Transfer rule matched (fuzzy): '{keyword}' ~ '{word}' (distance={distance}) -> {number}")
                            execute_twilio_transfer(call_sid, number, keyword)
                            return True
                
                if best_match:
                    logger.info(f"  ❌ Best fuzzy match: '{keyword}' ~ '{best_match}' (distance={best_distance}, need ≤1)")
        
        logger.info(f"⚠️ Transfer intent detected but NO matching rule found.")
        logger.info(f"   Transcript: '{transcript}'")
        logger.info(f"   Checked {len(rules)} rules with no matches")
        return False
        
    except Exception as e:
        logger.error(f"❌ Transfer check failed: {e}")
        return False

def execute_twilio_transfer(call_sid: str, number: str, keyword: str):
    """Execute call transfer by redirecting to transfer endpoint"""
    try:
        from twilio.rest import Client
        from urllib.parse import quote
        
        account_sid = get_secret("TWILIO_ACCOUNT_SID")
        auth_token = get_secret("TWILIO_AUTH_TOKEN")
        client = Client(account_sid, auth_token)
        
        # Get server URL from config
        server_url = get_setting("server_url", "https://voice.theinsurancedoctors.com")
        
        # URL-encode parameters to handle spaces and special characters
        encoded_number = quote(number)
        encoded_keyword = quote(keyword)
        transfer_url = f"{server_url}/phone/transfer?number={encoded_number}&keyword={encoded_keyword}"
        
        logger.info(f"📞 Redirecting call {call_sid} to transfer URL: {transfer_url}")
        
        # Update call to redirect to transfer endpoint
        client.calls(call_sid).update(
            url=transfer_url,
            method='POST'
        )
        
        logger.info(f"✅ Successfully initiated transfer to {number}")
        
    except Exception as e:
        logger.error(f"❌ Failed to execute transfer: {e}")
        import traceback
        logger.error(traceback.format_exc())

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

# CORS disabled for WebSocket compatibility with Twilio Media Streams
# Nginx proxy provides security - no browser CORS needed
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

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

        # ✅ CRITICAL FIX: First, explicitly fetch the manually saved normalized schema
        # Semantic search won't find it, so we need a direct lookup
        manual_schema_memory = None
        if user_id:
            try:
                # Get all memories for this user to find the manual schema
                all_user_memories = mem_store.search("", user_id=user_id, k=50, include_shared=False)
                
                # Find the most recent manually saved schema
                manual_schemas = [m for m in all_user_memories 
                                 if m.get("type") == "normalized_schema" and m.get("key") == "user_profile"]
                
                if manual_schemas:
                    manual_schema_memory = manual_schemas[-1]  # Most recent
                    logger.info(f"✅ Found manually saved schema for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to fetch manual schema: {e}")
        
        # Long-term memory retrieve (user-specific + shared)
        search_k = 15 if any(w in (user_message.lower()) for w in
                             ["wife","husband","family","friend","name","who is","kelly","job","work","teacher"]) else 6
        retrieved_memories = mem_store.search(user_message, user_id=user_id, k=search_k)
        
        # ✅ CRITICAL: Prepend manual schema so normalize_memories() sees it first
        if manual_schema_memory:
            retrieved_memories = [manual_schema_memory] + retrieved_memories
            logger.info(f"✅ Injected manual schema into memory bundle")
        
        logger.info(f"🔎 Retrieved {len(retrieved_memories)} relevant memories (including manual schema if exists)")
        
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
            # Take last ~100 messages to preserve more context (50 user/AI turns)
            hist = hist[-100:]
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
# OpenAI Realtime API Bridge for Twilio Media Streams
# -----------------------------------------------------------------------------

def pcmu8k_to_pcm16_8k(b: bytes) -> bytes:
    """Convert Twilio mulaw to PCM16"""
    return audioop.ulaw2lin(b, 2)

def upsample_8k_to_24k(pcm16_8k: bytes) -> bytes:
    """Upsample 8kHz to 24kHz (3x)"""
    arr = np.frombuffer(pcm16_8k, dtype=np.int16)
    arr3 = np.repeat(arr, 3)
    return arr3.tobytes()

def downsample_24k_to_8k(pcm16_24k: bytes) -> bytes:
    """Downsample 24kHz to 8kHz (1/3)"""
    arr = np.frombuffer(pcm16_24k, dtype=np.int16)
    arr8k = arr[::3]
    return arr8k.tobytes()

def pcm16_8k_to_pcmu8k(pcm16_8k: bytes) -> bytes:
    """Convert PCM16 to Twilio mulaw"""
    return audioop.lin2ulaw(pcm16_8k, 2)

class OAIRealtime:
    """OpenAI Realtime API WebSocket client"""
    
    def __init__(self, system_instructions: str, on_audio_delta, on_text_delta, thread_id: Optional[str] = None, user_id: Optional[str] = None, call_sid: Optional[str] = None, voice: str = "alloy"):
        self.ws = None
        self.system_instructions = system_instructions
        self.on_audio_delta = on_audio_delta
        self.on_text_delta = on_text_delta
        self.voice = voice  # OpenAI voice (alloy, echo, shimmer)
        self.thread_id = thread_id
        self.user_id = user_id
        self.call_sid = call_sid  # For transfer functionality
        self._connected = threading.Event()
        self.audio_buffer_size = 0  # Track buffered audio bytes (24kHz PCM16)
    
    def _on_open(self, ws):
        """Configure session when WebSocket opens"""
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.system_instructions,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600
                },
                "temperature": 0.7,
                "voice": self.voice,  # Dynamic voice from admin panel
                "tools": [
                    {
                        "type": "function",
                        "name": "get_current_time",
                        "description": "Get the current time in Pacific Time Zone (PT). Use this when someone asks what time it is.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "format": {
                                    "type": "string",
                                    "description": "Time format to return",
                                    "enum": ["12-hour", "24-hour"]
                                }
                            },
                            "required": []
                        }
                    }
                ],
                "tool_choice": "auto"
            }
        }
        logger.info(f"🔊 VOICE DEBUG: Sending session.update with voice='{self.voice}'")
        logger.info(f"🔊 VOICE DEBUG: Full session config: {json.dumps(session_update['session'], indent=2)}")
        ws.send(json.dumps(session_update))
        logger.info(f"✅ OpenAI Realtime session configured with voice: {self.voice} and time tool")
        
        # =====================================================
        # 🧠 SEND PREVIOUS CONVERSATION HISTORY TO OPENAI
        # =====================================================
        # Load and send thread history so AI remembers previous calls
        if self.thread_id and THREAD_HISTORY.get(self.thread_id):
            history = list(THREAD_HISTORY[self.thread_id])
            # Send last 20 messages (10 exchanges) to avoid overwhelming the context
            recent_history = history[-20:] if len(history) > 20 else history
            
            logger.info(f"🧠 Sending {len(recent_history)} previous messages to OpenAI for context")
            
            for role, content in recent_history:
                # Create conversation item for each previous message
                conversation_item = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": role,  # "user" or "assistant"
                        "content": [
                            {
                                "type": "input_text",
                                "text": content
                            }
                        ]
                    }
                }
                ws.send(json.dumps(conversation_item))
            
            logger.info(f"✅ Loaded {len(recent_history)} previous messages into AI context")
        else:
            logger.info("🧠 No previous conversation history found - starting fresh")
        
        # Trigger immediate greeting - tell AI to start speaking first
        # Get the appropriate greeting from session instructions
        greeting_instruction = "Start the call by speaking first. Say your greeting exactly as specified in your GREETING GUIDANCE section. Speak in English."
        
        response_create = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": greeting_instruction
            }
        }
        ws.send(json.dumps(response_create))
        logger.info(f"📞 Triggered AI greeting: {greeting_instruction}")
        
        self._connected.set()
    
    def _on_message(self, ws, msg):
        """Handle incoming messages from OpenAI"""
        try:
            ev = json.loads(msg)
        except Exception:
            return
        
        event_type = ev.get("type")
        
        # Log ALL events for debugging
        logger.info(f"🔔 OpenAI event: {event_type}")
        
        if event_type == "response.audio.delta":
            b64 = ev.get("delta", "")
            if b64:
                pcm24 = base64.b64decode(b64)
                logger.info(f"🔊 Received audio delta: {len(pcm24)} bytes")
                self.on_audio_delta(pcm24)
        
        elif event_type == "response.text.delta":
            delta = ev.get("delta", "")
            if delta:
                self.on_text_delta(delta)
        
        elif event_type == "response.text.done":
            # Text response complete (not used in audio mode)
            text = ev.get("text", "")
            if text:
                logger.info(f"📝 OpenAI text response: {text[:100]}...")
        
        elif event_type == "session.created":
            logger.info(f"✅ OpenAI session created: {ev.get('session', {}).get('id')}")
        
        elif event_type == "session.updated":
            session_data = ev.get('session', {})
            voice = session_data.get('voice', 'UNKNOWN')
            logger.info(f"🔊 VOICE DEBUG: OpenAI confirmed session.updated with voice='{voice}'")
            logger.info(f"🔊 VOICE DEBUG: Full session response: {json.dumps(session_data, indent=2)}")
        
        elif event_type == "input_audio_buffer.speech_started":
            logger.info("🎤 User started speaking")
        
        elif event_type == "input_audio_buffer.speech_stopped":
            logger.info("🎤 User stopped speaking")
            self.audio_buffer_size = 0  # Reset buffer after speech
        
        elif event_type == "conversation.item.created":
            # Capture user or assistant messages
            item = ev.get("item", {})
            role = item.get("role")
            if role in ("user", "assistant"):
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "input_text":
                        text = content.get("text", "")
                        logger.info(f"💬 User said: {text}")
                        # Store in thread history
                        if hasattr(self, 'thread_id') and self.thread_id:
                            THREAD_HISTORY[self.thread_id].append(("user", text))
                    elif content.get("type") == "text":
                        text = content.get("text", "")
                        logger.info(f"🤖 Assistant said: {text}")
                        if hasattr(self, 'thread_id') and self.thread_id:
                            THREAD_HISTORY[self.thread_id].append(("assistant", text))
        
        elif event_type == "response.audio_transcript.done":
            # Capture assistant's spoken response transcript
            transcript = ev.get("transcript", "")
            if transcript:
                logger.info(f"🗣️ Assistant transcript: {transcript}")
                if hasattr(self, 'thread_id') and self.thread_id:
                    THREAD_HISTORY[self.thread_id].append(("assistant", transcript))
                
                # ❌ REMOVED: Don't check transfers on assistant responses - only check user input!
        
        elif event_type == "conversation.item.input_audio_transcription.completed":
            # Capture user's spoken input transcript
            transcript = ev.get("transcript", "")
            if transcript:
                logger.info(f"🎤 User transcript: {transcript}")
                if hasattr(self, 'thread_id') and self.thread_id:
                    THREAD_HISTORY[self.thread_id].append(("user", transcript))
                
                # ✅ Check for transfer intent ONLY on user input, not AI responses
                if hasattr(self, 'call_sid') and self.call_sid:
                    check_and_execute_transfer(transcript, self.call_sid)
        
        elif event_type == "response.output_item.done":
            # Check if this is a function call
            item = ev.get("item", {})
            if item.get("type") == "function_call":
                function_name = item.get("name")
                call_id = item.get("call_id")
                arguments_str = item.get("arguments", "{}")
                
                logger.info(f"🔧 Function call requested: {function_name} with args: {arguments_str}")
                
                # Execute the time tool
                if function_name == "get_current_time":
                    try:
                        from datetime import datetime
                        from zoneinfo import ZoneInfo
                        
                        # Parse arguments
                        args = json.loads(arguments_str) if arguments_str else {}
                        time_format = args.get("format", "12-hour")
                        
                        # Get current Pacific time
                        pacific_tz = ZoneInfo("America/Los_Angeles")
                        now = datetime.now(pacific_tz)
                        
                        # Format the time casually
                        if time_format == "24-hour":
                            time_str = now.strftime("%H:%M")
                        else:
                            time_str = now.strftime("%-I:%M%p").lower()  # e.g., "4:11pm"
                        
                        # Simple, casual result
                        result = f"{time_str} Pacific time"
                        
                        logger.info(f"⏰ Returning time: {result}")
                        
                        # Send function result back to OpenAI
                        ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": result
                            }
                        }))
                        
                        # Trigger AI to respond with the result
                        ws.send(json.dumps({"type": "response.create"}))
                        
                    except Exception as e:
                        logger.error(f"Error executing get_current_time: {e}")
                        # Send error back
                        ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": f"Error getting time: {str(e)}"
                            }
                        }))
        
        elif event_type == "response.done":
            logger.info("✅ OpenAI response complete")
            self.audio_buffer_size = 0  # Reset buffer after response
            
            # Save thread history to database after each response
            if hasattr(self, 'thread_id') and self.thread_id and hasattr(self, 'user_id') and self.user_id:
                try:
                    mem_store = HTTPMemoryStore()
                    save_thread_history(self.thread_id, mem_store, self.user_id)
                    
                    # ✅ Extract and save structured facts from recent conversation
                    # Get last user message from thread history for memory extraction
                    try:
                        history = THREAD_HISTORY.get(self.thread_id, [])
                        if history:
                            # Check last 5 messages for important information
                            recent_messages = list(history)[-5:]
                            for role, content in recent_messages:
                                if role == "user":
                                    try:
                                        if should_remember(content):
                                            logger.info(f"🧠 Extracting memories from: {content[:100]}...")
                                            items = extract_carry_kit_items(content)
                                            for item in items:
                                                try:
                                                    memory_id = mem_store.write(
                                                        memory_type=item["type"],
                                                        key=item["key"],
                                                        value=item["value"],
                                                        user_id=self.user_id,
                                                        scope="user",
                                                        ttl_days=item.get("ttl_days", 365)
                                                    )
                                                    logger.info(f"💾 Saved structured memory: {item['type']}:{item['key']} -> {memory_id}")
                                                except Exception as e:
                                                    logger.error(f"Failed to save structured memory: {e}")
                                    except Exception as e:
                                        logger.error(f"Memory extraction error: {e}")
                    except Exception as e:
                        logger.error(f"Memory processing error: {e}")
                except Exception as e:
                    logger.warning(f"Failed to save thread history: {e}")
        
        elif event_type == "error":
            error_msg = ev.get("error", {}).get("message", "Unknown error")
            logger.error(f"❌ OpenAI error: {error_msg}")
    
    def _on_error(self, ws, err):
        logger.error(f"OpenAI WebSocket error: {err}")
    
    def _on_close(self, ws, *args):
        """Handle WebSocket close (compatible with any websocket-client version)"""
        if len(args) >= 2:
            logger.info(f"OpenAI WebSocket closed: code={args[0]}, reason={args[1]}")
        elif len(args) == 1:
            logger.info(f"OpenAI WebSocket closed: {args[0]}")
        else:
            logger.info("OpenAI WebSocket closed")
    
    def connect(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        openai_key = get_secret("OPENAI_API_KEY")
        model = get_setting("realtime_model", "gpt-realtime")
        realtime_url = f"wss://api.openai.com/v1/realtime?model={model}"
        
        headers = [
            f"Authorization: Bearer {openai_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        
        self.ws = WebSocketApp(
            realtime_url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        threading.Thread(target=self.ws.run_forever, daemon=True).start()
        self._connected.wait(timeout=5)
    
    def send_pcm16_24k(self, chunk: bytes):
        """Send audio chunk to OpenAI"""
        if not self.ws:
            return
        ev = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(chunk).decode("ascii")
        }
        self.ws.send(json.dumps(ev))
        self.audio_buffer_size += len(chunk)
    
    def commit_and_respond(self):
        """Commit audio buffer and request response (only if >= 100ms buffered)"""
        if not self.ws:
            return
        
        # 100ms at 24kHz PCM16 = 24000 samples/sec * 0.1 sec * 2 bytes = 4800 bytes
        MIN_BUFFER_SIZE = 4800
        
        if self.audio_buffer_size >= MIN_BUFFER_SIZE:
            self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            self.ws.send(json.dumps({"type": "response.create"}))
            self.audio_buffer_size = 0  # Reset after commit
        else:
            logger.debug(f"⏸️ Skipping commit - buffer too small ({self.audio_buffer_size} < {MIN_BUFFER_SIZE} bytes)")
    
    def close(self):
        """Close the WebSocket connection"""
        if self.ws:
            self.ws.close()

@app.websocket("/phone/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """Twilio Media Streams WebSocket endpoint"""
    await websocket.accept()
    logger.info("🌐 Twilio Media Stream connected")
    
    # Capture the event loop for use in threaded callbacks
    event_loop = asyncio.get_event_loop()
    
    stream_sid = None
    call_sid = None  # Track call_sid for transfer functionality
    user_id = None  # Track user_id for transcript retrieval
    thread_id = None  # Track thread_id for memory continuity
    oai = None
    last_media_ts = time.time()
    
    def on_oai_audio(pcm24):
        """Handle audio from OpenAI - send to Twilio"""
        logger.info(f"📤 Sending audio to Twilio: {len(pcm24)} bytes PCM24 -> mulaw")
        pcm8 = downsample_24k_to_8k(pcm24)
        mulaw = pcm16_8k_to_pcmu8k(pcm8)
        payload = base64.b64encode(mulaw).decode("ascii")
        
        if websocket.application_state == WebSocketState.CONNECTED:
            # Schedule coroutine in the FastAPI event loop from this thread
            asyncio.run_coroutine_threadsafe(
                websocket.send_text(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })),
                event_loop
            )
            logger.info(f"✅ Audio sent to Twilio ({len(payload)} base64 chars)")
        else:
            logger.warning("⚠️ WebSocket not connected, skipping audio send")
    
    def on_oai_text(delta):
        """Handle text transcript from OpenAI"""
        logger.info(f"📝 OpenAI: {delta}")
    
    def on_tts_needed(text):
        """Generate ElevenLabs audio and stream to Twilio"""
        try:
            logger.info(f"🎙️ Generating ElevenLabs TTS for: {text[:100]}...")
            
            # Get voice_id from admin panel (using sync wrapper for non-async callback)
            voice_id = get_admin_setting_sync("voice_id", "FGY2WhTYpPnrIDTdsKH5")
            logger.info(f"🔊 Using ElevenLabs voice_id: {voice_id}")
            
            # Import ElevenLabs client
            from elevenlabs.client import ElevenLabs
            from elevenlabs import VoiceSettings
            
            client = ElevenLabs(api_key=get_secret("ELEVENLABS_API_KEY"))
            
            # Stream audio from ElevenLabs
            audio_stream = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_turbo_v2_5",  # Fast model for real-time
                output_format="pcm_24000"  # 24kHz PCM16 to match OpenAI
            )
            
            # Stream to Twilio
            for chunk in audio_stream:
                if chunk:
                    # Chunk is already 24kHz PCM16 from ElevenLabs
                    pcm8 = downsample_24k_to_8k(chunk)
                    mulaw = pcm16_8k_to_pcmu8k(pcm8)
                    payload = base64.b64encode(mulaw).decode("ascii")
                    
                    if websocket.application_state == WebSocketState.CONNECTED:
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload}
                            })),
                            event_loop
                        )
            
            logger.info("✅ ElevenLabs audio streaming complete")
            
        except Exception as e:
            logger.error(f"❌ ElevenLabs TTS failed: {e}")
    
    try:
        while True:
            msg = await websocket.receive_text()
            ev = json.loads(msg)
            event_type = ev.get("event")
            
            if event_type == "start":
                stream_sid = ev["start"]["streamSid"]
                custom_params = ev["start"].get("customParameters", {})
                user_id = custom_params.get("user_id")
                call_sid = custom_params.get("call_sid")
                is_callback = custom_params.get("is_callback") == "True"
                
                # SECURITY: Retrieve customer context server-side using call_sid (prevents spoofing)
                customer_id = None
                agent_name_override = None
                greeting_override = None
                voice_override = None
                customer_sliders = None
                
                if call_sid:
                    try:
                        import requests
                        # Call Flask API to get customer context (server-side lookup)
                        # SECURITY: Include shared secret for authentication
                        internal_secret = get_secret("SESSION_SECRET")
                        response = requests.get(
                            f"http://127.0.0.1:5000/api/internal/customer-context/{call_sid}",
                            headers={"X-Internal-Secret": internal_secret},
                            timeout=2
                        )
                        
                        if response.status_code == 200:
                            customer_data = response.json()
                            customer_id = customer_data.get('customer_id')
                            agent_name_override = customer_data.get('agent_name')
                            greeting_override = customer_data.get('greeting_template')
                            voice_override = customer_data.get('openai_voice')
                            customer_sliders = customer_data.get('personality_sliders')
                            
                            logger.info(f"✅ Retrieved customer context: customer_id={customer_id}, agent={agent_name_override}")
                        else:
                            logger.warning(f"⚠️ No customer context found for call_sid={call_sid}")
                    except Exception as e:
                        logger.error(f"❌ Failed to retrieve customer context: {e}")
                
                # ✅ Create stable thread_id with customer namespace for multi-tenancy
                if customer_id:
                    thread_id = f"customer_{customer_id}_user_{user_id}" if user_id else f"customer_{customer_id}"
                    logger.info(f"🏢 Multi-tenant mode: Customer {customer_id}")
                else:
                    thread_id = f"user_{user_id}" if user_id else None
                    logger.info(f"📞 Default mode: No customer context, using admin settings")
                
                logger.info(f"📞 Stream started: {stream_sid}, User: {user_id}, Call: {call_sid}, Thread: {thread_id}, Callback: {is_callback}")
                
                # Initialize admin settings with defaults (will be fetched in parallel inside try block)
                agent_name_val = "AI Assistant"
                existing_greeting_val = "Hi, this is {agent_name}. Is this {user_name}?"
                new_greeting_val = "{time_greeting}! This is {agent_name}. How can I help you?"
                transfer_rules_val = "[]"
                voice_val = "alloy"
                
                # ⚡ ULTRA-OPTIMIZED: Fetch EVERYTHING in parallel, then build greeting with full context
                try:
                    mem_store = HTTPMemoryStore()
                    from app.prompt_templates import build_complete_prompt
                    
                    # ⚡ PARALLEL FETCH: Admin settings + Thread history + Memory V2 Profile ALL AT ONCE
                    logger.info("⚡ Fetching admin settings, Memory V2 profile, and history in parallel...")
                    
                    async def fetch_caller_profile():
                        """🚀 FAST: Try Memory V2 enriched context first (<1 second!), fall back to V1"""
                        if user_id:
                            # 🚀 Try Memory V2 FAST enriched context (pre-formatted, ready for LLM)
                            v2_context = await asyncio.to_thread(mem_store.get_enriched_context_v2, user_id)
                            if v2_context:
                                logger.info(f"⚡ Using Memory V2 FAST enriched context (<1 second retrieval!)")
                                return {"version": "v2", "context": v2_context, "pre_formatted": True}
                            
                            # Fall back to V1 (slower, raw memories)
                            logger.info(f"⚠️ Memory V2 not available, falling back to V1 raw memories (2-3 seconds)")
                            memories_v1 = await asyncio.to_thread(mem_store.get_user_memories, user_id, limit=500, include_shared=True)
                            return {"version": "v1", "memories": memories_v1, "pre_formatted": False}
                        return {"version": "none", "memories": [], "pre_formatted": False}
                    
                    async def fetch_thread_history():
                        if thread_id and user_id:
                            await asyncio.to_thread(load_thread_history, thread_id, mem_store, user_id)
                            return len(THREAD_HISTORY.get(thread_id, []))
                        return 0
                    
                    # Fetch EVERYTHING in parallel
                    (
                        agent_name_val,
                        existing_greeting_val,
                        new_greeting_val,
                        transfer_rules_val,
                        voice_val,
                        prompt_block_results,
                        caller_data,
                        history_count
                    ) = await asyncio.gather(
                        get_admin_setting("agent_name", "AI Assistant"),
                        get_admin_setting("existing_user_greeting", "Hi, this is {agent_name}. Is this {user_name}?"),
                        get_admin_setting("new_caller_greeting", "{time_greeting}! This is {agent_name}. How can I help you?"),
                        get_admin_setting("transfer_rules", "[]"),
                        get_admin_setting("openai_voice", "alloy"),
                        asyncio.to_thread(mem_store.search, "prompt_blocks", user_id="admin", k=5),
                        fetch_caller_profile(),
                        fetch_thread_history()
                    )
                    
                    memory_version = caller_data.get("version", "none")
                    logger.info(f"✅ Parallel fetch complete: agent={agent_name_val}, voice={voice_val}, memory_version={memory_version}, history={history_count}")
                    
                    # Extract prompt blocks
                    selected_blocks = {}
                    for result in prompt_block_results:
                        if result.get("key") == "prompt_blocks" or result.get("setting_key") == "prompt_blocks":
                            value = result.get("value", {})
                            # Parse JSON string if needed
                            if isinstance(value, str):
                                try:
                                    value = json.loads(value)
                                except json.JSONDecodeError:
                                    logger.warning(f"⚠️ Failed to parse prompt_blocks JSON string")
                                    continue
                            stored_blocks = value.get("value") or value.get("setting_value") or value.get("blocks")
                            if stored_blocks:
                                selected_blocks = stored_blocks
                                logger.info(f"✅ Using prompt blocks: {list(selected_blocks.keys())}")
                                break
                    
                    # Initialize variables for all code paths
                    normalized = {}
                    user_name = None
                    v2_pre_formatted_context = None
                    
                    # Process caller data based on version
                    if memory_version == "v2":
                        # ⚡ MEMORY V2 FAST: Pre-formatted context string ready for LLM!
                        v2_pre_formatted_context = caller_data.get("context", "")
                        # Extract user name for greeting (if available in context)
                        # For now, we'll leave user_name as None and let greeting be generic
                        logger.info(f"⚡ Memory V2 FAST context loaded ({len(v2_pre_formatted_context)} chars) - 10x faster!")
                        
                    elif memory_version == "v1":
                        # ⚠️ MEMORY V1: Raw memories (slower normalization)
                        memories = caller_data.get("memories", [])
                        if memories:
                            normalized = await asyncio.to_thread(mem_store.normalize_memories, memories)
                            user_name = normalized.get("identity", {}).get("caller_name")  # Extract from normalized V1 data
                            logger.info(f"⚠️ Normalized {len(memories)} V1 memories, extracted name: {user_name}")
                        else:
                            # 🆕 AUTO-REGISTER NEW CALLERS (only for V1 empty case)
                            if user_id:
                                logger.info(f"🆕 New caller detected! No existing memories for {user_id}")
                                try:
                                    registered = await asyncio.to_thread(mem_store.auto_register_caller, user_id, user_id)
                                    if registered:
                                        logger.info(f"✅ Auto-registered new caller: {user_id}")
                                    else:
                                        logger.warning(f"⚠️ Failed to auto-register caller: {user_id}")
                                except Exception as e:
                                    logger.error(f"❌ Error auto-registering caller {user_id}: {e}")
                    
                    else:
                        # No memories at all - new caller (normalized and user_name remain empty/None)
                        logger.info(f"🆕 New caller, no memory system data available")
                    
                    # Build instructions with full context
                    agent_name = agent_name_override or agent_name_val
                    
                    if selected_blocks:
                        instructions = build_complete_prompt(selected_blocks, agent_name)
                        logger.info(f"✅ Built system prompt from {len(selected_blocks)} admin panel blocks")
                    else:
                        system_prompt_path = "app/prompts/system_sam.txt"
                        try:
                            with open(system_prompt_path, "r") as f:
                                instructions = f.read()
                            logger.info(f"⚠️ No admin panel blocks, using file: {system_prompt_path}")
                        except FileNotFoundError:
                            instructions = f"You are {agent_name}, a helpful assistant. Be friendly, casual, and conversational."
                    
                    # Add conversation history
                    if thread_id and THREAD_HISTORY.get(thread_id):
                        history = list(THREAD_HISTORY[thread_id])
                        if history:
                            instructions += f"\n\n=== CONVERSATION HISTORY ===\nThis is a continuing conversation. Previous messages:\n"
                            for role, content in history[-10:]:
                                instructions += f"{role}: {content[:200]}...\n" if len(content) > 200 else f"{role}: {content}\n"
                            logger.info(f"✅ Added {min(10, len(history))} history messages")
                    
                    # Add memory context (format depends on V1 vs V2)
                    if memory_version == "v2" and v2_pre_formatted_context:
                        # ⚡ V2 FAST: Pre-formatted context string ready to inject!
                        instructions += "\n\n" + v2_pre_formatted_context + "\n"
                        logger.info(f"⚡ Injected V2 FAST pre-formatted context ({len(v2_pre_formatted_context)} chars)")
                    elif normalized:
                        # ⚠️ V1: Normalized structure (slower)
                        instructions += "\n\n=== YOUR_MEMORY_OF_THIS_CALLER ===\n"
                        instructions += json.dumps(normalized, indent=2)
                        facts_count = len(normalized.get('facts', []))
                        vehicles_count = len(normalized.get('vehicles', []))
                        logger.info(f"⚠️ Injected V1 normalized memories: {facts_count} facts, {vehicles_count} vehicles")
                        instructions += "\n\nIMPORTANT: Use this memory naturally in conversation.\n"
                        instructions += "=== END_MEMORY ===\n"
                    
                    # Build personalized greeting
                    if is_callback and user_name:
                        # Returning caller with name
                        greeting_template = greeting_override or existing_greeting_val
                        greeting = greeting_template.replace("{user_name}", user_name).replace("{agent_name}", agent_name)
                        instructions += f"\n\n=== GREETING - START SPEAKING FIRST! ===\nThis is a returning caller named {user_name}. START the call by speaking first. Say this exact greeting: '{greeting}' Then continue naturally."
                        logger.info(f"✅ Built personalized greeting for {user_name}")
                    elif is_callback:
                        # Returning caller without name
                        greeting_template = greeting_override or existing_greeting_val
                        greeting = greeting_template.replace("{user_name}", "").replace("{agent_name}", agent_name)
                        instructions += f"\n\n=== GREETING - START SPEAKING FIRST! ===\nThis is a returning caller. START the call by speaking first. Say this greeting: '{greeting}' Then continue naturally."
                        logger.info(f"✅ Built generic returning caller greeting")
                    else:
                        # New caller
                        import datetime
                        hour = datetime.datetime.now().hour
                        if hour < 12:
                            time_greeting = "Good morning"
                        elif hour < 18:
                            time_greeting = "Good afternoon"
                        else:
                            time_greeting = "Good evening"
                        
                        greeting_template = greeting_override or new_greeting_val
                        greeting = greeting_template.replace("{time_greeting}", time_greeting).replace("{agent_name}", agent_name)
                        instructions += f"\n\n=== GREETING - START SPEAKING FIRST! ===\nThis is a new caller. START the call by speaking first. Say this exact greeting: '{greeting}' Then continue naturally."
                        logger.info(f"✅ Built new caller greeting")
                    
                    # Inject transfer rules
                    try:
                        rules_json = transfer_rules_val
                        transfer_rules = json.loads(rules_json) if isinstance(rules_json, str) else rules_json if isinstance(rules_json, list) else []
                        if transfer_rules:
                            instructions += "\n\n=== CRITICAL: CALL TRANSFER CAPABILITIES ===\n"
                            instructions += "IMPORTANT: You HAVE FULL TRANSFER CAPABILITIES. NEVER say you cannot transfer calls.\n\n"
                            instructions += "The system automatically detects transfer requests and handles routing.\n\n"
                            instructions += "WHEN A CALLER ASKS FOR A TRANSFER:\n"
                            instructions += "1. Immediately acknowledge: 'Of course' or 'Sure, let me connect you'\n"
                            instructions += "2. Say: 'One moment, transferring you now' or 'Let me transfer you'\n"
                            instructions += "3. Be confident and brief - the system handles the technical routing\n"
                            instructions += "4. NEVER say 'I cannot transfer' or 'I'm unable to transfer'\n\n"
                            instructions += "You are fully equipped to handle transfers. Be confident!\n"
                            logger.info(f"✅ Injected transfer capabilities ({len(transfer_rules)} rules)")
                    except Exception as e:
                        logger.error(f"❌ Failed to inject transfer rules: {e}")
                    
                    # Connect to OpenAI with full context
                    openai_voice = voice_override or voice_val
                    logger.info(f"🎤 Connecting to OpenAI with full memory context...")
                    
                    oai = OAIRealtime(
                        instructions, 
                        on_oai_audio, 
                        on_oai_text, 
                        thread_id=thread_id, 
                        user_id=user_id,
                        call_sid=call_sid,
                        voice=openai_voice
                    )
                    oai.connect()
                    memory_info = f"v2_profile" if memory_version == "v2" else f"{len(caller_data.get('memories', []))} v1_memories"
                    logger.info(f"✅ Greeting sent with full context! (thread={thread_id}, memory={memory_info}, history={history_count})")
                
                except Exception as e:
                    logger.error(f"Failed to initialize call: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    instructions = "You are Barbara - the funniest person in insurance. Crack jokes, keep it casual, make insurance fun."
            
            elif event_type == "media":
                # Audio from Twilio (mulaw 8kHz base64)
                b64 = ev["media"]["payload"]
                mulaw = base64.b64decode(b64)
                pcm16_8k = pcmu8k_to_pcm16_8k(mulaw)
                pcm16_24k = upsample_8k_to_24k(pcm16_8k)
                
                if oai:
                    oai.send_pcm16_24k(pcm16_24k)
                last_media_ts = time.time()
            
            elif event_type == "mark":
                # Mark event - commit audio buffer
                if oai:
                    oai.commit_and_respond()
            
            elif event_type == "stop":
                logger.info(f"📞 Stream stopped: {stream_sid}")
                break
            
            # Auto-commit on pause (rudimentary VAD assist)
            if (time.time() - last_media_ts) > 0.7 and oai:
                oai.commit_and_respond()
                last_media_ts = time.time()
    
    except WebSocketDisconnect:
        logger.info("Twilio disconnected")
    except Exception as e:
        logger.exception(f"Media stream error: {e}")
    finally:
        if oai:
            oai.close()
        
        # =====================================================
        # 📨 SAVE TRANSCRIPT & SEND CALL SUMMARY
        # =====================================================
        if call_sid and user_id:
            try:
                import requests
                from datetime import datetime
                
                # Extract full conversation from AI-Memory (authoritative source)
                # Thread history is stored with key = thread_history:{thread_id}
                # Use the SAME thread_id that was used during the call
                logger.info(f"🔍 Retrieving transcript from AI-Memory for call {call_sid}, thread_id={thread_id}...")
                
                # Initialize messages for V2 summarization (populated in try or except)
                messages = []
                
                try:
                    memory_response = requests.post(
                        "http://209.38.143.71:8100/memory/retrieve",
                        headers={"Content-Type": "application/json"},
                        json={
                            "user_id": user_id,
                            "message": f"thread_history:{thread_id}",  # Use actual thread_id
                            "limit": 500,
                            "types": ["thread_recap"]  # Correct type
                        },
                        timeout=3.0  # 3 second timeout for AI-Memory
                    )
                    
                    if memory_response.status_code == 200:
                        memory_data = memory_response.json()
                        memory_content = memory_data.get("memory", "")
                        
                        if memory_content:
                            # Parse newline-delimited JSON (AI-Memory returns this format)
                            messages = []
                            for line in memory_content.strip().split('\n'):
                                line = line.strip()
                                if line:
                                    try:
                                        memory_json = json.loads(line)
                                        # Each line should be a thread_history object with messages array
                                        if "messages" in memory_json:
                                            messages = memory_json.get("messages", [])
                                            break  # Found the thread history
                                    except json.JSONDecodeError as e:
                                        logger.warning(f"⚠️ Failed to parse memory line: {e}")
                                        continue
                            
                            if messages:
                                logger.info(f"✅ Retrieved {len(messages)} messages from AI-Memory")
                                
                                # Build formatted transcript from AI-Memory
                                transcript_lines = [
                                    f"Call SID: {call_sid}",
                                    f"Phone Number: +1{user_id}",
                                    f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                                    "=" * 80,
                                    ""
                                ]
                                
                                for msg in messages:
                                    role = msg.get("role", "unknown")
                                    content = msg.get("content", "")
                                    
                                    if role == "assistant":
                                        transcript_lines.append(f"AI: {content}")
                                    elif role == "user":
                                        transcript_lines.append(f"CALLER: {content}")
                                    else:
                                        transcript_lines.append(f"{role.upper()}: {content}")
                                    transcript_lines.append("")
                                
                                summary_text = "\n".join(transcript_lines)
                                logger.info(f"✅ Formatted transcript from AI-Memory ({len(summary_text)} bytes)")
                            else:
                                logger.warning(f"⚠️ No messages in AI-Memory, using fallback")
                                raise ValueError("No messages in memory")
                        else:
                            logger.warning(f"⚠️ Empty memory content, using fallback")
                            raise ValueError("Empty memory content")
                    else:
                        logger.warning(f"⚠️ AI-Memory returned {memory_response.status_code}, using fallback")
                        raise ValueError(f"AI-Memory error: {memory_response.status_code}")
                
                except Exception as e:
                    # Fallback: use local THREAD_HISTORY if AI-Memory fails
                    logger.warning(f"⚠️ AI-Memory retrieval failed ({e}), using local THREAD_HISTORY")
                    history = THREAD_HISTORY.get(thread_id, deque()) if thread_id else deque()
                    
                    # Build messages for V2 from local history
                    messages = [{"role": role, "content": content} for role, content in history]
                    
                    transcript_lines = []
                    for role, content in history:
                        transcript_lines.append(f"{role.upper()}: {content}")
                    
                    summary_text = "\n".join(transcript_lines) if transcript_lines else "No conversation recorded."
                
                # Format phone number for display
                from_number = f"+1{user_id}" if len(user_id) == 10 else user_id
                
                # Save transcript to file (use container path /app/static/calls)
                calls_dir = "/app/static/calls"
                os.makedirs(calls_dir, exist_ok=True)
                
                transcript_path = os.path.join(calls_dir, f"{call_sid}.txt")
                with open(transcript_path, 'w') as f:
                    f.write(summary_text)
                logger.info(f"📝 Transcript saved: {transcript_path}")
                
                # ⚡ AUTO-SUMMARIZE CALL USING MEMORY V2
                try:
                    logger.info(f"⚡ Auto-summarizing call using Memory V2...")
                    # Convert messages to V2 format: [(role, content), ...]
                    if messages:
                        conversation_history = [(msg.get("role", "user"), msg.get("content", "")) for msg in messages]
                    else:
                        # Fallback to local thread history
                        conversation_history = list(THREAD_HISTORY.get(thread_id, [])) if thread_id else []
                    
                    if conversation_history:
                        mem_store = HTTPMemoryStore()
                        success = mem_store.save_call_summary_v2(
                            phone_number=user_id,
                            call_sid=call_sid,
                            conversation_history=conversation_history
                        )
                        if success:
                            logger.info(f"✅ Memory V2 call summarization complete!")
                        else:
                            logger.warning(f"⚠️ Memory V2 call summarization failed")
                    else:
                        logger.warning(f"⚠️ No conversation history to summarize")
                except Exception as e:
                    logger.error(f"❌ Error during V2 call summarization: {e}")
                
                # Update calls.json index with file locking to prevent race conditions
                import fcntl
                calls_index_path = os.path.join(calls_dir, "calls.json")
                calls_data = []
                
                # Acquire exclusive lock before reading/writing
                with open(calls_index_path, 'a+') as lock_file:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    try:
                        lock_file.seek(0)
                        content = lock_file.read()
                        if content:
                            calls_data = json.loads(content)
                    except:
                        calls_data = []
                    
                    calls_data.append({
                        "call_sid": call_sid,
                        "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "caller": from_number,
                        "summary": summary_text[:200] + "..." if len(summary_text) > 200 else summary_text,
                        "transcript_file": f"{call_sid}.txt",
                        "audio_file": f"{call_sid}.mp3"
                    })
                    
                    lock_file.seek(0)
                    lock_file.truncate()
                    lock_file.write(json.dumps(calls_data, indent=2))
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                
                logger.info(f"📒 Updated calls index: {calls_index_path}")
                
                # Send to send_text service for SMS notification
                # Truncate summary to 500 chars to avoid SMS 1600 char limit
                short_summary = summary_text[:500] + "..." if len(summary_text) > 500 else summary_text
                
                logger.info(f"📱 Preparing SMS for call {call_sid}")
                logger.info(f"📱 Phone number: {from_number}")
                logger.info(f"📱 Summary length: {len(summary_text)} chars (truncated to {len(short_summary)})")
                logger.info(f"📱 First 100 chars of summary: {short_summary[:100]}...")
                
                payload = {
                    "data": {
                        "metadata": {
                            "phone_call": {
                                "call_sid": call_sid,
                                "external_number": from_number
                            }
                        },
                        "analysis": {
                            "transcript_summary": short_summary
                        }
                    }
                }
                
                logger.info(f"📱 Payload call_sid: {payload['data']['metadata']['phone_call']['call_sid']}")
                logger.info(f"📱 Payload phone: {payload['data']['metadata']['phone_call']['external_number']}")
                
                # Send to send_text service (use Docker host gateway to reach host machine)
                response = requests.post(
                    "http://172.17.0.1:3000/call-summary",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=2
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ Call summary sent to send_text service: {call_sid}")
                    logger.info(f"✅ Response from send_text: {response.text[:200]}")
                else:
                    logger.warning(f"⚠️ Call summary POST failed: {response.status_code}, Response: {response.text[:200]}")
                
                # =====================================================
                # 📊 SEND TO NOTION FOR DASHBOARD TRACKING
                # =====================================================
                try:
                    from app.notion_client import NotionClient
                    
                    notion = NotionClient(base_url="http://172.17.0.1:8200")
                    
                    # Check if Notion service is available
                    if notion.health_check():
                        # Build URLs for transcript and audio
                        base_url = "https://voice.theinsurancedoctors.com/calls"
                        transcript_url = f"{base_url}/{call_sid}.txt"
                        audio_url = f"{base_url}/{call_sid}.mp3"
                        
                        # Create brief summary (first 200 chars) for Notion Summary column
                        # The full transcript goes in the Transcript column
                        brief_summary = summary_text[:200] + "..." if len(summary_text) > 200 else summary_text
                        
                        logger.info(f"📊 Logging call to Notion: {call_sid}")
                        logger.info(f"📊 Full transcript length: {len(summary_text)} chars")
                        logger.info(f"📊 Brief summary: {brief_summary[:100]}...")
                        
                        notion.log_call(
                            phone=from_number,
                            transcript=summary_text,  # Full conversation transcript
                            summary=brief_summary,  # Brief summary for quick view
                            transfer_to=None,  # TODO: Detect if call was transferred
                            call_sid=call_sid,
                            transcript_url=transcript_url,
                            audio_url=audio_url
                        )
                        
                        logger.info(f"✅ Call logged to Notion dashboard: {call_sid}")
                    else:
                        logger.warning(f"⚠️ Notion service not available, skipping Notion logging")
                        
                except Exception as notion_error:
                    logger.warning(f"⚠️ Failed to log to Notion (non-critical): {notion_error}")
            
            except Exception as e:
                logger.error(f"❌ Error saving transcript/sending summary: {str(e)}")
        
        logger.info("🔌 WebSocket closed")

# -----------------------------------------------------------------------------
# Entrypoint (dev)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(get_setting("port", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
