"""
Centralized Configuration Loader for NeuroSphere Orchestrator
Reads from both config.json (GitHub-synced) and environment variables (secure)
"""
import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self._config_cache = None
        self._last_modified = 0
        
    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file with hot reload support"""
        try:
            # Check if file was modified for hot reload
            if os.path.exists(self.config_file):
                modified_time = os.path.getmtime(self.config_file)
                if modified_time > self._last_modified:
                    with open(self.config_file, 'r') as f:
                        self._config_cache = json.load(f)
                        self._last_modified = modified_time
                        logger.info(f"✅ Configuration reloaded from {self.config_file}")
                        
            return self._config_cache or {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"⚠️ Could not load {self.config_file}: {e}")
            return {}
    
    def get(self, key: str, default: Any = None, fallback_env: Optional[str] = None) -> Any:
        """
        Get configuration value with priority:
        1. Environment variable (for secrets)
        2. config.json file (for settings)
        3. Default value
        """
        # Priority 1: Environment variable (secrets)
        env_value = os.environ.get(key.upper())
        if env_value is not None:
            return env_value
            
        # Check fallback environment variable name if provided
        if fallback_env:
            fallback_value = os.environ.get(fallback_env)
            if fallback_value is not None:
                return fallback_value
        
        # Priority 2: config.json file (settings)
        config = self._load_config_file()
        if key.lower() in config:
            return config[key.lower()]
            
        # Priority 3: Default value
        return default
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get complete configuration for debugging/admin interface"""
        config = self._load_config_file()
        
        # Add environment variables (but mask secrets)
        sensitive_keys = ['api_key', 'token', 'secret', 'password', 'auth', 'sid', 'database_url', 'db_', 'connection', 'dsn']
        
        result = {}
        for key, value in config.items():
            result[key] = value
            
        # Add environment variables that aren't in config.json
        for env_key in os.environ:
            lower_key = env_key.lower()
            if lower_key not in result:
                # Mask sensitive values
                is_sensitive = any(sensitive in lower_key for sensitive in sensitive_keys)
                result[lower_key] = "***MASKED***" if is_sensitive else os.environ[env_key]
                
        return result
    
    def reload(self):
        """Force reload configuration from file"""
        self._last_modified = 0
        return self._load_config_file()

# Global configuration loader instance
config = ConfigLoader()

# Convenience functions for common usage patterns
def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get secret from environment variables with fallback"""
    return config.get(key, default)

def get_setting(key: str, default: Any = None) -> Any:
    """Get setting from config.json with environment variable override"""
    return config.get(key, default)

def get_database_url() -> str:
    """Get database URL from environment"""
    return config.get("DATABASE_URL", fallback_env="PGHOST", default="")

def get_llm_config() -> Dict[str, str]:
    """Get LLM configuration"""
    return {
        "base_url": config.get("LLM_BASE_URL", default="http://localhost:8001"),
        "model": config.get("LLM_MODEL", default="mistralai/Mistral-7B-Instruct-v0.1"),
        "api_key": config.get("LLM_API_KEY", default="")
    }

def get_twilio_config() -> Dict[str, str]:
    """Get Twilio configuration"""
    return {
        "account_sid": config.get("TWILIO_ACCOUNT_SID", default=""),
        "auth_token": config.get("TWILIO_AUTH_TOKEN", default=""),
        "phone_number": config.get("TWILIO_PHONE_NUMBER", default="+19497071290")
    }

def get_elevenlabs_config() -> Dict[str, str]:
    """Get ElevenLabs configuration"""
    return {
        "api_key": config.get("ELEVENLABS_API_KEY", default=""),
        "voice_id": config.get("ELEVENLABS_VOICE_ID", default="dnRitNTYKgyEUEizTqqH")
    }