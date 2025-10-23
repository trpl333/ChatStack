#!/usr/bin/env python3
"""
Script to fix AI-Memory API endpoint calls from old format to new format.

Old endpoints (404 errors):
- POST /memory/store
- POST /memory/retrieve

New endpoints (correct):
- POST /v1/memories (store)
- GET /v1/memories (retrieve)
"""

import re

def fix_main_py():
    """Fix main.py endpoint calls"""
    with open('main.py', 'r') as f:
        content = f.read()
    
    # Count replacements
    store_count = content.count('/memory/store')
    retrieve_count = content.count('/memory/retrieve')
    
    print(f"Found {store_count} /memory/store calls and {retrieve_count} /memory/retrieve calls in main.py")
    
    # Replace store endpoints
    content = content.replace('f"{ai_memory_url}/memory/store"', 'f"{ai_memory_url}/v1/memories"')
    
    # Replace retrieve endpoints - these need more careful handling
    # Pattern 1: Simple POST requests
    content = re.sub(
        r'requests\.post\(\s*f"\{ai_memory_url\}/memory/retrieve"',
        r'requests.get(f"{ai_memory_url}/v1/memories"',
        content
    )
    
    # Pattern 2: Change json= to params= for GET requests
    content = re.sub(
        r'(requests\.get\([^)]+v1/memories[^)]+),\s*json=(\{[^}]+\})',
        r'\1, params=\2',
        content
    )
    
    with open('main.py', 'w') as f:
        f.write(content)
    
    print("✅ Fixed main.py")

if __name__ == "__main__":
    fix_main_py()
    print("\n✅ All endpoint fixes complete!")
    print("\nNext: Restart the application with ./update.sh on DigitalOcean")
