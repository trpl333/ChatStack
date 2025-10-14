"""
Initialize Customer Management Database Tables
Run this script to create customer, configuration, and usage tables
"""
import sys
import os
# Add current directory to path so we can import config_loader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from customer_models import Base, Customer, CustomerConfiguration, CustomerUsage
from config_loader import get_secret

def init_customer_database():
    """Create all customer management tables"""
    try:
        # Get database URL from config (same way Flask app does)
        database_url = get_secret('DATABASE_URL')
        
        if not database_url:
            print("❌ DATABASE_URL not found in environment or config")
            return False
        
        print(f"🔗 Connecting to database...")
        engine = create_engine(database_url)
        
        print("📊 Creating customer management tables...")
        Base.metadata.create_all(engine)
        
        print("✅ Customer database tables created successfully!")
        print("\nCreated tables:")
        print("  - customers")
        print("  - customer_configurations")
        print("  - customer_usage")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize customer database: {e}")
        return False

if __name__ == "__main__":
    init_customer_database()
