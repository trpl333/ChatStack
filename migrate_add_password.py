#!/usr/bin/env python3
"""
Database Migration: Add password_hash column to customers table
Run this on the DigitalOcean server to add password authentication
"""
import os
from sqlalchemy import create_engine, text
from config_loader import get_secret

def migrate():
    """Add password_hash column to customers table"""
    
    # Get database URL
    database_url = get_secret("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return False
    
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='password_hash'
            """))
            
            if result.fetchone():
                print("✅ password_hash column already exists")
                return True
            
            # Add password_hash column
            print("🔧 Adding password_hash column to customers table...")
            conn.execute(text("""
                ALTER TABLE customers 
                ADD COLUMN password_hash VARCHAR(256)
            """))
            conn.commit()
            
            print("✅ Migration complete! password_hash column added")
            print("\n⚠️  IMPORTANT:")
            print("   - Existing customers do not have passwords set")
            print("   - They will need to contact support or use password reset")
            print("   - New customers must set password during onboarding")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    print("=" * 60)
    print("Database Migration: Add password_hash to customers")
    print("=" * 60)
    
    success = migrate()
    
    if success:
        print("\n✅ Migration successful!")
    else:
        print("\n❌ Migration failed!")
    
    print("=" * 60)
