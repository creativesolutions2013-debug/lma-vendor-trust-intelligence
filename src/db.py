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
    assessments = relationship("Assessment", back_populates="vendor", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="vendor", cascade="all, delete-orphan")

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

class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    assessment_type = Column(String(120), nullable=False)
    assessment_reason = Column(String(120), default="New vendor")
    status = Column(String(50), default="Not Started")
    assigned_to = Column(String(255))
    due_date = Column(String(40))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    risk_score = Column(Float, default=0)
    approval_status = Column(String(80), default="Pending")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="assessments")
    evidence = relationship("Evidence", back_populates="assessment")

class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    assessment_id = Column(Integer, ForeignKey("assessments.id"))
    document_type = Column(String(120), nullable=False)
    document_name = Column(String(255), nullable=False)
    document_date = Column(String(40))
    coverage_start = Column(String(40))
    coverage_end = Column(String(40))
    expiration_date = Column(String(40))
    issuer = Column(String(255))
    opinion = Column(String(120))
    exceptions_count = Column(Integer, default=0)
    status = Column(String(80), default="Received")
    storage_path = Column(String(500))
    analyst_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="evidence")
    assessment = relationship("Assessment", back_populates="evidence")

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

