import os
import json
import uuid
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
EMBED_DIM = int(os.environ.get("EMBED_DIM", 768))
DB_URL = os.environ.get("DATABASE_URL")

def embed(text: str) -> np.ndarray:
    """
    Generate embedding vector for the given text.
    
    This is currently a placeholder implementation using deterministic hashing.
    In production, replace with a real embedding service like OpenAI embeddings,
    Sentence Transformers, or similar.
    
    Args:
        text: Input text to embed
        
    Returns:
        Normalized embedding vector
    """
    # Deterministic hash-based embedding (placeholder)
    # This ensures consistent embeddings for the same text across runs
    text_hash = abs(hash(text.lower().strip())) % (2**32)
    rng = np.random.default_rng(text_hash)
    
    # Generate random vector and normalize
    vector = rng.normal(size=EMBED_DIM)
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    
    return vector

class MemoryStore:
    """
    PostgreSQL-based memory store with vector similarity search using pgvector.
    """
    
    def __init__(self):
        """Initialize connection to PostgreSQL database."""
        if not DB_URL:
            raise ValueError("DATABASE_URL environment variable is required")
            
        try:
            self.conn = psycopg2.connect(DB_URL)
            self.conn.autocommit = True
            logger.info("Connected to PostgreSQL database")
            
            # Verify pgvector extension is available
            self._verify_extension()
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _verify_extension(self):
        """Verify that pgvector extension is installed."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                if not cur.fetchone():
                    logger.warning("pgvector extension not found - attempting to install")
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as e:
            logger.error(f"Failed to verify/install pgvector extension: {e}")
            raise

    def write(self, memory_type: str, key: str, value: Dict[str, Any], ttl_days: int = 365, source: str = "orchestrator") -> str:
        """
        Store a memory object in the database.
        
        Args:
            memory_type: Type of memory (person, preference, project, rule, moment, fact)
            key: Unique key/identifier for the memory
            value: Memory content as dictionary
            ttl_days: Time to live in days
            source: Source of the memory
            
        Returns:
            UUID of the stored memory
        """
        try:
            # Generate embedding for the memory content
            content_text = json.dumps(value, sort_keys=True)
            embedding = embed(content_text).tolist()
            
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memories (type, k, value_json, embedding, ttl_days, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (memory_type, key, Json(value), embedding, ttl_days, source)
                )
                result = cur.fetchone()
                if result:
                    memory_id = result[0]
                else:
                    raise Exception("Failed to get memory ID")
                
            logger.info(f"Stored memory: {memory_type}:{key} with ID {memory_id}")
            return str(memory_id)
            
        except Exception as e:
            logger.error(f"Failed to write memory: {e}")
            raise

    def search(self, query_text: str, k: int = 6, memory_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using vector similarity.
        
        Args:
            query_text: Text to search for
            k: Number of results to return
            memory_types: Optional filter by memory types
            
        Returns:
            List of memory objects with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = embed(query_text).tolist()
            
            # Build query with optional type filtering
            type_filter = ""
            params = [query_embedding]
            
            if memory_types:
                type_filter = "AND type = ANY(%s)"
                params.append(memory_types)
            
            params.append(query_embedding)
            params.append(k)
            
            query = f"""
                SELECT id, type, k, value_json, embedding <-> %s::vector as distance
                FROM memories
                WHERE created_at > NOW() - INTERVAL '1 year' {type_filter}
                ORDER BY embedding <-> %s::vector
                LIMIT %s
            """
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row["id"]),
                    "type": row["type"],
                    "key": row["k"],
                    "value": row["value_json"],
                    "distance": float(row["distance"])
                })
            
            logger.info(f"Memory search for '{query_text[:50]}...' returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.
        
        Args:
            memory_id: UUID of the memory
            
        Returns:
            Memory object or None if not found
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, type, k, value_json FROM memories WHERE id = %s",
                    (memory_id,)
                )
                row = cur.fetchone()
                
            if row:
                return {
                    "id": str(row["id"]),
                    "type": row["type"],
                    "key": row["k"],
                    "value": row["value_json"]
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            return None

    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: UUID of the memory to delete
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
                deleted = cur.rowcount > 0
                
            logger.info(f"Memory {memory_id} {'deleted' if deleted else 'not found'}")
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False

    def cleanup_expired(self) -> int:
        """
        Remove expired memories based on TTL.
        
        Returns:
            Number of memories deleted
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM memories 
                    WHERE created_at + INTERVAL '1 day' * ttl_days < NOW()
                    """
                )
                deleted_count = cur.rowcount
                
            logger.info(f"Cleaned up {deleted_count} expired memories")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored memories.
        
        Returns:
            Dictionary with memory statistics
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        type,
                        COUNT(*) as count,
                        AVG(EXTRACT(days FROM NOW() - created_at)) as avg_age_days
                    FROM memories 
                    GROUP BY type
                    ORDER BY count DESC
                    """
                )
                type_stats = cur.fetchall()
                
                cur.execute("SELECT COUNT(*) as total FROM memories")
                result = cur.fetchone()
                total_count = result["total"] if result else 0
                
            return {
                "total_memories": total_count,
                "by_type": [dict(row) for row in type_stats]
            }
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total_memories": 0, "by_type": []}

    def close(self):
        """Close the database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.info("Database connection closed")
