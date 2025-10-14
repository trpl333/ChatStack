"""
Notion Client for Peterson Insurance AI Phone System

This module provides Python interface to the Notion API server,
allowing the phone system to sync call data to Notion databases.
"""

import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Notion API server endpoint
NOTION_API_URL = "http://localhost:8200"

class NotionClient:
    """Client for interacting with Notion sync service"""
    
    def __init__(self, base_url: str = NOTION_API_URL):
        self.base_url = base_url
        
    def upsert_customer(
        self, 
        phone: str, 
        name: Optional[str] = None,
        email: Optional[str] = None,
        spouse: Optional[str] = None
    ) -> Optional[str]:
        """
        Create or update customer in Notion
        
        Args:
            phone: Customer phone number
            name: Customer name
            email: Customer email
            spouse: Spouse name
            
        Returns:
            Notion customer page ID
        """
        try:
            response = requests.post(
                f"{self.base_url}/notion/customer",
                json={
                    "phone": phone,
                    "name": name,
                    "email": email,
                    "spouse": spouse
                },
                timeout=5
            )
            
            if response.ok:
                data = response.json()
                logger.info(f"✅ Customer {name} synced to Notion: {data.get('customer_id')}")
                return data.get('customer_id')
            else:
                logger.error(f"Failed to upsert customer: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling Notion API: {e}")
            return None
    
    def log_call(
        self,
        phone: str,
        transcript: str,
        summary: str,
        transfer_to: Optional[str] = None
    ) -> bool:
        """
        Log call to Notion
        
        Args:
            phone: Customer phone number
            transcript: Full conversation transcript
            summary: AI-generated summary
            transfer_to: Person/department call was transferred to
            
        Returns:
            Success status
        """
        try:
            response = requests.post(
                f"{self.base_url}/notion/call-log",
                json={
                    "phone": phone,
                    "transcript": transcript,
                    "summary": summary,
                    "transfer_to": transfer_to
                },
                timeout=5
            )
            
            if response.ok:
                logger.info(f"✅ Call logged to Notion for {phone}")
                return True
            else:
                logger.error(f"Failed to log call: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error calling Notion API: {e}")
            return False
    
    def sync_to_memory(self, customer_id: str) -> bool:
        """
        Sync customer data from Notion to AI-Memory
        
        Args:
            customer_id: Notion customer page ID
            
        Returns:
            Success status
        """
        try:
            response = requests.post(
                f"{self.base_url}/notion/sync-to-memory",
                json={"customer_id": customer_id},
                timeout=5
            )
            
            if response.ok:
                logger.info(f"✅ Customer {customer_id} synced to AI-Memory")
                return True
            else:
                logger.error(f"Failed to sync to memory: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error calling Notion API: {e}")
            return False
    
    def get_databases(self) -> Optional[Dict[str, str]]:
        """
        Get all Notion database IDs
        
        Returns:
            Dictionary of database names to IDs
        """
        try:
            response = requests.get(f"{self.base_url}/notion/databases", timeout=5)
            
            if response.ok:
                data = response.json()
                return data.get('databases', {})
            else:
                logger.error(f"Failed to get databases: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling Notion API: {e}")
            return None
    
    def health_check(self) -> bool:
        """
        Check if Notion service is healthy
        
        Returns:
            True if service is ready
        """
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.ok and response.json().get('status') == 'ok'
        except:
            return False


# Global instance
notion_client = NotionClient()
