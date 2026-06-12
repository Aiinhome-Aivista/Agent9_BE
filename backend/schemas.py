from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


# ── Enums ─────────────────────────────────────────────────
class PriorityType(str, Enum):
    new_policy = "new_policy"
    renewal    = "renewal"
    cross_sell = "cross_sell"

class UrgencyLevel(str, Enum):
    Critical = "Critical"
    High     = "High"
    Medium   = "Medium"
    Low      = "Low"

class PolicyType(str, Enum):
    Life       = "Life"
    Health     = "Health"
    Motor      = "Motor"
    Property   = "Property"
    Commercial = "Commercial"
    Travel     = "Travel"

class CampaignStatus(str, Enum):
    draft     = "draft"
    scheduled = "scheduled"
    active    = "active"
    paused    = "paused"
    completed = "completed"


# ── Connector ─────────────────────────────────────────────
class CSVAnalyzeRequest(BaseModel):
    csv_content: str = Field(..., description="Raw CSV text content")
    source_name: str = Field(default="upload.csv")

class CSVAnalyzeResponse(BaseModel):
    detected_fields:    list[str]
    mappings:           dict[str, str]
    missing_fields:     list[str]
    sample_prospects:   list[dict[str, Any]]
    record_count:       int
    ingestion_summary:  str

class MySQLCRMRequest(BaseModel):
    host:     str
    port:     int = 3306
    user:     str
    password: str
    database: str
    table_name: str = "customers"

class CRMConnectResponse(BaseModel):
    connected:    bool
    record_count: int
    tables:       list[str]
    message:      str


# ── Policy ────────────────────────────────────────────────
class PolicyCreate(BaseModel):
    name:               str
    policy_type:        PolicyType
    coverage_range:     Optional[str] = None
    premium_range:      Optional[str] = None
    eligibility:        Optional[str] = None
    features:           list[str] = []
    propensity_targets: list[str] = []

class PolicyResponse(BaseModel):
    id:                 str
    name:               str
    policy_type:        str
    coverage_range:     Optional[str]
    premium_range:      Optional[str]
    eligibility:        Optional[str]
    features:           list[str]
    propensity_targets: list[str]
    is_indexed:         bool
    doc_count:          int
    arango_vertex_id:   Optional[str]
    created_at:         datetime

    model_config = {"from_attributes": True}

class PolicyUploadResponse(BaseModel):
    filename:           str
    saved:              bool
    policy_id:          Optional[str] = None
    name:               Optional[str] = None
    policy_type:        Optional[str] = None
    coverage_range:     Optional[str] = None
    premium_range:      Optional[str] = None
    eligibility:        Optional[str] = None
    features:           list[str] = []
    propensity_targets: list[str] = []
    preview:            str
    relevance_score:    float
    is_relevant:        bool
    relevance_threshold: int = 75
    document_path:      Optional[str] = None

    model_config = {"from_attributes": True}

class KnowledgeGraphResponse(BaseModel):
    vertices: list[dict[str, Any]]
    edges:    list[dict[str, Any]]
    stats:    dict[str, Any]


# ── Prospects ─────────────────────────────────────────────
class ProspectResponse(BaseModel):
    id:                  str
    rank:                int
    name:                str
    age:                 Optional[int]
    location:            Optional[str]
    email:               Optional[str]
    income_bracket:      Optional[str]
    propensity_score:    float
    recommended_product: Optional[str]
    behavioral_signals:  list[str]
    outreach_channel:    Optional[str]
    urgency_level:       str
    ai_context:          Optional[str]
    source_name:         Optional[str]

    model_config = {"from_attributes": True}

class RenewalProspectResponse(BaseModel):
    id:              str
    rank:            int
    name:            str
    age:             Optional[int]
    location:        Optional[str]
    email:           Optional[str]
    policy_name:     str
    days_to_expiry:  int
    retention_score: float
    churn_risk:      str
    renewal_action:  Optional[str]
    urgency_level:   str
    signals:         list[str]
    recommendation:  Optional[str]
    ai_context:      Optional[str]

class ProspectAnalysisRequest(BaseModel):
    prospect_id: str
    analysis_type: str = "full"   # full | pitch | risk | objections

class ProspectAnalysisResponse(BaseModel):
    prospect_id:   str
    analysis:      str
    key_insights:  list[str]
    talking_points: list[str]
    risk_factors:  list[str]
    next_action:   str
    best_time:     str
    generated_at:  datetime


# ── Campaigns ─────────────────────────────────────────────
class CampaignCreate(BaseModel):
    name:          str
    description:   Optional[str] = None
    campaign_type: str
    channel:       str
    prospect_ids:  list[str] = []
    scheduled_at:  Optional[datetime] = None

class PolicyCampaignCreate(BaseModel):
    policy_id:     str
    name:          Optional[str] = None
    description:   Optional[str] = None
    campaign_type: Optional[str] = "cross_sell"
    channel:       Optional[str] = "email"


class CampaignResponse(BaseModel):
    id:              str
    name:            str
    campaign_type:   str
    channel:         str
    status:          str
    target_count:    int
    sent_count:      int
    opened_count:    int
    converted_count: int
    launched_at:     Optional[datetime]
    created_at:      datetime

    model_config = {"from_attributes": True}


# ── Agent Logs ────────────────────────────────────────────
class LogResponse(BaseModel):
    id:         int
    agent_name: str
    event_type: str
    message:    str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────
class DashboardMetrics(BaseModel):
    total_prospects:     int
    new_policy_count:    int
    renewal_count:       int
    policies_indexed:    int
    avg_propensity:      float
    critical_renewals:   int
    active_campaigns:    int
    conversion_rate:     float

