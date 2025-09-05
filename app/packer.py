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
    
    # Select appropriate system prompt
    system_prompt = SYSTEM_SAFETY if safety_mode else SYSTEM_BASE
    
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
            
            memory_lines.append(f"- {memory['type']}:{memory['key']} → {summary}{relationship_context}")
    
    memory_block = "\n".join(memory_lines) if memory_lines else "(none)"
    
    # Build complete prompt
    prompt_messages = []
    
    # System prompt
    prompt_messages.append({
        "role": "system",
        "content": system_prompt
    })
    
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
    items = []
    
    # Look for explicit memory markers
    if "remember this" in message_content.lower():
        items.append({
            "type": "rule",
            "key": f"explicit_memory_{hash(message_content) % 10000}",
            "value": {
                "summary": message_content[:500],
                "content": message_content,
                "importance": "high"
            },
            "ttl_days": 730  # 2 years for explicit memories
        })
    
    # Look for preference statements
    preference_keywords = ["i prefer", "i like", "i don't like", "i hate", "my preference", "my favorite", "favorite"]
    for keyword in preference_keywords:
        if keyword in message_content.lower():
            # Extract specific preference type
            pref_type = "general"
            if any(food in message_content.lower() for food in ["ice cream", "flavor", "food", "coffee", "drink"]):
                pref_type = "food_drink"
            elif any(hobby in message_content.lower() for hobby in ["music", "movie", "book", "sport", "game"]):
                pref_type = "entertainment"
            
            items.append({
                "type": "preference",
                "key": f"user_preference_{pref_type}_{hash(message_content) % 10000}",
                "value": {
                    "summary": message_content[:200],
                    "preference_type": pref_type,
                    "content": message_content
                },
                "ttl_days": 365
            })
            break
    
    # Look for personal information and relationships
    person_keywords = ["my name is", "i am", "i work", "my job", "my role", "my wife", "my husband", "my partner", "my friend", "my family"]
    for keyword in person_keywords:
        if keyword in message_content.lower():
            items.append({
                "type": "person",
                "key": "user_info" if "my name" in keyword else "relationship_info",
                "value": {
                    "summary": message_content[:200],
                    "info_type": "personal" if "my name" in keyword else "relationship"
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
        "i don't like", "important to me"
    ]
    if any(pattern in content_lower for pattern in important_patterns):
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
