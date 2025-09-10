import os
import requests
import logging
from typing import List, Dict, Any, Tuple
from config_loader import get_llm_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _get_llm_config():
    """Get LLM configuration dynamically for hot reload support"""
    return get_llm_config()

def _get_headers():
    """Get request headers dynamically for hot reload support"""
    config = _get_llm_config()
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"
    return headers

def chat(messages: List[Dict[str, str]], temperature: float = 0.6, top_p: float = 0.9, max_tokens: int = 800) -> Tuple[str, Dict[str, Any]]:
    """
    Call the LLM endpoint with the provided messages and parameters.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        temperature: Sampling temperature (0.0 to 2.0)
        top_p: Top-p sampling parameter (0.0 to 1.0)
        max_tokens: Maximum tokens to generate
        
    Returns:
        Tuple of (response_content, usage_stats)
    """
    # Get current configuration
    config = _get_llm_config()
    base_url = config["base_url"]
    model = config["model"]
    headers = _get_headers()
    
    # Check if using mock endpoint for development
    if base_url == "http://localhost:8000":
        return _mock_llm_response(messages, temperature, top_p, max_tokens)
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens
    }
    
    try:
        logger.info(f"Calling LLM with {len(messages)} messages, temp={temperature}, top_p={top_p}")
        
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=120  # Increased timeout for longer responses
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Extract response content and usage stats
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        logger.info(f"LLM response received: {usage.get('total_tokens', 0)} total tokens")
        
        return content, usage
        
    except requests.exceptions.Timeout:
        logger.error("LLM request timeout")
        raise Exception("LLM request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        logger.error(f"Failed to connect to LLM at {base_url}")
        raise Exception("Failed to connect to LLM service. Please check configuration.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"LLM HTTP error: {e}")
        raise Exception(f"LLM service error: {e}")
    except KeyError as e:
        logger.error(f"Unexpected LLM response format: {e}")
        raise Exception("Unexpected response format from LLM service.")
    except Exception as e:
        logger.error(f"Unexpected error calling LLM: {e}")
        raise Exception(f"LLM service error: {str(e)}")

def _mock_llm_response(messages: List[Dict[str, str]], temperature: float, top_p: float, max_tokens: int) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a mock LLM response for development/testing.
    """
    logger.info(f"Using mock LLM response for {len(messages)} messages")
    
    # Get the last user message
    user_message = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_message = msg["content"]
            break
    
    # Generate a simple contextual response
    if "hello" in user_message.lower() or "hi" in user_message.lower():
        response = "Hello! I'm Sam, your AI assistant. I'm running in development mode right now. How can I help you today?"
    elif "weather" in user_message.lower():
        response = "I'd love to help with weather information, but I'm currently running in mock mode. In a real deployment, I would call a weather API to get current conditions."
    elif "tool" in user_message.lower() or "book" in user_message.lower():
        response = "I can help with tool calls! Try asking me to book a meeting or send a message. I'll demonstrate the tool calling functionality."
    elif "remember" in user_message.lower():
        response = "I'll remember that information! My memory system is working and will store important details from our conversation for future reference."
    else:
        response = f"I understand you're asking about: '{user_message[:100]}...' I'm currently running in development mode with a mock LLM. In production, I would provide a more detailed and helpful response using a real language model."
    
    # Mock usage statistics
    usage = {
        "prompt_tokens": sum(len(msg["content"].split()) for msg in messages),
        "completion_tokens": len(response.split()),
        "total_tokens": sum(len(msg["content"].split()) for msg in messages) + len(response.split())
    }
    
    return response, usage

def validate_llm_connection() -> bool:
    """
    Validate that the LLM service is accessible.
    
    Returns:
        True if connection is valid, False otherwise
    """
    try:
        test_messages = [{"role": "user", "content": "Hello"}]
        chat(test_messages, max_tokens=10)
        logger.info("LLM connection validation successful")
        return True
    except Exception as e:
        logger.error(f"LLM connection validation failed: {e}")
        return False
