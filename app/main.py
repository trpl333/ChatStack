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
# Import get_admin_setting from main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from main import get_admin_setting
except ImportError:
    # Fallback if main.py not available
    def get_admin_setting(setting_key, default=None):
        return get_setting(setting_key, default)
from app.models import ChatRequest, ChatResponse, MemoryObject
from app.llm import chat as llm_chat, chat_realtime_stream, _get_llm_config, validate_llm_connection
from app.http_memory import HTTPMemoryStore
from app.packer import pack_prompt, should_remember, extract_carry_kit_items, detect_safety_triggers
from app.tools import tool_dispatcher, parse_tool_calls, execute_tool_calls
from app.notion_client import notion_client

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
            instructions += f"• Never mention being an AI - stay fully in character\n"
        else:
            instructions += f"• Minimize AI self-references\n"
    
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
    if THREAD_LOADED.get(thread_id):
        logger.info(f"⏭️ Thread {thread_id} already loaded, skipping")
        return  # Already loaded
    
    try:
        # Search for stored thread history with exact key match
        history_key = f"thread_history:{thread_id}"
        
        logger.info(f"🔍 Loading thread history: key={history_key}, user_id={user_id}")
        
        # Strategy: Search broadly (type filter doesn't work in ai-memory service)
        # Then filter client-side for exact key match
        results = mem_store.search(history_key, user_id=user_id, k=200)
        
        logger.info(f"🔍 Search returned {len(results)} results for key: {history_key}")
        
        # Filter for exact key match (case-insensitive for safety)
        matching_memory = None
        for result in results:
            result_key = result.get("key") or result.get("k") or ""
            # Check exact match OR if the value contains our thread history
            if result_key == history_key:
                matching_memory = result
                logger.info(f"✅ Found exact match for key: {history_key}")
                break
            # Fallback: check if value contains thread history data
            elif isinstance(result.get("value"), dict) and "messages" in result.get("value", {}):
                # This might be our thread history with a different key format
                logger.info(f"🔍 Found potential match with key={result_key}")
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
                THREAD_LOADED[thread_id] = True
                return
        
        logger.info(f"🧵 No stored history found for thread {thread_id} (searched {len(results)} results)")
        THREAD_LOADED[thread_id] = True
    except Exception as e:
        logger.error(f"❌ Failed to load thread history for {thread_id}: {e}", exc_info=True)
        THREAD_LOADED[thread_id] = True  # Mark as attempted to avoid retry loops

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
    """
    try:
        transcript_lower = transcript.lower()
        
        # Load transfer rules from admin settings
        rules_json = get_admin_setting("transfer_rules", "[]")
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
                
                # Flexible matching: require at least 1 important word (for 2-word phrases) or 50% for longer phrases
                min_matches = 1 if len(important_words) <= 2 else (len(important_words) + 1) // 2
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
                "turn_detection": {"type": "server_vad"},
                "temperature": 0.7,
                "voice": self.voice  # Dynamic voice from admin panel
            }
        }
        ws.send(json.dumps(session_update))
        logger.info(f"✅ OpenAI Realtime session configured with voice: {self.voice}")
        
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
            
            # Get voice_id from admin panel
            voice_id = get_admin_setting("voice_id", "FGY2WhTYpPnrIDTdsKH5")
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
                call_sid = custom_params.get("call_sid")  # Extract call_sid for transfer functionality
                is_callback = custom_params.get("is_callback") == "True"
                
                # ✅ Create stable thread_id for conversation continuity
                thread_id = f"user_{user_id}" if user_id else None
                
                logger.info(f"📞 Stream started: {stream_sid}, User: {user_id}, Call: {call_sid}, Thread: {thread_id}, Callback: {is_callback}")
                
                # Build system instructions with memory context
                try:
                    mem_store = HTTPMemoryStore()
                    
                    # ✅ CRITICAL: Load thread history from database for conversation continuity
                    if thread_id and user_id:
                        load_thread_history(thread_id, mem_store, user_id)
                        logger.info(f"🔄 Loaded thread history for {thread_id}: {len(THREAD_HISTORY.get(thread_id, []))} messages")
                    
                    # ✅ CRITICAL FIX: Use paginated get_user_memories to retrieve ALL user memories
                    if user_id:
                        memories = mem_store.get_user_memories(user_id, limit=2000, include_shared=True)
                        logger.info(f"🧠 Retrieved {len(memories)} memories for user {user_id}")
                        # DEBUG: Log first few memories
                        for i, mem in enumerate(memories[:5]):
                            mem_type = mem.get('type', 'unknown')
                            mem_key = mem.get('key') or mem.get('k', 'no-key')
                            logger.info(f"  Memory {i+1}: {mem_type}:{mem_key}")
                    else:
                        memories = []
                    
                    # Load base system prompt
                    system_prompt_path = "app/prompts/system_sam.txt"
                    try:
                        with open(system_prompt_path, "r") as f:
                            instructions = f.read()
                    except FileNotFoundError:
                        instructions = "You are Samantha for Peterson Family Insurance. Be concise, warm, and human."
                    
                    # Add identity, personality, and greeting context - use get_admin_setting to query ai-memory directly
                    agent_name = get_admin_setting("agent_name", "Betsy")
                    instructions += f"\n\n=== YOUR IDENTITY ===\nYour name is {agent_name} and you work for Peterson Family Insurance Agency, part of Farmers Insurance."
                    
                    # ✅ ADD PERSONALITY INSTRUCTIONS (with dynamic sliders)
                    base_personality = """

