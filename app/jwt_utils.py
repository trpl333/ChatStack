"""
JWT Token Generation for Multi-Tenant Authentication
Chad (ChatStack) uses this to generate tokens for Alice (AI-Memory) API calls
"""
import os
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# JWT Secret Key (shared with Alice)
# This must match the JWT_SECRET_KEY in Alice's environment
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 1  # Tokens expire after 1 hour

def generate_memory_token(customer_id: int, scope: str = "memory:read:write") -> str:
    """
    Generate JWT token for Alice (AI-Memory) API authentication
    
    Args:
        customer_id: Tenant identifier (from customers table)
        scope: Permission scope (default: full memory access)
    
    Returns:
        JWT token string
        
    Example:
        token = generate_memory_token(customer_id=1)
        headers = {"Authorization": f"Bearer {token}"}
    """
    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY environment variable not set!")
    
    payload = {
        "customer_id": customer_id,
        "scope": scope,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.info(f"✅ Generated JWT token for customer_id={customer_id}, scope={scope}")
    
    return token

def verify_token(token: str) -> Optional[dict]:
    """
    Verify JWT token (for testing purposes - Alice handles validation in production)
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload if valid, None if invalid
    """
    if not JWT_SECRET_KEY:
        logger.error("JWT_SECRET_KEY not set")
        return None
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        logger.info(f"✅ Token verified: customer_id={payload.get('customer_id')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.error("❌ Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid token: {e}")
        return None
