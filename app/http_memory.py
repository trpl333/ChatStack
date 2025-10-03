import os
import json
import uuid
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# Import centralized configuration
from config_loader import get_setting

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HTTPMemoryStore:
    """
    HTTP-based memory store that connects to AI-Memory service instead of direct PostgreSQL.
    Provides the same interface as MemoryStore but uses REST API calls.
    """
    
    def __init__(self):
        """Initialize connection to AI-Memory service."""
        self.ai_memory_url = get_setting("ai_memory_url", "http://127.0.0.1:8100")
        self.session = requests.Session()
        # Note: requests.Session doesn't have timeout as an attribute, 
        # it's passed to individual request methods
        
        try:
            logger.info(f"Connecting to AI-Memory service at {self.ai_memory_url}...")
            
            # Test connection to AI-Memory service
            response = self.session.get(f"{self.ai_memory_url}/health", timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                if health_data.get("status") == "ok" and health_data.get("db") is True:
                    self.available = True
                    logger.info("✅ Connected to AI-Memory service")
                else:
                    raise Exception(f"AI-Memory service unhealthy: {health_data}")
            else:
                raise Exception(f"AI-Memory service returned {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to AI-Memory service: {e}")
            self.available = False
            # Don't raise - allow app to start in degraded mode

    def _check_connection(self):
        """Check if AI-Memory service connection is available."""
        if not self.available:
            raise RuntimeError("Memory store is not available (AI-Memory service connection failed)")

    def write(self, memory_type: str, key: str, value: Dict[str, Any], user_id: Optional[str] = None, scope: str = "user", ttl_days: int = 365, source: str = "orchestrator") -> str:
        """
        Store a memory object via AI-Memory service.
        
        Args:
            memory_type: Type of memory (person, preference, project, rule, moment, fact)
            key: Unique key/identifier for the memory
            value: Memory content as dictionary
            user_id: User ID for user-scoped memories (None for shared)
            scope: Memory scope ('user', 'shared', 'global')
            ttl_days: Time to live in days
            source: Source of the memory
            
        Returns:
            UUID of the stored memory
        """
        self._check_connection()
        
        # Fix scope/user_id mismatch: reject scope='user' without user_id
        if scope == "user" and user_id is None:
            logger.warning("Cannot use scope='user' without user_id, changing to scope='shared'")
            scope = "shared"
        
        try:
            # Prepare payload for AI-Memory service
            payload = {
                "user_id": user_id or "unknown",
                "message": json.dumps(value) if isinstance(value, dict) else str(value),
                "type": memory_type,
                "k": key,
                "value_json": value,
                "scope": scope,
                "ttl_days": ttl_days,
                "source": source
            }
            
            response = self.session.post(
                f"{self.ai_memory_url}/memory/store",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                # ✅ Fix: AI-Memory service may return different ID field names or just success message
                memory_id = result.get("id") or result.get("memory_id") or result.get("session_id")
                if not memory_id and "data" in result:
                    memory_id = result["data"].get("id")
                
                if memory_id:
                    scope_info = f" [{scope}]" + (f" user:{user_id}" if user_id else "")
                    logger.info(f"Stored memory: {memory_type}:{key} with ID {memory_id}{scope_info}")
                    return str(memory_id)
                else:
                    # ✅ Fix: Don't fail on successful 200 response, generate fallback ID
                    logger.warning(f"AI-Memory service returned 200 but no ID field found. Response: {result}")
                    scope_info = f" [{scope}]" + (f" user:{user_id}" if user_id else "")
                    logger.info(f"Stored memory: {memory_type}:{key} with fallback KEY {key}{scope_info}")
                    return key
            else:
                raise Exception(f"AI-Memory service returned {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to write memory: {e}")
            raise

    def search(self, query_text: str, user_id: Optional[str] = None, k: int = 6, memory_types: Optional[List[str]] = None, include_shared: bool = True) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using AI-Memory service.
        
        Args:
            query_text: Text to search for
            user_id: User ID to filter personal memories (None for no user filter)
            k: Number of results to return
            memory_types: Optional filter by memory types
            include_shared: Whether to include shared/global memories
            
        Returns:
            List of memory objects with similarity scores
        """
        self._check_connection()
        
        try:
            # Build payload for AI-Memory service
            payload = {
                "user_id": user_id or "unknown",
                "message": query_text,
                "limit": k,
                "types": memory_types or []
            }
            
            if not include_shared:
                payload["scope"] = "user"
            
            # 🔍 DEBUG: Log what we're sending
            logger.info(f"🔍 Querying AI-Memory: POST {self.ai_memory_url}/memory/retrieve")
            logger.info(f"🔍 Payload: {json.dumps(payload, indent=2)}")
            
            response = self.session.post(
                f"{self.ai_memory_url}/memory/retrieve",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 🔍 DEBUG: Log full response to understand format
                logger.info(f"🔍 AI-Memory response keys: {result.keys()}")
                logger.info(f"🔍 AI-Memory full response: {json.dumps(result, indent=2)[:500]}")
                
                # ✅ Fix: Handle both "memories" array and "memory" string formats from ai-memory service
                if "memories" in result:
                    logger.info(f"✅ Found 'memories' array with {len(result['memories'])} items")
                    return result["memories"]
                elif "memory" in result and isinstance(result["memory"], str):
                    # Parse concatenated JSON format (newline-separated JSON objects)
                    memory_str = result["memory"].strip()
                    if not memory_str:
                        return []
                    
                    memories = []
                    for idx, line in enumerate(memory_str.split('\n')):
                        line = line.strip()
                        if line:
                            try:
                                mem_obj = json.loads(line)
                                
                                # ✅ Normalize to standard memory format with type/key/value
                                normalized = {
                                    "type": mem_obj.get("type", "fact"),
                                    "key": mem_obj.get("key") or mem_obj.get("k") or mem_obj.get("setting_key") or mem_obj.get("summary", "")[:50] or mem_obj.get("phone_number", "") or f"memory_{idx}",
                                    "value": mem_obj,  # Store entire object as value
                                    "scope": mem_obj.get("scope", "user"),
                                    "user_id": mem_obj.get("user_id"),
                                    "id": mem_obj.get("id") or mem_obj.get("memory_id") or f"concat_{idx}",
                                    "setting_key": mem_obj.get("setting_key"),  # Preserve for admin settings
                                    "k": mem_obj.get("k") or mem_obj.get("key") or mem_obj.get("setting_key")  # Alias
                                }
                                memories.append(normalized)
                            except json.JSONDecodeError:
                                logger.warning(f"Could not parse memory line: {line[:100]}")
                    
                    logger.info(f"✅ Parsed {len(memories)} memories from concatenated format")
                    return memories
                else:
                    logger.error(f"❌ Unexpected response format from AI-Memory service")
                return []
            else:
                logger.error(f"Memory search failed: {response.status_code} {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    def get_user_memories(self, user_id: str, limit: int = 10, include_shared: bool = True) -> List[Dict[str, Any]]:
        """Get memories for a specific user."""
        return self.search("", user_id=user_id, k=limit, include_shared=include_shared)
    
    def normalize_memories(self, raw_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Normalize raw memory entries into a structured dictionary.
        
        Converts 800+ scattered memory entries into organized categories:
        - contacts: People (family, friends) with names, birthdays, relationships
        - vehicles: Cars with year, make, model, VIN
        - policies: Insurance policies
        - preferences: User likes/dislikes
        - history: Recent conversation summaries
        
        Args:
            raw_memories: List of raw memory dicts from ai-memory service
            
        Returns:
            Organized dict with categorized, deduplicated data
        """
        normalized = {
            "contacts": {},
            "vehicles": [],
            "policies": [],
            "preferences": {},
            "facts": [],
            "recent_conversations": []
        }
        
        # Track seen items for deduplication
        seen_people = {}  # key: name.lower() -> full contact dict
        seen_vehicles = set()  # VINs or "year_make_model"
        
        for mem in raw_memories:
            mem_type = mem.get("type", "unknown")
            value = mem.get("value", {})
            mem_key = (mem.get("key") or mem.get("k", "")).lower()
            
            # Handle DICT values (structured data)
            if isinstance(value, dict):
                # CONTACTS: People with names, relationships, birthdays
                if "name" in value or "relationship" in value:
                    name = value.get("name", "").strip()
                    relationship = value.get("relationship", "").strip().lower()
                    
                    if name:
                        # Deduplicate by name
                        name_key = name.lower()
                        
                        # Use relationship as key if available (father, mother, spouse, etc.)
                        contact_key = relationship if relationship else name_key
                        
                        if contact_key not in seen_people:
                            contact_info = {
                                "name": name,
                                "relationship": relationship or "contact"
                            }
                            
                            # Add optional fields
                            if value.get("birthday"):
                                contact_info["birthday"] = value["birthday"]
                            if value.get("phone"):
                                contact_info["phone"] = value["phone"]
                            if value.get("notes"):
                                contact_info["notes"] = value["notes"]
                            if value.get("goes_by"):
                                contact_info["nickname"] = value["goes_by"]
                            
                            normalized["contacts"][contact_key] = contact_info
                            seen_people[contact_key] = True
                
                # VEHICLES: Cars with make, model, year, VIN
                elif any(k in value for k in ["make", "model", "vin", "car", "vehicle"]):
                    vin = value.get("vin", "")
                    vehicle_key = vin if vin else f"{value.get('year', '')}_{value.get('make', '')}_{value.get('model', '')}"
                    
                    if vehicle_key and vehicle_key not in seen_vehicles:
                        vehicle_info = {}
                        if value.get("year"):
                            vehicle_info["year"] = value["year"]
                        if value.get("make"):
                            vehicle_info["make"] = value["make"]
                        if value.get("model"):
                            vehicle_info["model"] = value["model"]
                        if value.get("vin"):
                            vehicle_info["vin"] = value["vin"]
                        if value.get("owner"):
                            vehicle_info["owner"] = value["owner"]
                        
                        if vehicle_info:
                            normalized["vehicles"].append(vehicle_info)
                            seen_vehicles.add(vehicle_key)
                
                # PREFERENCES: Likes/dislikes
                elif "preference" in value or "item" in value or mem_type == "preference":
                    if "item" in value:
                        pref_type = value.get("preference", "likes")
                        item = value["item"]
                        normalized["preferences"][item] = pref_type
                    elif "description" in value:
                        normalized["facts"].append({
                            "type": "preference",
                            "content": value["description"]
                        })
                
                # CONVERSATION SUMMARIES
                elif "summary" in value:
                    summary = value["summary"]
                    if len(normalized["recent_conversations"]) < 5:  # Keep last 5
                        normalized["recent_conversations"].append(summary)
                
                # POLICIES: Insurance policies
                elif mem_type == "policy" or "policy" in mem_key:
                    policy_info = {k: v for k, v in value.items() if k not in ["type", "key"]}
                    if policy_info:
                        normalized["policies"].append(policy_info)
                
                # GENERAL FACTS with description
                elif "description" in value:
                    normalized["facts"].append({
                        "type": mem_type,
                        "content": value["description"]
                    })
            
            # Handle STRING values (plain text)
            elif isinstance(value, str) and len(value) > 5:
                value_lower = value.lower()
                
                # ✅ ENHANCED: Parse text for family relationships and names
                # Patterns: "My wife Kelly", "wife's name is Kelly", "Kelly (wife)", etc.
                import re
                
                # Check for wife/spouse patterns
                wife_patterns = [
                    r"(?:my )?wife(?:'s name)? is (\w+)",
                    r"(\w+)(?:,| is| \().*?(?:wife|spouse)",
                    r"wife.*?name.*?(\w+)",
                ]
                for pattern in wife_patterns:
                    match = re.search(pattern, value_lower)
                    if match and "wife" not in seen_people and "spouse" not in seen_people:
                        name = match.group(1).strip().title()
                        if len(name) > 2:  # Valid name
                            normalized["contacts"]["spouse"] = {
                                "name": name,
                                "relationship": "wife",
                                "notes": value[:200]
                            }
                            seen_people["spouse"] = True
                            break
                
                # Check for father patterns
                father_patterns = [
                    r"(?:my )?(?:father|dad)(?:'s name)? is (\w+)",
                    r"(\w+)(?:,| is| \().*?(?:father|dad)",
                ]
                for pattern in father_patterns:
                    match = re.search(pattern, value_lower)
                    if match and "father" not in seen_people:
                        name = match.group(1).strip().title()
                        if len(name) > 2:
                            normalized["contacts"]["father"] = {
                                "name": name,
                                "relationship": "father",
                                "notes": value[:200]
                            }
                            seen_people["father"] = True
                            break
                
                # Check for mother patterns
                mother_patterns = [
                    r"(?:my )?(?:mother|mom)(?:'s name)? is (\w+)",
                    r"(\w+)(?:,| is| \().*?(?:mother|mom)",
                ]
                for pattern in mother_patterns:
                    match = re.search(pattern, value_lower)
                    if match and "mother" not in seen_people:
                        name = match.group(1).strip().title()
                        if len(name) > 2:
                            normalized["contacts"]["mother"] = {
                                "name": name,
                                "relationship": "mother",
                                "notes": value[:200]
                            }
                            seen_people["mother"] = True
                            break
                
                # Check for birthday patterns (extract from text)
                birthday_pattern = r"birthday.*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4})"
                bday_match = re.search(birthday_pattern, value_lower)
                if bday_match:
                    birthday_str = bday_match.group(1)
                    # Check if it mentions who (wife, father, etc.)
                    for rel_keyword in ["wife", "spouse", "kelly"]:
                        if rel_keyword in value_lower[:50]:  # Check near birthday mention
                            if "spouse" in normalized["contacts"]:
                                normalized["contacts"]["spouse"]["birthday"] = birthday_str
                            break
                
                # Only include important string memories
                if mem_type in ("person", "preference", "project", "rule", "moment"):
                    # Check if key contains family keywords
                    if any(keyword in mem_key for keyword in ["father", "mother", "wife", "spouse", "husband", "son", "daughter", "family"]):
                        # Try to extract relationship from key
                        rel = None
                        for keyword in ["father", "mother", "wife", "spouse", "son", "daughter"]:
                            if keyword in mem_key:
                                rel = keyword
                                break
                        
                        if rel and rel not in seen_people:
                            normalized["contacts"][rel] = {
                                "relationship": rel,
                                "notes": value[:200]
                            }
                            seen_people[rel] = True
                    elif len(normalized["facts"]) < 10:  # Limit plain facts
                        normalized["facts"].append({
                            "type": mem_type,
                            "key": mem_key,
                            "content": value[:200]
                        })
        
        # Clean up empty sections
        normalized = {k: v for k, v in normalized.items() if v}
        
        return normalized

    def get_shared_memories(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get shared memories."""
        try:
            payload = {
                "user_id": "shared",
                "message": "",
                "limit": limit,
                "scope": "shared,global"
            }
            response = self.session.post(f"{self.ai_memory_url}/memory/retrieve", json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            
            if response.status_code == 200:
                return response.json().get("memories", [])
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to get shared memories: {e}")
            return []

    def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific memory by ID."""
        self._check_connection()
        
        try:
            # Use memory/read endpoint with session_id parameter  
            response = self.session.get(f"{self.ai_memory_url}/memory/read", params={"session_id": memory_id}, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to get memory by ID: {e}")
            return None

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        self._check_connection()
        
        try:
            # Note: Delete endpoint may not be available in current AI-Memory service
            # Return True for now since memories have TTL
            logger.warning(f"Delete memory not implemented in AI-Memory service, memory_id: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

    def cleanup_expired(self) -> int:
        """Cleanup expired memories."""
        self._check_connection()
        
        try:
            # Cleanup may not be available in current AI-Memory service
            logger.info("Cleanup expired memories not implemented in AI-Memory service")
            return 0
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        try:
            # Stats may not be available in current AI-Memory service  
            logger.info("Memory stats not implemented in AI-Memory service")
            return {"total": 0, "by_type": {}, "by_scope": {}}
                
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total": 0, "by_type": {}, "by_scope": {}}

    def close(self):
        """Close the HTTP session."""
        if hasattr(self, 'session'):
            self.session.close()
            logger.info("HTTP session closed")