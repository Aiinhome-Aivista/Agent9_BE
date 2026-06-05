from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, Enum, JSON,
    ForeignKey, func, Index
)
from sqlalchemy.orm import relationship
from .database import Base
import uuid
from sqlalchemy import Column, Integer, String, JSON, DECIMAL, TIMESTAMP
from sqlalchemy.sql import func


def gen_uuid():
    return str(uuid.uuid4())


class DataSource(Base):
    __tablename__ = "data_sources"

    id          = Column(String(36), primary_key=True, default=gen_uuid)
    source_type = Column(Enum("csv", "mysql_crm", "zoho_crm"), nullable=False)
    name        = Column(String(255), nullable=False)
    filename    = Column(String(255))
    record_count = Column(Integer, default=0)
    field_map   = Column(JSON)
    status      = Column(Enum("pending", "processing", "ingested", "error"), default="pending")
    error_msg   = Column(Text)
    ingested_at = Column(DateTime, server_default=func.now())

    prospects   = relationship("ProspectAudience", back_populates="source")


class ProspectAudience(Base):
    __tablename__ = "prospect_audience"

    id                  = Column(String(36), primary_key=True, default=gen_uuid)
    source_id           = Column(String(36), ForeignKey("data_sources.id"), nullable=True)
    name                = Column(String(255), nullable=False)
    email               = Column(String(255))
    phone               = Column(String(30))
    age                 = Column(Integer)
    location            = Column(String(255))
    income_bracket      = Column(String(100))
    occupation          = Column(String(255))
    existing_policies   = Column(JSON)
    behavioral_signals  = Column(JSON)
    life_events         = Column(JSON)
    propensity_score    = Column(Float, default=0.0)
    recommended_product = Column(String(255))
    priority_type       = Column(
        Enum("new_policy", "renewal", "cross_sell"), default="new_policy"
    )
    outreach_channel    = Column(String(100))
    urgency_level       = Column(
        Enum("Critical", "High", "Medium", "Low"), default="Medium"
    )
    ai_context          = Column(Text)
    crm_reference_id    = Column(String(255))
    is_contacted        = Column(Boolean, default=False)
    created_at          = Column(DateTime, server_default=func.now())
    updated_at          = Column(DateTime, server_default=func.now(), onupdate=func.now())

    source  = relationship("DataSource", back_populates="prospects")
    renewal = relationship("Renewal", back_populates="prospect", uselist=False)

    __table_args__ = (
        Index("idx_score",   propensity_score.desc()),
        Index("idx_priority", priority_type),
        Index("idx_urgency",  urgency_level),
    )


class Policy(Base):
    __tablename__ = "policies"

    id                 = Column(String(36), primary_key=True, default=gen_uuid)
    name               = Column(String(255), nullable=False)
    policy_type        = Column(
        Enum("Life", "Health", "Motor", "Property", "Commercial", "Travel"), nullable=False
    )
    coverage_range     = Column(String(100))
    premium_range      = Column(String(100))
    eligibility        = Column(String(255))
    features           = Column(JSON)
    propensity_targets = Column(JSON)
    document_path      = Column(String(500))
    is_indexed         = Column(Boolean, default=False)
    chroma_collection  = Column(String(100), default="policy_documents")
    arango_vertex_id   = Column(String(100))
    doc_count          = Column(Integer, default=0)
    embedding_model    = Column(String(100))
    created_at         = Column(DateTime, server_default=func.now())
    updated_at         = Column(DateTime, server_default=func.now(), onupdate=func.now())

    renewals = relationship("Renewal", back_populates="policy")


class Renewal(Base):
    __tablename__ = "renewals"

    id               = Column(String(36), primary_key=True, default=gen_uuid)
    prospect_id      = Column(String(36), ForeignKey("prospect_audience.id"), nullable=False)
    policy_id        = Column(String(36), ForeignKey("policies.id"), nullable=False)
    policy_name      = Column(String(255))
    expiry_date      = Column(String(10), nullable=False)   # stored as YYYY-MM-DD string
    days_to_expiry   = Column(Integer)
    retention_score  = Column(Float, default=0.0)
    churn_risk       = Column(Enum("High", "Medium", "Low"), default="Medium")
    renewal_action   = Column(String(255))
    renewal_status   = Column(
        Enum("pending", "contacted", "renewed", "lapsed"), default="pending"
    )
    created_at       = Column(DateTime, server_default=func.now())

    prospect = relationship("ProspectAudience", back_populates="renewal")
    policy   = relationship("Policy", back_populates="renewals")


class Campaign(Base):
    __tablename__ = "campaigns"

    id              = Column(String(36), primary_key=True, default=gen_uuid)
    name            = Column(String(255), nullable=False)
    description     = Column(Text)
    campaign_type   = Column(
        Enum("new_policy", "renewal", "cross_sell", "retention"), nullable=False
    )
    channel         = Column(String(100))
    status          = Column(
        Enum("draft", "scheduled", "active", "paused", "completed"), default="draft"
    )
    target_count    = Column(Integer, default=0)
    sent_count      = Column(Integer, default=0)
    opened_count    = Column(Integer, default=0)
    converted_count = Column(Integer, default=0)
    scheduled_at    = Column(DateTime)
    launched_at     = Column(DateTime)
    completed_at    = Column(DateTime)
    created_at      = Column(DateTime, server_default=func.now())


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(100), nullable=False)
    event_type = Column(
        Enum("info", "success", "warning", "error"), default="info"
    )
    message    = Column(Text, nullable=False)
    extra_metadata = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())






class Customer(Base):
    __tablename__ = "customer"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), nullable=False)

    email = Column(String(255), nullable=True)

    phone = Column(String(20), nullable=True)

    age = Column(Integer, nullable=True)

    location = Column(String(255), nullable=True)

    income_bracket = Column(String(100), nullable=True)

    occupation = Column(String(255), nullable=True)

    existing_policies = Column(JSON, nullable=True)

    behavioral_signals = Column(JSON, nullable=True)

    life_events = Column(JSON, nullable=True)

    propensity_score = Column(
        DECIMAL(10,2),
        default=0
    )

    created_at = Column(
        TIMESTAMP,
        server_default=func.now()
    )

    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )
    
class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(255), nullable=False)
    email      = Column(String(255), unique=True, nullable=False, index=True)
    username   = Column(String(255), unique=True, nullable=False)
    password   = Column(String(255), nullable=False)
    role       = Column(String(50), default="SALES_AGENT")
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())