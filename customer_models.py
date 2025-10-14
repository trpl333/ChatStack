"""
Customer Management Database Models
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Customer(Base):
    """Customer account model"""
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    business_name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=False)
    phone = Column(String(50))
    
    # Package/subscription info
    package_tier = Column(String(50))  # starter, professional, enterprise
    status = Column(String(50), default='active')  # active, suspended, cancelled
    
    # AI Configuration
    agent_name = Column(String(100), default='AI Assistant')
    openai_voice = Column(String(50), default='alloy')
    greeting_template = Column(Text)
    personality_sliders = Column(JSON)  # Store 30-slider config as JSON
    
    # Twilio/Phone config
    twilio_phone_number = Column(String(50))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    configurations = relationship("CustomerConfiguration", back_populates="customer", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'business_name': self.business_name,
            'contact_name': self.contact_name,
            'phone': self.phone,
            'package_tier': self.package_tier,
            'status': self.status,
            'agent_name': self.agent_name,
            'openai_voice': self.openai_voice,
            'greeting_template': self.greeting_template,
            'personality_sliders': self.personality_sliders,
            'twilio_phone_number': self.twilio_phone_number,
            'created_at': self.created_at.isoformat() if self.created_at is not None else None
        }

class CustomerConfiguration(Base):
    """Customer-specific AI configuration history"""
    __tablename__ = 'customer_configurations'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    
    # Configuration type
    config_type = Column(String(100))  # greeting, voice, personality, system_prompt
    config_key = Column(String(100))
    config_value = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), default='customer')
    
    # Relationships
    customer = relationship("Customer", back_populates="configurations")
    
    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'config_type': self.config_type,
            'config_key': self.config_key,
            'config_value': self.config_value,
            'created_at': self.created_at.isoformat() if self.created_at is not None else None,
            'created_by': self.created_by
        }

class CustomerUsage(Base):
    """Track customer usage and call metrics"""
    __tablename__ = 'customer_usage'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    
    # Usage metrics
    total_calls = Column(Integer, default=0)
    total_minutes = Column(Integer, default=0)
    month = Column(String(7))  # Format: YYYY-MM
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
