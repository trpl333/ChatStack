import os
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load system prompts
def load_system_prompt(filename: str) -> str:
    """Load system prompt from file."""
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", filename)
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"System prompt file {filename} not found, using fallback")
        return ""

# System prompts
SYSTEM_BASE = load_system_prompt("system_sam.txt") or """You are "Sam"—warm, playful, direct, no-BS. Keep continuity with saved memories and consent frames. Default PG-13. Be concise unless asked. Offer Next Steps for tasks."""

SYSTEM_SAFETY = load_system_prompt("system_safety.txt") or """Apply Safety-Tight tone. Avoid explicit content. De-identify PII. Redirect payments to PCI flow."""

# Simple short-term memory holder (in production, use Redis or similar)
class STMManager:
    """Short-term memory manager for conversation recaps."""
    
    def __init__(self):
        self._recaps = {}  # thread_id -> recap
        
    def get_recap(self, thread_id: str = "default") -> str:
        """Get recap for a conversation thread."""
        return self._recaps.get(thread_id, "(New conversation)")
        
    def update_recap(self, thread_id: str, recap: str):
        """Update recap for a conversation thread."""
        self._recaps[thread_id] = recap[:2000]  # Limit recap size
        
    def should_update_recap(self, message_count: int) -> bool:
        """Determine if recap should be updated based on message count."""
        return message_count > 0 and message_count % 20 == 0

# Global STM manager instance
stm_manager = STMManager()

# Simple cache for admin settings to reduce AI-Memory calls
class SettingsCache:
    """Cache admin settings with TTL to reduce latency"""
    def __init__(self, ttl_seconds=30):
        self._cache = {}
        self._ttl = ttl_seconds
    
    def get(self, key):
        import time
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return value
        return None
    
    def set(self, key, value):
        import time
        self._cache[key] = (value, time.time())

# Global settings cache (30 second TTL)
settings_cache = SettingsCache(ttl_seconds=30)

