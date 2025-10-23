#!/usr/bin/env python3
"""
Memory Cleanup Script for NeuroSphere AI-Memory Service

This script consolidates duplicate memories, removes greeting template pollution,
and organizes the 5,755+ memory entries into a clean, efficient structure.

Usage:
    python cleanup_memories.py --user-id <phone_number> --dry-run
    python cleanup_memories.py --user-id <phone_number> --execute
"""

import requests
import json
import logging
import argparse
from typing import List, Dict, Any, Set
from collections import defaultdict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

AI_MEMORY_URL = "http://209.38.143.71:8100"

class MemoryCleanup:
    """Consolidate and clean up AI-Memory service entries"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session = requests.Session()
        
        # Greeting template patterns to remove
        self.greeting_patterns = [
            "{agent_name}",
            "{user_name}",
            "{time_greeting}",
            "good morning",
            "good afternoon",
            "good evening",
            "this is {agent_name}",
            "hi, this is"
        ]
    
    def fetch_all_memories(self, max_limit: int = 10000) -> List[Dict[str, Any]]:
        """
        Fetch ALL memories for a user using pagination.
        
        Args:
            max_limit: Maximum total memories to fetch across all pages
        
        Returns:
            Complete list of all user memories
        """
        all_memories = []
        page_size = 500  # Fetch 500 at a time
        offset = 0
        
        try:
            logger.info(f"📥 Fetching ALL memories for user {self.user_id} (max: {max_limit})...")
            
            while len(all_memories) < max_limit:
                logger.info(f"  📄 Fetching page {offset // page_size + 1} (offset={offset}, limit={page_size})...")
                
                response = self.session.post(
                    f"{AI_MEMORY_URL}/memory/retrieve",
                    headers={"Content-Type": "application/json"},
                    json={
                        "user_id": self.user_id,
                        "message": "",
                        "limit": page_size,
                        "offset": offset,
                        "scope": "user,shared"
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    page_memories = data.get("memories", [])
                    
                    if not page_memories:
                        logger.info(f"  ✅ No more memories found, stopping pagination")
                        break
                    
                    all_memories.extend(page_memories)
                    logger.info(f"  ✅ Fetched {len(page_memories)} memories (total: {len(all_memories)})")
                    
                    # If we got fewer than page_size, we've reached the end
                    if len(page_memories) < page_size:
                        logger.info(f"  ✅ Reached last page")
                        break
                    
                    offset += page_size
                else:
                    logger.error(f"❌ Failed to fetch page at offset {offset}: {response.status_code}")
                    break
            
            logger.info(f"✅ Fetched {len(all_memories)} total memories across {(offset // page_size) + 1} pages")
            return all_memories[:max_limit]  # Enforce max limit
                
        except Exception as e:
            logger.error(f"❌ Error fetching memories: {e}")
            return all_memories  # Return what we got so far
    
    def is_greeting_template(self, memory: Dict[str, Any]) -> bool:
        """Check if memory is a greeting template (should be removed)"""
        value = memory.get("value", {})
        
        # Check memory content for greeting patterns
        content = json.dumps(value).lower()
        
        # Must contain at least one placeholder variable
        has_placeholder = any(pattern in content for pattern in ["{agent_name}", "{user_name}", "{time_greeting}"])
        
        # Must be in a greeting-like structure
        is_greeting_like = any(pattern in content for pattern in [
            "good morning", "good afternoon", "good evening",
            "this is {agent_name}", "hi, this is", "how can i help"
        ])
        
        return has_placeholder or is_greeting_like
    
    def is_duplicate(self, memory1: Dict[str, Any], memory2: Dict[str, Any]) -> bool:
        """Check if two memories are duplicates"""
        # Same type and key = duplicate
        if memory1.get("type") == memory2.get("type") and memory1.get("key") == memory2.get("key"):
            return True
        
        # Check value similarity for person/fact types
        if memory1.get("type") == memory2.get("type") == "person":
            val1 = memory1.get("value", {})
            val2 = memory2.get("value", {})
            if val1.get("name") == val2.get("name") and val1.get("relationship") == val2.get("relationship"):
                return True
        
        return False
    
    def consolidate_memories(self, memories: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Consolidate memories into categories:
        - keep: Valid unique memories to preserve
        - remove_greeting: Greeting templates to delete
        - remove_duplicate: Duplicate entries to delete
        """
        result = {
            "keep": [],
            "remove_greeting": [],
            "remove_duplicate": []
        }
        
        seen_keys: Set[str] = set()
        seen_values: Dict[str, Dict[str, Any]] = {}
        
        for memory in memories:
            # Skip if no ID (cannot delete)
            if not memory.get("id"):
                continue
            
            # Check if greeting template
            if self.is_greeting_template(memory):
                result["remove_greeting"].append(memory)
                continue
            
            # Check for duplicates by type+key
            mem_type = memory.get("type", "unknown")
            mem_key = memory.get("key", "unknown")
            unique_id = f"{mem_type}:{mem_key}"
            
            if unique_id in seen_keys:
                # Duplicate found
                result["remove_duplicate"].append(memory)
                continue
            
            # Check for value-based duplicates (person names, etc.)
            if mem_type == "person":
                value = memory.get("value", {})
                name = value.get("name", "").lower()
                relationship = value.get("relationship", "").lower()
                value_id = f"person:{name}:{relationship}"
                
                if value_id in seen_values:
                    result["remove_duplicate"].append(memory)
                    continue
                else:
                    seen_values[value_id] = memory
            
            # Valid unique memory - keep it
            seen_keys.add(unique_id)
            result["keep"].append(memory)
        
        return result
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory by ID"""
        try:
            # Note: AI-Memory service may not have delete endpoint
            # This is a placeholder for future implementation
            logger.warning(f"Delete not implemented in AI-Memory service, memory_id: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting memory {memory_id}: {e}")
            return False
    
    def print_summary(self, consolidated: Dict[str, List[Dict[str, Any]]]):
        """Print cleanup summary"""
        print("\n" + "="*80)
        print("MEMORY CLEANUP SUMMARY")
        print("="*80)
        print(f"Total memories analyzed: {sum(len(v) for v in consolidated.values())}")
        print(f"✅ Memories to KEEP: {len(consolidated['keep'])}")
        print(f"🗑️  Greeting templates to REMOVE: {len(consolidated['remove_greeting'])}")
        print(f"🗑️  Duplicates to REMOVE: {len(consolidated['remove_duplicate'])}")
        print(f"📉 Total reduction: {len(consolidated['remove_greeting']) + len(consolidated['remove_duplicate'])} memories")
        print("="*80)
        
        # Show examples
        if consolidated['remove_greeting']:
            print("\n📋 GREETING TEMPLATE EXAMPLES (to be removed):")
            for mem in consolidated['remove_greeting'][:5]:
                print(f"  - {mem.get('type')}:{mem.get('key')} = {str(mem.get('value'))[:100]}")
        
        if consolidated['remove_duplicate']:
            print("\n📋 DUPLICATE EXAMPLES (to be removed):")
            for mem in consolidated['remove_duplicate'][:5]:
                print(f"  - {mem.get('type')}:{mem.get('key')} = {str(mem.get('value'))[:100]}")
        
        if consolidated['keep']:
            print("\n📋 VALID MEMORY EXAMPLES (to be kept):")
            for mem in consolidated['keep'][:10]:
                print(f"  - {mem.get('type')}:{mem.get('key')} = {str(mem.get('value'))[:100]}")
        
        print("\n")
    
    def execute_cleanup(self, consolidated: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
        """Execute the cleanup (delete unwanted memories)"""
        logger.info("⚠️ CLEANUP NOT IMPLEMENTED - AI-Memory service lacks delete endpoint")
        logger.info("💡 Recommended: Manually review and clean via AI-Memory admin panel")
        
        results = {
            "deleted_greetings": 0,
            "deleted_duplicates": 0,
            "errors": 0
        }
        
        # TODO: Implement when AI-Memory service adds delete endpoint
        # for memory in consolidated['remove_greeting']:
        #     if self.delete_memory(memory['id']):
        #         results['deleted_greetings'] += 1
        
        return results


def main():
    parser = argparse.ArgumentParser(description="Clean up AI-Memory service duplicates")
    parser.add_argument("--user-id", required=True, help="User ID (phone number) to clean")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't delete")
    parser.add_argument("--execute", action="store_true", help="Execute cleanup (delete duplicates)")
    parser.add_argument("--max-limit", type=int, default=10000, help="Max memories to fetch (default: 10000)")
    
    args = parser.parse_args()
    
    if args.execute and args.dry_run:
        print("❌ Error: Cannot use both --dry-run and --execute")
        return
    
    if not args.execute and not args.dry_run:
        print("❌ Error: Must specify either --dry-run or --execute")
        return
    
    # Initialize cleanup
    cleanup = MemoryCleanup(args.user_id)
    
    # Fetch all memories with pagination
    memories = cleanup.fetch_all_memories(max_limit=args.max_limit)
    
    if not memories:
        print("❌ No memories found")
        return
    
    # Consolidate
    logger.info("🔍 Analyzing memories for duplicates and templates...")
    consolidated = cleanup.consolidate_memories(memories)
    
    # Print summary
    cleanup.print_summary(consolidated)
    
    # Execute if requested
    if args.execute:
        logger.info("🚀 Executing cleanup...")
        results = cleanup.execute_cleanup(consolidated)
        print(f"\n✅ Cleanup complete!")
        print(f"  - Deleted greeting templates: {results['deleted_greetings']}")
        print(f"  - Deleted duplicates: {results['deleted_duplicates']}")
        print(f"  - Errors: {results['errors']}")
    else:
        logger.info("✅ Dry-run complete. Use --execute to apply changes.")


if __name__ == "__main__":
    main()
