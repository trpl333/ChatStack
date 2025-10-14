"""
Initialize Customer Management Database Tables
Run this script to create customer, configuration, and usage tables
"""
import os
from sqlalchemy import create_engine
from customer_models import Base, Customer, CustomerConfiguration, CustomerUsage

def init_customer_database():
    """Create all customer management tables"""
    try:
        # Get database URL from environment
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            print("❌ DATABASE_URL not found in environment")
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