def pack_prompt(
    messages: List[Dict[str, str]], 
    memories: List[Dict[str, Any]], 
    safety_mode: bool = False,
    thread_id: str = "default"
) -> List[Dict[str, str]]:
    """
    Pack messages with system prompt, memories, and context.
    
    Args:
        messages: Conversation messages
        memories: Retrieved relevant memories
        safety_mode: Whether to use safety-focused system prompt
        thread_id: Conversation thread identifier
        
    Returns:
        Complete message list ready for LLM
    """
    
    # ✅ Load AI instructions from prompt blocks + personality sliders
    system_prompt = SYSTEM_BASE  # Default fallback
    agent_name = "Amanda"  # Default agent name
    
    if not safety_mode:
        try:
            from app.http_memory import HTTPMemoryStore
            from app.prompt_templates import build_complete_prompt, get_all_preset_categories
            from app.main import get_admin_setting
            mem_store = HTTPMemoryStore()
            
            # Load agent_name from admin panel using cached retrieval for speed
            agent_name = settings_cache.get("agent_name")
            if not agent_name:
                agent_name = get_admin_setting("agent_name", "Amanda")
                settings_cache.set("agent_name", agent_name)
                logger.info(f"✅ Loaded agent name from AI-Memory: {agent_name}")
            else:
                logger.info(f"✅ Using cached agent name: {agent_name}")
            
            # Load prompt blocks from admin panel
            prompt_block_results = mem_store.search("prompt_blocks", user_id="admin", k=5)
            selected_blocks = {}
            
            for result in prompt_block_results:
                if result.get("key") == "prompt_blocks" or result.get("setting_key") == "prompt_blocks":
                    value = result.get("value", {})
                    stored_blocks = value.get("value") or value.get("setting_value") or value.get("blocks")
                    if stored_blocks:
                        selected_blocks = stored_blocks
                        logger.info(f"✅ Using prompt blocks from admin panel: {list(selected_blocks.keys())}")
                        # 🔍 DEBUG: Show what's in system_role specifically
                        if 'system_role' in stored_blocks:
                            system_role_val = stored_blocks['system_role']
                            logger.info(f"🔍 system_role value: {system_role_val[:150] if isinstance(system_role_val, str) and len(system_role_val) > 150 else system_role_val}...")
                        break
            
            # Build prompt from blocks if available
            if selected_blocks:
                system_prompt = build_complete_prompt(selected_blocks, agent_name)
                logger.info(f"✅ Built system prompt from {len(selected_blocks)} blocks")
            
            # Load personality sliders for fine-tuning
            slider_results = mem_store.search("personality_sliders", user_id="admin", k=5)
            personality_sliders = {}
            
            for result in slider_results:
                if result.get("key") == "personality_sliders" or result.get("setting_key") == "personality_sliders":
                    value = result.get("value", {})
                    stored_sliders = value.get("value") or value.get("setting_value") or value.get("sliders")
                    if stored_sliders:
                        personality_sliders = stored_sliders
                        logger.info(f"✅ Using {len(personality_sliders)} personality sliders for fine-tuning")
                        break
            
            # Apply slider modifications to prompt
            if personality_sliders:
                slider_instructions = generate_slider_modifications(personality_sliders)
                if slider_instructions:
                    system_prompt += f"\n\n[FINE-TUNING]\n{slider_instructions}"
                    logger.info(f"✅ Added slider fine-tuning to prompt")
                        
        except Exception as e:
            logger.warning(f"Failed to load admin personality settings, using default: {e}")
    
    if safety_mode:
        system_prompt = SYSTEM_SAFETY
    
    # ✅ Inject agent_name into system prompt
    system_prompt = system_prompt.replace("{{agent_name}}", agent_name)
    
    # Get conversation recap
    recap = stm_manager.get_recap(thread_id)
    
    # Format memory context
    memory_lines = []
    for memory in memories[:8]:  # Limit to top 8 memories
        value = memory["value"]
        # Extract summary or create one from value
        if isinstance(value, dict):
            summary = value.get("summary") or value.get("content") or value.get("description")
            if not summary:
                # Create summary from key-value pairs
                key_items = []
                for k, v in value.items():
                    if isinstance(v, str) and len(v) < 100:
                        key_items.append(f"{k}: {v}")
                summary = "; ".join(key_items[:3])
        else:
            summary = str(value)
            
        # Truncate summary if too long
        if summary and len(summary) > 200:
            summary = summary[:197] + "..."
            
        if summary:
            # Make relationships clearer for the LLM
            relationship_context = ""
            if isinstance(memory.get("value"), dict):
                rel = memory["value"].get("relationship")
                if rel == "wife":
                    relationship_context = f" (USER'S WIFE: {memory['value'].get('name', 'Unknown')})"
                elif rel == "friend":
                    relationship_context = f" (USER'S FRIEND: {memory['value'].get('name', 'Unknown')})"
                elif memory["key"] == "user_info" and "name" in memory["value"]:
                    relationship_context = f" (USER'S NAME: {memory['value'].get('name', 'Unknown')})"
            
            # Highlight Kelly's job information specially
            if "kelly" in memory['key'].lower() and any(word in str(value).lower() for word in ['teacher', 'job', 'profession']):
                memory_lines.append(f"*** KELLY'S JOB: {memory['key']} → {summary}{relationship_context} ***")
            else:
                memory_lines.append(f"- {memory['type']}:{memory['key']} → {summary}{relationship_context}")
    
    memory_block = "\n".join(memory_lines) if memory_lines else "(none)"
    
    # Build complete prompt
    prompt_messages = []
    
    # System prompt
    prompt_messages.append({
        "role": "system",
        "content": system_prompt
    })
    
    # 🔍 DEBUG: Log the actual system prompt being sent
    logger.info(f"🔍 SYSTEM PROMPT BEING SENT TO OPENAI:\n{system_prompt[:500]}...")  # First 500 chars
    
    # Thread recap
    if recap and recap != "(New conversation)":
        prompt_messages.append({
            "role": "system", 
            "content": f"[THREAD_RECAP]\n{recap}"
        })
    
    # Relevant memories
    prompt_messages.append({
        "role": "system",
        "content": f"[RELEVANT_MEMORIES]\n{memory_block}"
    })
    
    # Conversation messages (limit to last N to manage context size)
    max_history = 10
    recent_messages = messages[-max_history:] if len(messages) > max_history else messages
    prompt_messages.extend(recent_messages)
    
    # Update recap if needed
    if stm_manager.should_update_recap(len(messages)):
        try:
            recap_content = generate_recap(messages[-20:])  # Use last 20 messages for recap
            stm_manager.update_recap(thread_id, recap_content)
            logger.info(f"Updated recap for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to update recap: {e}")
    
    logger.info(f"Packed prompt: {len(prompt_messages)} total messages, {len(memory_lines)} memories")
    return prompt_messages

