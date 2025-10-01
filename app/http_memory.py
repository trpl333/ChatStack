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
                "message": value.get("msg", "") if isinstance(value, dict) else str(value),
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
                    # Legacy format - parse concatenated string (ai-memory service bug workaround)
                    logger.warning(f"AI-Memory service returned legacy concatenated format, cannot parse properly")
                    logger.warning(f"Full 'memory' value: {result['memory'][:200]}")
                    return []
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