=== YOUR PERSONALITY & VOICE ===
Sound smooth, happy, and confident—friendly but not over-excited.
Be lightly playful and casual; show subtle warmth, even a bit flirty when appropriate.
Switch to professional seriousness if the caller's tone or topic demands it.
Keep responses short and natural. Allow brief pauses so callers can jump in.
Always refer naturally to Peterson Family Insurance Agency and Farmers Insurance when relevant.
"""
                    
                    # Get personality sliders and generate dynamic instructions
                    sliders = get_admin_setting("personality_sliders", {})
                    if sliders:
                        personality_instructions = generate_personality_instructions(sliders)
                        instructions += base_personality + personality_instructions
                    else:
                        instructions += base_personality
                    
                    # ✅ NORMALIZE MEMORIES FIRST (before greeting) to extract caller identity
                    normalized = {}
                    if memories:
                        normalized = mem_store.normalize_memories(memories)
                        logger.info(f"📝 Normalized {len(memories)} memories into structured format")
                        # DEBUG: Log what we got from normalization
                        caller_name_debug = normalized.get("identity", {}).get("caller_name")
                        logger.info(f"🔍 DEBUG: normalized identity = {normalized.get('identity', {})}")
                        logger.info(f"🔍 DEBUG: extracted caller_name = {caller_name_debug}")
                    
                    # Add conversation history context
                    if thread_id and THREAD_HISTORY.get(thread_id):
                        history = list(THREAD_HISTORY[thread_id])
                        if history:
                            instructions += f"\n\n=== CONVERSATION HISTORY ===\nThis is a continuing conversation. Previous messages:\n"
                            for role, content in history[-10:]:  # Last 5 turns
                                instructions += f"{role}: {content[:200]}...\n" if len(content) > 200 else f"{role}: {content}\n"
                    
                    # Add caller context - extract from normalized structure
                    if is_callback:
                        # ✅ Extract caller name from normalized identity structure
                        user_name = normalized.get("identity", {}).get("caller_name") if normalized else None
                        spouse_name = normalized.get("contacts", {}).get("spouse", {}).get("name") if normalized else None
                        
                        # ✅ FALLBACK: If normalization didn't find name, check raw memories
                        if not user_name and memories:
                            logger.warning("⚠️ Normalization didn't find caller_name, checking raw memories...")
                            import re
                            for mem in memories[:50]:  # Check first 50 memories
                                value = mem.get("value", {})
                                mem_key = mem.get("key", "")
                                
                                # Method 1: Check for structured name field
                                if isinstance(value, dict):
                                    if value.get("name") and ("phone" in mem_key.lower() or "registration" in mem.get("type", "").lower()):
                                        user_name = value.get("name")
                                        logger.info(f"✅ Found caller name in structured memory: {user_name}")
                                        break
                                    
                                    # Method 2: Extract from conversation summaries
                                    summary = value.get("summary", "") or value.get("user_message", "")
                                    if summary:
                                        # Pattern: "I'm [Name]" or "This is [Name]" or "It's [Name]"
                                        name_match = re.search(r"(?:I'm|I am|This is|It's)\s+([A-Z][a-z]+)", summary)
                                        if name_match:
                                            user_name = name_match.group(1)
                                            logger.info(f"✅ Extracted caller name from conversation: {user_name}")
                                            break
                        
                        # ✅ FALLBACK 2: Extract spouse name from memories if not in normalized data
                        if not spouse_name and memories:
                            import re
                            for mem in memories[:50]:
                                value = mem.get("value", {})
                                if isinstance(value, dict):
                                    summary = value.get("summary", "") or value.get("user_message", "")
                                    # Pattern: "wife's name is [Name]" or "my wife [Name]" or just "[Name]."
                                    spouse_match = re.search(r"(?:wife'?s? (?:name )?is |my wife )?([A-Z][a-z]+)(?:\.|,)", summary)
                                    if spouse_match and "wife" in summary.lower():
                                        spouse_name = spouse_match.group(1)
                                        logger.info(f"✅ Extracted spouse name from conversation: {spouse_name}")
                                        break
                        
                        logger.info(f"👤 Caller identity: user_name={user_name}, spouse={spouse_name}, is_callback={is_callback}")
                        
                        greeting_template = get_admin_setting("existing_user_greeting", 
                                                             f"Hi, this is {agent_name} from Peterson Family Insurance Agency. Is this {{user_name}}?")
                        logger.info(f"🎤 Admin greeting template: '{greeting_template}'")
                        
                        # Build caller identity context
                        identity_context = ""
                        if user_name:
                            greeting = greeting_template.replace("{user_name}", user_name).replace("{agent_name}", agent_name)
                            identity_context = f"This is a returning caller named {user_name}."
                            
                            # Add family context if available
                            if spouse_name:
                                identity_context += f" Their spouse is {spouse_name}."
                            
                            instructions += f"\n\n=== GREETING - START SPEAKING FIRST! ===\n{identity_context} START the call by speaking first. Say this exact greeting: '{greeting}' Then continue naturally."
                        else:
                            greeting = greeting_template.replace("{user_name}", "").replace("{agent_name}", agent_name)
                            instructions += f"\n\n=== GREETING - START SPEAKING FIRST! ===\nThis is a returning caller. START the call by speaking first. Say this greeting: '{greeting}' Then continue naturally."
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
                        
                        greeting_template = get_admin_setting("new_caller_greeting", 
                                                             f"{{time_greeting}}! This is {agent_name} from Peterson Family Insurance Agency. How can I help you?")
                        greeting = greeting_template.replace("{time_greeting}", time_greeting).replace("{agent_name}", agent_name)
                        instructions += f"\n\n=== GREETING - START SPEAKING FIRST! ===\nThis is a new caller. START the call by speaking first. Say this exact greeting: '{greeting}' Then continue naturally."
                    
                    # Inject normalized memory context (organized dict instead of raw entries)
                    if normalized:
                        # Format as structured memory for AI
                        instructions += "\n\n=== YOUR_MEMORY_OF_THIS_CALLER ===\n"
                        instructions += "Below is everything you know about this caller, organized by category:\n\n"
                        instructions += json.dumps(normalized, indent=2)
                        instructions += "\n\nIMPORTANT: Use this structured data naturally in conversation. "
                        instructions += "If you see a spouse name, use it. If you see a birthday, remember it. "
                        instructions += "Empty fields (null values) mean you haven't learned that info yet.\n"
                        instructions += "=== END_MEMORY ===\n"
                        
                        # Count actual populated data
                        filled_contacts = sum(1 for rel in ["spouse", "father", "mother"] 
                                            if normalized.get("contacts", {}).get(rel, {}).get("name"))
                        filled_contacts += len(normalized.get("contacts", {}).get("children", []))
                        
                        stats = {
                            "contacts": filled_contacts,
                            "vehicles": len(normalized.get("vehicles", [])),
                            "policies": len(normalized.get("policies", [])),
                            "facts": len(normalized.get("facts", [])),
                            "commitments": len(normalized.get("commitments", []))
                        }
                        
                        logger.info(f"📝 Injected comprehensive memory template from {len(memories)} raw entries:")
                        logger.info(f"   └─ Contacts: {stats['contacts']}, Vehicles: {stats['vehicles']}, Policies: {stats['policies']}, Facts: {stats['facts']}")
                        
                        # 🔍 DEBUG: Show what contacts were extracted
                        if stats['contacts'] > 0:
                            logger.info(f"   👥 Contacts found:")
                            for rel in ["spouse", "father", "mother"]:
                                contact = normalized.get("contacts", {}).get(rel, {})
                                if contact.get("name"):
                                    logger.info(f"      • {rel.title()}: {contact['name']}" + 
                                              (f" (birthday: {contact['birthday']})" if contact.get("birthday") else ""))
                            
                            for child in normalized.get("contacts", {}).get("children", []):
                                logger.info(f"      • {child.get('relationship', 'child').title()}: {child.get('name', 'unknown')}")
                
                except Exception as e:
                    logger.error(f"Failed to load memory context: {e}")
                    instructions = "You are Samantha for Peterson Family Insurance. Be concise, warm, and human."
                
                # ✅ INJECT CURRENT TRANSFER RULES DYNAMICALLY
                try:
                    rules_json = get_admin_setting("transfer_rules", "[]")
                    logger.info(f"🔧 Raw transfer_rules from admin: {rules_json}")
                    transfer_rules = json.loads(rules_json) if isinstance(rules_json, str) else rules_json if isinstance(rules_json, list) else []
                    logger.info(f"🔧 Parsed transfer_rules: {len(transfer_rules)} rules")
                    
                    if transfer_rules:
                        instructions += "\n\n=== CALL TRANSFER CAPABILITIES ===\n"
                        instructions += "You CAN transfer calls! When a caller needs to speak with someone or a department, you can help.\n\n"
                        instructions += "Available transfers (use these EXACT keywords/phrases):\n"
                        
                        for rule in transfer_rules:
                            keyword = rule.get("keyword", "")
                            description = rule.get("description", keyword)
                            if keyword and description:
                                # Show both keyword and description for clarity
                                instructions += f"• {description}: Use phrase '{keyword}' in your response to trigger transfer\n"
                        
                        instructions += "\nHOW TRANSFERS WORK:\n"
                        instructions += "1. When caller requests a transfer, acknowledge their request warmly\n"
                        instructions += "2. Use the EXACT keyword/phrase from above naturally in your response\n"
                        instructions += "3. The system automatically handles the transfer when it detects the keyword\n"
                        instructions += "4. Phrases work with variations: 'filing a claim' matches 'claims', 'file a claim', etc.\n\n"
                        instructions += "EXAMPLES:\n"
                        instructions += "• Caller: 'I need to file a claim' → You: 'I can help with filing a claim, let me transfer you'\n"
                        instructions += "• Caller: 'Connect me to billing' → You: 'Sure, I'll help with billing'\n"
                        instructions += "• Caller: 'Can I talk to Melissa?' → You: 'Of course, let me connect you to Milissa'\n"
                        logger.info(f"✅ Injected {len(transfer_rules)} transfer rules into system prompt")
                    else:
                        logger.warning(f"⚠️ No transfer rules to inject (got empty list or None)")
                except Exception as e:
                    logger.error(f"❌ Failed to inject transfer rules: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                
                # Get voice from admin panel (alloy, echo, shimmer)
                openai_voice = get_admin_setting("openai_voice", "alloy")
                logger.info(f"🎤 Using OpenAI voice from admin panel: {openai_voice}")
                
                # Connect to OpenAI with thread tracking
                oai = OAIRealtime(
                    instructions, 
                    on_oai_audio, 
                    on_oai_text, 
                    thread_id=thread_id, 
                    user_id=user_id,
                    call_sid=call_sid,  # Pass call_sid for transfer functionality
                    voice=openai_voice
                )
                oai.connect()
                logger.info(f"🔗 OpenAI client initialized with thread_id={thread_id}, user_id={user_id}")
            
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
        # Log call to Notion before closing
        if 'thread_id' in locals() and 'user_id' in locals() and thread_id and user_id:
            try:
                # Generate call summary from thread history
                history = THREAD_HISTORY.get(thread_id, [])
                if history:
                    # Build phone number from user_id
                    phone_number = f"+1{user_id}" if not user_id.startswith('+') else user_id
                    
                    # Build full transcript
                    transcript_lines = []
                    for role, text in history:
                        prefix = "Customer" if role == "user" else "Samantha"
                        transcript_lines.append(f"{prefix}: {text}")
                    
                    full_transcript = "\n".join(transcript_lines[-20:])  # Last 20 exchanges
                    
                    # Extract caller name and spouse from history or normalized memory
                    caller_name = 'user_name' in locals() and user_name or 'Unknown'
                    spouse = 'spouse_name' in locals() and spouse_name or None
                    
                    # Generate AI summary
                    summary = f"Call with {caller_name} - {len(history)} exchanges"
                    
                    # Extract transfer info if any
                    transfer_to = None
                    for role, text in reversed(list(history)[-5:]):
                        if "transfer" in text.lower() or "connect you to" in text.lower():
                            # Try to extract who they were transferred to
                            for keyword in ["John", "Milissa", "Colin", "billing", "claims"]:
                                if keyword.lower() in text.lower():
                                    transfer_to = keyword
                                    break
                            break
                    
                    # Update customer info in Notion
                    notion_client.upsert_customer(
                        phone=phone_number,
                        name=caller_name,
                        spouse=spouse
                    )
                    
                    # Log the call
                    notion_client.log_call(
                        phone=phone_number,
                        transcript=full_transcript,
                        summary=summary,
                        transfer_to=transfer_to
                    )
                    
                    logger.info(f"📝 Call logged to Notion for {phone_number}")
                    
            except Exception as e:
                logger.error(f"Failed to log call to Notion: {e}")
        
        if oai:
            oai.close()
        logger.info("🔌 WebSocket closed")

# -----------------------------------------------------------------------------
# Entrypoint (dev)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(get_setting("port", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