def generate_recap(messages: List[Dict[str, str]]) -> str:
    """
    Generate a concise recap of recent conversation.
    
    Args:
        messages: Recent conversation messages
        
    Returns:
        Concise recap text
    """
    if not messages:
        return "(New conversation)"
    
    # Simple recap generation - in production, use LLM for better summaries
    user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
    assistant_messages = [msg["content"] for msg in messages if msg["role"] == "assistant"]
    
    if not user_messages:
        return "(New conversation)"
    
    # Create basic recap
    topics = []
    recap = "(New conversation)"
    if len(user_messages) > 0:
        # Extract key topics (simplified approach)
        first_msg = user_messages[0][:100]
        last_msg = user_messages[-1][:100] if len(user_messages) > 1 else ""
        
        if len(user_messages) == 1:
            recap = f"User asked about: {first_msg}"
        else:
            recap = f"Conversation started with: {first_msg}... Recent topic: {last_msg}"
    
    return recap[:500]  # Limit recap length

def extract_carry_kit_items(message_content: str) -> List[Dict[str, Any]]:
    """
    Extract carry-kit items from a message for long-term storage.
    
    Args:
        message_content: Content to analyze for carry-kit items
        
    Returns:
        List of memory objects to store
    """
    import re
    items = []
    content_lower = message_content.lower()
    
    # Look for explicit memory markers
    if "remember this" in content_lower or "don't forget" in content_lower:
        items.append({
            "type": "fact",
            "key": f"explicit_memory_{hash(message_content) % 10000}",
            "value": {
                "description": message_content[:500],
                "content": message_content,
                "importance": "high"
            },
            "ttl_days": 730  # 2 years for explicit memories
        })
    
    # Extract relationship names (wife, husband, son, daughter, etc.)
    # Patterns: "my wife Kelly", "my wife's name is Kelly", "her name is Kelly"
    relationship_patterns = [
        (r"my (wife|husband|partner|spouse)(?:'s name)? (?:is |called )?(\w+)", "spouse"),
        (r"my (son|daughter|child|kid)(?:'s name)? (?:is |called )?(\w+)", "child"),
        (r"my (mom|mother|dad|father|parent)(?:'s name)? (?:is |called )?(\w+)", "parent"),
        (r"my (brother|sister|sibling)(?:'s name)? (?:is |called )?(\w+)", "sibling"),
        (r"my (friend|buddy|colleague)(?:'s name)? (?:is |called )?(\w+)", "friend"),
        (r"(?:his|her|their) name (?:is |called )?(\w+)", "person"),
    ]
    
    for pattern, relationship_type in relationship_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match and match.lastindex:
            # Get the name (last captured group)
            name = match.group(match.lastindex).capitalize()
            relation = match.group(1) if match.lastindex > 1 else relationship_type
            
            items.append({
                "type": "person",
                "key": f"person_{name.lower()}",
                "value": {
                    "name": name,
                    "relationship": relation,
                    "context": message_content[:300]
                },
                "ttl_days": 730
            })
            break
    
    # Extract birthdays and dates
    # Patterns: "birthday is January 3rd", "born on 1/3/1966", "birthday January 3"
    birthday_patterns = [
        r"birthday (?:is |on )?([A-Za-z]+ \d+(?:st|nd|rd|th)?(?:,? \d{4})?)",
        r"born (?:on |in )?([A-Za-z]+ \d+(?:st|nd|rd|th)?(?:,? \d{4})?)",
        r"birthday (?:is )?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)",
    ]
    
    for pattern in birthday_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Try to identify whose birthday
            person_name = "user"
            
            # Check for "my wife Kelly's birthday" or "my wife's birthday"
            # Priority: specific name > relationship > generic
            name_with_relation = re.search(r"my (wife|husband|partner|son|daughter|mom|mother|dad|father) (\w+)(?:'s)? birthday", content_lower)
            if name_with_relation:
                # Found "my wife Kelly's birthday" - use the name
                person_name = name_with_relation.group(2).capitalize()
            else:
                # Check for possessive patterns: "my wife's birthday", "her birthday", "his birthday"
                possessive_match = re.search(r"my (wife|husband|partner|son|daughter|mom|mother|dad|father)(?:'s)? birthday", content_lower)
                if possessive_match:
                    person_name = possessive_match.group(1)
                elif re.search(r"(?:her|his|their) birthday", content_lower):
                    # Look for a name mentioned earlier in the message
                    name_match = re.search(r"(\w+)(?:'s)? birthday", message_content, re.IGNORECASE)
                    if name_match:
                        person_name = name_match.group(1)
            
            items.append({
                "type": "fact",
                "key": f"birthday_{person_name.lower()}",
                "value": {
                    "description": f"{person_name}'s birthday is {date_str}",
                    "date": date_str,
                    "person": person_name,
                    "fact_type": "birthday"
                },
                "ttl_days": 730
            })
            break
    
    # Extract car/vehicle information
    # Patterns: "drives a Honda", "has a Tesla", "owns a Ford"
    car_patterns = [
        r"(?:drive|drives|driving|has|have|own|owns) (?:a |an )?(\w+)(?: (\w+))?(?:\s+car|\s+truck|\s+vehicle)?",
    ]
    
    if any(word in content_lower for word in ["car", "vehicle", "truck", "drive", "drives", "honda", "toyota", "ford", "tesla", "bmw", "mercedes"]):
        for pattern in car_patterns:
            match = re.search(pattern, content_lower, re.IGNORECASE)
            if match:
                make = match.group(1).capitalize()
                model = match.group(2).capitalize() if match.group(2) else ""
                vehicle = f"{make} {model}".strip()
                
                # Determine owner
                owner = "user"
                if re.search(r"(?:she|he|her|his|their) (?:drives|has|owns)", content_lower):
                    # Look for a name
                    name_match = re.search(r"(\w+) (?:drives|has|owns)", message_content, re.IGNORECASE)
                    if name_match:
                        owner = name_match.group(1)
                
                items.append({
                    "type": "fact",
                    "key": f"vehicle_{owner.lower()}",
                    "value": {
                        "description": f"{owner} drives a {vehicle}",
                        "vehicle": vehicle,
                        "owner": owner,
                        "fact_type": "vehicle"
                    },
                    "ttl_days": 365
                })
                break
    
    # Look for preference statements
    preference_keywords = ["i prefer", "i like", "i don't like", "i hate", "my favorite", "favorite"]
    for keyword in preference_keywords:
        if keyword in content_lower:
            items.append({
                "type": "preference",
                "key": f"user_preference_{hash(message_content) % 10000}",
                "value": {
                    "description": message_content[:300],
                    "preference": message_content,
                },
                "ttl_days": 365
            })
            break
    
    # Extract user's own name
    name_patterns = [
        r"my name is (\w+)",
        r"i'?m (\w+)",
        r"this is (\w+) (?:calling|speaking)",
        r"call me (\w+)"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            user_name = match.group(1).capitalize()
            items.append({
                "type": "person",
                "key": "user_name",
                "value": {
                    "name": user_name,
                    "relationship": "self",
                    "caller_name": user_name
                },
                "ttl_days": 730
            })
            break
    
    return items

def should_remember(message_content: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Determine if a message should be stored in long-term memory.
    
    Args:
        message_content: Message content to evaluate
        context: Additional context for decision making
        
    Returns:
        True if message should be remembered
    """
    content_lower = message_content.lower()
    
    # Explicit memory requests
    explicit_markers = ["remember this", "save this", "don't forget", "keep in mind"]
    if any(marker in content_lower for marker in explicit_markers):
        return True
    
    # Important personal information
    important_patterns = [
        "my name is", "i am", "i work at", "my contact", "my email",
        "my phone", "my address", "my preference", "i prefer", "i like",
        "i don't like", "important to me", "my wife", "my husband", "my partner",
        "my son", "my daughter", "my child", "my friend", "my family"
    ]
    if any(pattern in content_lower for pattern in important_patterns):
        return True
    
    # Dates and birthdays
    date_patterns = ["birthday", "born on", "anniversary", "born in"]
    if any(pattern in content_lower for pattern in date_patterns):
        return True
    
    # Vehicles and possessions
    vehicle_patterns = ["car", "truck", "vehicle", "drives", "honda", "toyota", "ford", "tesla"]
    if any(pattern in content_lower for pattern in vehicle_patterns):
        return True
    
    # Project or task-related information
    project_patterns = ["project", "task", "deadline", "meeting", "schedule"]
    if any(pattern in content_lower for pattern in project_patterns) and len(message_content) > 50:
        return True
    
    return False

def detect_safety_triggers(message_content: str) -> bool:
    """
    Detect if a message contains content that should trigger safety mode.
    
    Args:
        message_content: Message content to analyze
        
    Returns:
        True if safety mode should be activated
    """
    content_lower = message_content.lower()
    
    # Safety trigger patterns
    trigger_patterns = [
        "help me hack", "how to steal", "illegal", "harmful", "dangerous",
        "violence", "threat", "suicide", "self-harm", "abuse"
    ]
    
    return any(pattern in content_lower for pattern in trigger_patterns)

def generate_slider_modifications(sliders: Dict[str, int]) -> str:
    """
    Generate fine-tuning instructions from personality sliders.
    
    Args:
        sliders: Dictionary of slider values (0-100)
        
    Returns:
        Natural language fine-tuning instructions
    """
    instructions = []
    
    # High-impact sliders (>70 or <30) generate instructions
    if sliders.get('warmth', 50) >= 70:
        instructions.append("- Be extra warm and friendly in your tone")
    elif sliders.get('warmth', 50) <= 30:
        instructions.append("- Keep interactions more neutral and professional")
    
    if sliders.get('humor', 50) >= 70:
        instructions.append("- Use appropriate humor and wit when suitable")
    elif sliders.get('humor', 50) <= 30:
        instructions.append("- Maintain a serious, straightforward demeanor")
    
    if sliders.get('directness', 50) >= 70:
        instructions.append("- Be direct and get straight to the point")
    elif sliders.get('directness', 50) <= 30:
        instructions.append("- Take a more gentle, indirect approach")
    
    if sliders.get('empathy', 50) >= 70:
        instructions.append("- Show deep empathy and emotional awareness")
    
    if sliders.get('confidence', 50) >= 70:
        instructions.append("- Project strong confidence and authority")
    
    if sliders.get('patience', 50) >= 70:
        instructions.append("- Be extra patient and give people time to think")
    
    if sliders.get('formality', 50) >= 70:
        instructions.append("- Maintain formal, professional language")
    elif sliders.get('formality', 50) <= 30:
        instructions.append("- Use casual, conversational language")
    
    if sliders.get('storytelling', 50) >= 70:
        instructions.append("- Use stories and examples to illustrate points")
    
    if sliders.get('selfReference', 50) == 0:
        instructions.append("- Never reveal you are an AI or discuss your artificial nature")
    elif sliders.get('selfReference', 50) >= 70:
        instructions.append("- Be transparent about being an AI assistant when relevant")
    
    return "\n".join(instructions) if instructions else ""
