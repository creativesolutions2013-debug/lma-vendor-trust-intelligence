from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///vendor_trust.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    legal_name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    website = Column(String(255))
    primary_domain = Column(String(255))
    industry = Column(String(120))
    headquarters_country = Column(String(120))
    relationship_status = Column(String(50), default="Prospective")
    criticality = Column(String(50), default="Moderate")
    inherent_risk_score = Column(Float, default=0)
    residual_risk_score = Column(Float, default=0)
    external_risk_score = Column(Float, default=0)
    control_effectiveness = Column(Float, default=50)
    overall_risk_rating = Column(String(50), default="Moderate")
    security_rating = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    engagements = relationship("Engagement", back_populates="vendor", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="vendor", cascade="all, delete-orphan")
    events = relationship("MonitoringEvent", back_populates="vendor", cascade="all, delete-orphan")

class Engagement(Base):
    __tablename__ = "engagements"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    service_name = Column(String(255), nullable=False)
    service_description = Column(Text)
    business_owner = Column(String(255))
    department = Column(String(120))
    business_criticality = Column(String(50))
    data_classification = Column(String(80))
    production_access = Column(Boolean, default=False)
    network_access = Column(Boolean, default=False)
    privileged_access = Column(Boolean, default=False)
    ai_enabled = Column(Boolean, default=False)
    status = Column(String(50), default="Active")

    vendor = relationship("Vendor", back_populates="engagements")

class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    source = Column(String(80), default="Assessment")
    severity = Column(String(40), default="Moderate")
    status = Column(String(50), default="Open")
    owner = Column(String(255))
    target_date = Column(String(40))
    created_at = Column(DateTime, default=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="findings")

class MonitoringEvent(Base):
    __tablename__ = "monitoring_events"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    event_type = Column(String(120), nullable=False)
    severity = Column(String(40), default="Moderate")
    description = Column(Text)
    previous_value = Column(String(120))
    new_value = Column(String(120))
    requires_review = Column(Boolean, default=True)
    status = Column(String(50), default="Open")
    event_date = Column(DateTime, default=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="events")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()
