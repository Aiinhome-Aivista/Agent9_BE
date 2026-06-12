"""
ARIES FastAPI Routers — All Agent Endpoints
============================================
connector_router  /api/connector  — CSV ingest, CRM connect
policy_router     /api/policy     — Policy upload, index, knowledge graph
prospect_router   /api/prospects  — Ranked new prospects + renewals
campaign_router   /api/campaigns  — Campaign CRUD + launch
log_router        /api/logs       — Agent activity logs
"""

import importlib
import os
import io
import csv
import uuid
import logging
from datetime import datetime, timedelta, date
from typing import Any

import pandas as pd
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse, Response, RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc

from backend.database import get_db, AsyncSessionLocal

from backend.models import (
    DataSource,
    ProspectAudience,
    Policy,
    Renewal,
    Campaign,
    AgentLog,
    Customer,
)

from backend.schemas import (
    CSVAnalyzeRequest,
    CSVAnalyzeResponse,
    MySQLCRMRequest,
    CRMConnectResponse,
    PolicyCreate,
    PolicyResponse,
    PolicyUploadResponse,
    KnowledgeGraphResponse,
    ProspectResponse,
    RenewalProspectResponse,
    ProspectAnalysisRequest,
    ProspectAnalysisResponse,
    CampaignCreate,
    PolicyCampaignCreate,
    CampaignResponse,
    LogResponse,
    DashboardMetrics,
)

from backend import mistral_client as llm
from backend import chroma_client as chroma
from backend import arango_client as arango
from backend import email_service

from backend.config import get_settings

logger   = logging.getLogger("aries.routers")
settings = get_settings()


async def _log(db: AsyncSession, agent: str, msg: str, etype: str = "info") -> None:
    entry = AgentLog(agent_name=agent, event_type=etype, message=msg)
    db.add(entry)
    await db.flush()


# ════════════════════════════════════════════════════════════
#  DASHBOARD
# ════════════════════════════════════════════════════════════
dashboard_router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@dashboard_router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    total   = await db.scalar(select(func.count(ProspectAudience.id)))
    new_cnt = await db.scalar(select(func.count(ProspectAudience.id)).where(ProspectAudience.priority_type == "new_policy"))
    ren_cnt = await db.scalar(select(func.count(ProspectAudience.id)).where(ProspectAudience.priority_type == "renewal"))
    idx_cnt = await db.scalar(select(func.count(Policy.id)).where(Policy.is_indexed == True))
    avg_p   = await db.scalar(select(func.avg(ProspectAudience.propensity_score)))
    crit    = await db.scalar(select(func.count(Renewal.id)).where(Renewal.churn_risk == "High"))
    active  = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status == "active"))
    total_conv = await db.scalar(select(func.sum(Campaign.converted_count))) or 0
    total_sent = await db.scalar(select(func.sum(Campaign.sent_count)))     or 1

    return DashboardMetrics(
        total_prospects   = total   or 0,
        new_policy_count  = new_cnt or 0,
        renewal_count     = ren_cnt or 0,
        policies_indexed  = idx_cnt or 0,
        avg_propensity    = round(float(avg_p or 0), 1),
        critical_renewals = crit   or 0,
        active_campaigns  = active or 0,
        conversion_rate   = round(total_conv / total_sent * 100, 1),
    )


# ════════════════════════════════════════════════════════════
#  CONNECTOR AGENT
# ════════════════════════════════════════════════════════════
connector_router = APIRouter(prefix="/api/connector", tags=["Connector Agent"])

@connector_router.post("/csv/analyze", response_model=CSVAnalyzeResponse)
async def analyze_csv(req: CSVAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """Analyze CSV content with Mistral — return field mappings & sample prospects."""
    await _log(db, "Connector", f"CSV analysis started: {req.source_name}")
    try:
        result = await llm.analyze_csv(req.csv_content, req.source_name)
        await _log(db, "Connector",
                   f"CSV analyzed: {result.get('record_count',0)} records, "
                   f"{len(result.get('mappings',{}))} fields mapped", "success")
        return CSVAnalyzeResponse(**result)
    except Exception as exc:
        await _log(db, "Connector", f"CSV analysis error: {exc}", "error")
        raise HTTPException(status_code=500, detail=str(exc))


# @connector_router.post("/csv/ingest")
# async def ingest_csv(
#     file: UploadFile = File(...),
#     bg:   BackgroundTasks = BackgroundTasks(),
#     db:   AsyncSession    = Depends(get_db),
# ):
#     """Upload a CSV file, parse intelligently, persist to prospect_audience table."""
#     content = await file.read()
#     try:
#         df = pd.read_csv(io.BytesIO(content))
#     except Exception as exc:
#         raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

#     source = DataSource(
#         source_type  = "csv",
#         name         = file.filename,
#         filename     = file.filename,
#         record_count = len(df),
#         status       = "processing",
#     )
#     db.add(source)
#     await db.flush()

#     # Analyze field mappings via LLM
#     raw_csv = df.head(20).to_csv(index=False)
#     try:
#         mapping_result = await llm.analyze_csv(raw_csv, file.filename)
#         source.field_map = mapping_result.get("mappings", {})
#     except Exception:
#         source.field_map = {}

#     mappings: dict = source.field_map or {}
#     reverse  = {v: k for k, v in mappings.items()}

#     def col(standard_name: str) -> str | None:
#         return reverse.get(standard_name)

#     rows_added = 0
#     for _, row in df.iterrows():
#         p = ProspectAudience(
#             source_id       = source.id,
#             name            = str(row.get(col("name") or "name", "Unknown")),
#             email           = str(row.get(col("email") or "email", "")),
#             phone           = str(row.get(col("phone") or "phone", "")),
#             age             = _safe_int(row.get(col("age") or "age")),
#             location        = str(row.get(col("location") or "location", "")),
#             income_bracket  = str(row.get(col("income_bracket") or "income", "")),
#             occupation      = str(row.get(col("occupation") or "occupation", "")),
#             behavioral_signals = [],
#             priority_type   = "new_policy",
#         )
#         db.add(p)
#         rows_added += 1

#     source.record_count = rows_added
#     source.status       = "ingested"
#     await db.flush()

#     await _log(db, "Connector",
#                f"CSV ingested: {file.filename} → {rows_added} prospects", "success")
#     return {"source_id": source.id, "records_ingested": rows_added,
#             "filename": file.filename, "field_map": source.field_map}


@connector_router.post("/csv/ingest")
async def ingest_csv(
    file: UploadFile = File(...),
    bg: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """Upload CSV and persist to ProspectAudience + Customer"""

    content = await file.read()

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse CSV: {exc}"
        )

    source = DataSource(
        source_type="csv",
        name=file.filename,
        filename=file.filename,
        record_count=len(df),
        status="processing",
    )

    db.add(source)
    await db.flush()

    raw_csv = df.head(20).to_csv(index=False)

    try:
        mapping_result = await llm.analyze_csv(
            raw_csv,
            file.filename
        )

        source.field_map = mapping_result.get(
            "mappings", {}
        )

    except Exception:
        source.field_map = {}

    mappings = source.field_map or {}
    reverse = {v: k for k, v in mappings.items()}

    def col(name):
        return reverse.get(name)

    def to_list(value):
        if pd.isna(value):
            return []

        if isinstance(value, list):
            return value

        return [
            x.strip()
            for x in str(value).split(",")
            if x.strip()
        ]

    rows_added = 0

    for _, row in df.iterrows():

        name = str(
            row.get(col("name") or "name", "Unknown")
        )

        email = str(
            row.get(col("email") or "email", "")
        )

        phone = str(
            row.get(col("phone") or "phone", "")
        )

        age = _safe_int(
            row.get(col("age") or "age")
        )

        location = str(
            row.get(col("location") or "location", "")
        )

        income = str(
            row.get(
                col("income_bracket")
                or "income_bracket",
                ""
            )
        )

        occupation = str(
            row.get(
                col("occupation")
                or "occupation",
                ""
            )
        )

        existing_policies = to_list(
            row.get(
                col("existing_policies")
                or "existing_policies",
                ""
            )
        )

        behavioral_signals = to_list(
            row.get(
                col("behavioral_signals")
                or "behavioral_signals",
                ""
            )
        )

        life_events = to_list(
            row.get(
                col("life_events")
                or "life_events",
                ""
            )
        )

        # ProspectAudience
        prospect = ProspectAudience(
            source_id=source.id,
            name=name,
            email=email,
            phone=phone,
            age=age,
            location=location,
            income_bracket=income,
            occupation=occupation,

            existing_policies=existing_policies,

            behavioral_signals=behavioral_signals,

            life_events=life_events,

            priority_type="new_policy",
        )

        db.add(prospect)

        # Customer
        customer = Customer(
            name=name,
            email=email,
            phone=phone,
            age=age,
            location=location,

            income_bracket=income,

            occupation=occupation,

            existing_policies=existing_policies,

            behavioral_signals=behavioral_signals,

            life_events=life_events
        )

        db.add(customer)

        rows_added += 1

    source.record_count = rows_added
    source.status = "ingested"

    await db.flush()
    await db.commit()

    await _log(
        db,
        "Connector",
        f"CSV ingested: {file.filename} → {rows_added} prospects/customers",
        "success"
    )

    return {
        "source_id": source.id,
        "records_ingested": rows_added,
        "filename": file.filename,
        "field_map": source.field_map
    }

@connector_router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DataSource).order_by(desc(DataSource.ingested_at)).limit(20))
    sources = result.scalars().all()
    return [{"id": s.id, "type": s.source_type, "name": s.name,
             "records": s.record_count, "status": s.status,
             "fields": list((s.field_map or {}).keys()),
             "ingested_at": s.ingested_at} for s in sources]




@connector_router.post("/crm/mysql/test", response_model=CRMConnectResponse)
async def test_mysql_crm(req: MySQLCRMRequest, db: AsyncSession = Depends(get_db)):
    """Test connection to an external MySQL CRM (read-only probe)."""
    # pyrefly: ignore [missing-import]
    import aiomysql
    try:
        conn = await aiomysql.connect(
            host=req.host, port=req.port,
            user=req.user, password=req.password,
            db=req.database, connect_timeout=5,
        )
        async with conn.cursor() as cur:
            await cur.execute("SHOW TABLES")
            tables = [r[0] for r in await cur.fetchall()]
            await cur.execute(f"SELECT COUNT(*) FROM {req.table_name}")
            count = (await cur.fetchone())[0]
        conn.close()
        await _log(db, "Connector",
                   f"MySQL CRM connected: {req.host}/{req.database}", "success")
        return CRMConnectResponse(connected=True, record_count=count,
                                  tables=tables, message="Connection successful")
    except Exception as exc:
        return CRMConnectResponse(connected=False, record_count=0,
                                  tables=[], message=str(exc))







@connector_router.post("/crm/zoho/sync")
async def zoho_sync(db: AsyncSession = Depends(get_db)):
    """Placeholder — ZOHO OAuth sync would use ZOHO CRM REST API."""
    await _log(db, "Connector", "ZOHO CRM OAuth sync initiated (placeholder)", "info")
    return {"status": "initiated", "message": "Connect via ZOHO OAuth — redirect URL generated"}


# ════════════════════════════════════════════════════════════
#  POLICY WAREHOUSE AGENT
# ════════════════════════════════════════════════════════════
policy_router = APIRouter(prefix="/api/policy", tags=["Policy Warehouse"])

@policy_router.get("/list", response_model=list[PolicyResponse])
async def list_policies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).order_by(desc(Policy.created_at)))
    return result.scalars().all()


# @policy_router.post("/create", response_model=PolicyResponse)
# async def create_policy(payload: PolicyCreate, db: AsyncSession = Depends(get_db)):
#     pol = Policy(
#         name               = payload.name,
#         policy_type        = payload.policy_type,
#         coverage_range     = payload.coverage_range,
#         premium_range      = payload.premium_range,
#         eligibility        = payload.eligibility,
#         features           = payload.features,
#         propensity_targets = payload.propensity_targets,
#     )
#     db.add(pol)
#     await db.flush()
#     await _log(db, "Policy Warehouse", f"Policy created: '{pol.name}'", "info")
#     return pol

@policy_router.post("/create", response_model=PolicyResponse)
async def create_policy(
    payload: PolicyCreate,
    db: AsyncSession = Depends(get_db)
):
    pol = Policy(
        name=payload.name,
        policy_type=payload.policy_type,
        coverage_range=payload.coverage_range,
        premium_range=payload.premium_range,
        eligibility=payload.eligibility,
        features=payload.features,
        propensity_targets=payload.propensity_targets,
    )

    db.add(pol)

    await db.flush()
    await db.refresh(pol)

    await _log(
        db,
        "Policy Warehouse",
        f"Policy created: '{pol.name}'",
        "info"
    )

    return pol

@policy_router.post("/upload", response_model=PolicyUploadResponse)
async def upload_policy_document(
    file: UploadFile = File(...),
    save: bool = Form(False),
    policy_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF/DOCX policy document, analyze it with Mistral, and optionally save extracted fields to the DB."""
    def _normalize_policy_type(value: str | None) -> str | None:
        if not value:
            return None
        candidate = value.strip().title()
        allowed = {"Life", "Health", "Motor", "Property", "Commercial", "Travel"}
        return candidate if candidate in allowed else None

    def _ensure_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    content = await file.read()
    suffix = os.path.splitext(file.filename.lower())[1]
    if suffix == ".pdf":
        try:
            PdfReader = importlib.import_module("pypdf").PdfReader
            reader = PdfReader(io.BytesIO(content))
            text_content = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF parsing failed: {exc}")
    elif suffix == ".docx":
        try:
            Document = importlib.import_module("docx").Document
            doc = Document(io.BytesIO(content))
            text_content = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"DOCX parsing failed: {exc}")
    elif suffix == ".doc":
        raise HTTPException(status_code=400, detail="DOC format unsupported; please upload PDF or DOCX.")
    else:
        try:
            text_content = content.decode("utf-8", errors="ignore")
        except Exception:
            raise HTTPException(status_code=400, detail="Unsupported file type. Upload PDF or DOCX.")

    if not text_content.strip():
        raise HTTPException(status_code=400, detail="Document text could not be extracted or document is empty.")

    try:
        extracted = await llm.analyze_policy_document(text_content, file.filename)
    except Exception as exc:
        logger.warning("Policy document analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Policy document analysis failed: {exc}")

    policy_type = _normalize_policy_type(extracted.get("policy_type")) or "Life"
    features = _ensure_list(extracted.get("features"))
    propensity_targets = _ensure_list(extracted.get("propensity_targets"))
    preview = extracted.get("preview") or text_content[:320].strip()

    relevance_score = 0.0
    if extracted.get("relevance_score") is not None:
        try:
            relevance_score = float(extracted.get("relevance_score"))
        except (TypeError, ValueError):
            relevance_score = 0.0

    is_relevant = relevance_score >= 75.0
    saved = False
    doc_path = None
    policy_uuid = None
    if save:
        if policy_id:
            result = await db.execute(select(Policy).where(Policy.id == policy_id))
            pol = result.scalar_one_or_none()
            if not pol:
                raise HTTPException(status_code=404, detail="Policy not found")
        else:
            pol = Policy(
                name=extracted.get("name") or os.path.splitext(file.filename)[0],
                policy_type=policy_type,
                coverage_range=extracted.get("coverage_range"),
                premium_range=extracted.get("premium_range"),
                eligibility=extracted.get("eligibility"),
                features=features,
                propensity_targets=propensity_targets,
            )
            db.add(pol)
            await db.flush()

        if extracted.get("name"):
            pol.name = extracted["name"]
        if _normalize_policy_type(extracted.get("policy_type")):
            pol.policy_type = _normalize_policy_type(extracted.get("policy_type"))
        if extracted.get("coverage_range"):
            pol.coverage_range = extracted.get("coverage_range")
        if extracted.get("premium_range"):
            pol.premium_range = extracted.get("premium_range")
        if extracted.get("eligibility"):
            pol.eligibility = extracted.get("eligibility")
        if features:
            pol.features = features
        if propensity_targets:
            pol.propensity_targets = propensity_targets

        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        safe_filename = f"{pol.id}_{os.path.basename(file.filename)}"
        fpath = os.path.join(settings.UPLOAD_DIR, safe_filename)
        with open(fpath, "wb") as f:
            f.write(content)

        pol.document_path = fpath
        pol.doc_count = (pol.doc_count or 0) + 1
        pol.is_indexed = False

        await db.flush()
        await db.refresh(pol)

        saved = True
        doc_path = pol.document_path
        policy_uuid = pol.id

    return PolicyUploadResponse(
        filename=file.filename,
        saved=saved,
        policy_id=policy_uuid,
        name=extracted.get("name") or os.path.splitext(file.filename)[0],
        policy_type=policy_type,
        coverage_range=extracted.get("coverage_range"),
        premium_range=extracted.get("premium_range"),
        eligibility=extracted.get("eligibility"),
        features=features,
        propensity_targets=propensity_targets,
        preview=preview,
        relevance_score=relevance_score,
        is_relevant=is_relevant,
        relevance_threshold=75,
        document_path=doc_path,
    )


@policy_router.post("/{policy_id}/index")
async def index_policy(policy_id: str, db: AsyncSession = Depends(get_db)):
    """Index policy into ChromaDB (vectors) + ArangoDB (graph)."""
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    pol = result.scalar_one_or_none()
    if not pol:
        raise HTTPException(404, "Policy not found")

    # ChromaDB embedding
    chroma.index_policy(
        policy_id  = pol.id,
        name       = pol.name,
        policy_type= pol.policy_type,
        features   = pol.features or [],
        targets    = pol.propensity_targets or [],
    )

    # ArangoDB vertex
    vertex_id = arango.upsert_policy_vertex(
        policy_id   = pol.id,
        name        = pol.name,
        policy_type = pol.policy_type,
        targets     = pol.propensity_targets or [],
    )

    pol.is_indexed       = True
    pol.arango_vertex_id = vertex_id
    pol.embedding_model  = settings.EMBEDDING_MODEL

    await _log(db, "Policy Warehouse",
               f"Policy indexed: '{pol.name}' → ChromaDB + ArangoDB", "success")
    return {"status": "indexed", "policy_id": policy_id,
            "arango_vertex": vertex_id, "chroma_collection": settings.CHROMA_POLICY_COLLECTION}


@policy_router.get("/knowledge-graph", response_model=KnowledgeGraphResponse)
async def knowledge_graph():
    """Return full knowledge graph data from ArangoDB."""
    try:
        data = arango.get_knowledge_graph_data()
        return KnowledgeGraphResponse(**data)
    except Exception as exc:
        raise HTTPException(500, f"Knowledge graph error: {exc}")


@policy_router.delete("/{policy_id}")
async def delete_policy(policy_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    pol = result.scalar_one_or_none()
    if not pol:
        raise HTTPException(404, "Policy not found")
    await db.delete(pol)
    await _log(db, "Policy Warehouse", f"Policy deleted: '{pol.name}'")
    return {"deleted": policy_id}


# ════════════════════════════════════════════════════════════
#  PROSPECT AGENT
# ════════════════════════════════════════════════════════════
prospect_router = APIRouter(prefix="/api/prospects", tags=["Prospect Agent"])

@prospect_router.get("/new", response_model=list[ProspectResponse])
async def get_new_prospects(
    min_score: float = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(ProspectAudience)
        .where(
            ProspectAudience.priority_type == "new_policy",
            ProspectAudience.propensity_score >= min_score,
        )
        .order_by(desc(ProspectAudience.propensity_score))
        .limit(limit)
    )
    result = await db.execute(q)
    rows   = result.scalars().all()

    out = []
    for rank, p in enumerate(rows, 1):
        src_name = None
        if p.source_id:
            sr = await db.execute(select(DataSource.name).where(DataSource.id == p.source_id))
            src_name = sr.scalar_one_or_none()
        out.append(ProspectResponse(
            id                  = p.id,
            rank                = rank,
            name                = p.name,
            age                 = p.age,
            location            = p.location,
            email               = p.email,
            income_bracket      = p.income_bracket,
            propensity_score    = p.propensity_score,
            recommended_product = p.recommended_product,
            behavioral_signals  = p.behavioral_signals or [],
            outreach_channel    = p.outreach_channel,
            urgency_level       = p.urgency_level or "Medium",
            ai_context          = p.ai_context,
            source_name         = src_name,
        ))
    return out


@prospect_router.get("/renewals", response_model=list[RenewalProspectResponse])
async def get_renewals(
    min_score: float = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Renewal, ProspectAudience)
        .join(ProspectAudience, Renewal.prospect_id == ProspectAudience.id)
        .where(Renewal.retention_score >= min_score)
        .order_by(Renewal.days_to_expiry.asc(), desc(Renewal.retention_score))
        .limit(limit)
    )
    result = await db.execute(q)
    rows = result.all()

    return [
        RenewalProspectResponse(
            id              = r.id,
            rank            = i + 1,
            name            = p.name,
            age             = p.age,
            location        = p.location,
            email           = p.email,
            policy_name     = r.policy_name or "",
            days_to_expiry  = r.days_to_expiry or 0,
            retention_score = r.retention_score,
            churn_risk      = r.churn_risk or "Medium",
            renewal_action  = r.renewal_action,
            urgency_level   = p.urgency_level or "Medium",
            signals         = p.behavioral_signals or [],
            recommendation  = p.recommended_product,
            ai_context      = p.ai_context,
        )
        for i, (r, p) in enumerate(rows)
    ]


@prospect_router.post("/run-scoring")
async def run_prospect_scoring(db: AsyncSession = Depends(get_db)):
    """
    Full scoring pipeline:
    1. Fetch unscored prospects from DB
    2. Fetch indexed policies
    3. Use ChromaDB semantic matching + Mistral scoring
    4. Persist scores back to DB
    """
    await _log(db, "Prospect Agent", "Propensity scoring run initiated")

    # Fetch unscored prospects
    q_p = select(ProspectAudience).where(ProspectAudience.propensity_score == 0).limit(100)
    unscored = (await db.execute(q_p)).scalars().all()

    # Fetch indexed policies for context
    q_pol = select(Policy).where(Policy.is_indexed == True)
    policies = (await db.execute(q_pol)).scalars().all()
    pol_dicts = [{"id": p.id, "name": p.name, "type": p.policy_type,
                  "targets": p.propensity_targets or []} for p in policies]

    if not unscored or not pol_dicts:
        return {"scored": 0, "message": "No unscored prospects or no indexed policies"}

    # Build prospect dicts for LLM
    p_dicts = [
        {"id": p.id, "name": p.name, "age": p.age, "location": p.location,
         "income_bracket": p.income_bracket, "signals": p.behavioral_signals or [],
         "life_events": p.life_events or []}
        for p in unscored
    ]

    try:
        scored = await llm.score_and_rank_prospects(p_dicts, pol_dicts)
    except Exception as exc:
        await _log(db, "Prospect Agent", f"Scoring LLM error: {exc}", "error")
        raise HTTPException(500, str(exc))

    updated = 0
    for s in scored:
        await db.execute(
            update(ProspectAudience)
            .where(ProspectAudience.id == s.get("id"))
            .values(
                propensity_score    = float(s.get("propensity_score", 0)),
                recommended_product = s.get("recommended_product"),
                urgency_level       = s.get("urgency_level", "Medium"),
                outreach_channel    = s.get("outreach_channel"),
                ai_context          = s.get("ai_context"),
                behavioral_signals  = s.get("behavioral_signals", []),
            )
        )
        updated += 1

    await _log(db, "Prospect Agent",
               f"Scoring complete: {updated} prospects scored", "success")
    return {"scored": updated, "policies_used": len(pol_dicts)}


@prospect_router.post("/analyze/{prospect_id}", response_model=ProspectAnalysisResponse)
async def deep_analyze_prospect(
    prospect_id: str,
    req: ProspectAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProspectAudience).where(ProspectAudience.id == prospect_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Prospect not found")

    # Semantic match against policies
    matched = chroma.search_matching_policies(p.behavioral_signals or [], n_results=None)

    p_dict = {"id": p.id, "name": p.name, "age": p.age, "location": p.location,
              "income_bracket": p.income_bracket, "behavioral_signals": p.behavioral_signals or [],
              "ai_context": p.ai_context, "recommended_product": p.recommended_product}

    try:
        analysis = await llm.analyze_prospect_deep(p_dict, matched, req.analysis_type)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        logger.error(f"Deep Analysis Error: {str(exc)}")
        raise HTTPException(500, str(exc))

    await _log(db, "Prospect Agent",
               f"Deep analysis generated for: {p.name}", "success")

    return ProspectAnalysisResponse(
        prospect_id    = prospect_id,
        analysis       = analysis.get("analysis", ""),
        key_insights   = analysis.get("key_insights", []),
        talking_points = analysis.get("talking_points", []),
        risk_factors   = analysis.get("risk_factors", []),
        next_action    = analysis.get("next_action", ""),
        best_time      = analysis.get("best_time", ""),
        generated_at   = datetime.utcnow(),
    )


@prospect_router.get("/audience-table")
async def get_audience_table(
    priority_type: str = "new_policy",
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(ProspectAudience)
        .where(ProspectAudience.priority_type == priority_type)
        .order_by(desc(ProspectAudience.propensity_score))
        .offset(offset).limit(limit)
    )
    rows  = (await db.execute(q)).scalars().all()
    total = await db.scalar(
        select(func.count(ProspectAudience.id))
        .where(ProspectAudience.priority_type == priority_type)
    )
    return {"total": total, "offset": offset, "limit": limit, "data": [
        {c.name: getattr(r, c.name) for c in ProspectAudience.__table__.columns}
        for r in rows
    ]}


# @prospect_router.get("/customers-table")
# async def get_customers_table(
#     limit: int = 100,
#     offset: int = 0,
#     db: AsyncSession = Depends(get_db),
# ):
#     """Get customer/prospect data with specific columns: name, email, phone, age, city, income, occupation, 
#     existing_policies, behavioral_signals, life_events."""
#     q = (
#         select(ProspectAudience)
#         .order_by(desc(ProspectAudience.propensity_score))
#         .offset(offset)
#         .limit(limit)
#     )
#     rows = (await db.execute(q)).scalars().all()
#     total = await db.scalar(select(func.count(ProspectAudience.id)))

#     data = [
#         {
#             "name": r.name,
#             "email": r.email or "",
#             "phone": r.phone or "",
#             "age": r.age,
#             "city": r.location or "",
#             "income": r.income_bracket or "",
#             "occupation": r.occupation or "",
#             "existing_policies": r.existing_policies or [],
#             "behavioral_signals": r.behavioral_signals or [],
#             "life_events": r.life_events or [],
#         }
#         for r in rows
#     ]

#     return {"total": total, "offset": offset, "limit": limit, "data": data}






@prospect_router.get("/customers-table")
async def get_customers_table(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get customer data from Customer table"""

    q = (
        select(Customer)
        .order_by(desc(Customer.created_at))
        .offset(offset)
        .limit(limit)
    )

    rows = (await db.execute(q)).scalars().all()

    total = await db.scalar(
        select(func.count(Customer.id))
    )

    data = [
        {
            "name": r.name,
            "email": r.email or "",
            "phone": r.phone or "",
            "age": r.age,
            "city": r.location or "",
            "income": r.income_bracket or "",
            "occupation": r.occupation or "",
            "existing_policies": r.existing_policies or [],
            "behavioral_signals": r.behavioral_signals or [],
            "life_events": r.life_events or [],
        }
        for r in rows
    ]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "data": data
    }


# ════════════════════════════════════════════════════════════
#  CAMPAIGN AGENT
# ════════════════════════════════════════════════════════════
campaign_router = APIRouter(prefix="/api/campaigns", tags=["Campaign Agent"])

@campaign_router.get("/", response_model=list[CampaignResponse])
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(desc(Campaign.created_at)))
    return result.scalars().all()


@campaign_router.post("/", response_model=CampaignResponse)
async def create_campaign(payload: CampaignCreate, db: AsyncSession = Depends(get_db)):
    target_count = len(payload.prospect_ids)
    if target_count == 0:
        q = select(func.count(ProspectAudience.id)).where(
            ProspectAudience.priority_type == payload.campaign_type
        )
        target_count = await db.scalar(q) or 0

    c = Campaign(
        name          = payload.name,
        description   = payload.description,
        campaign_type = payload.campaign_type,
        channel       = payload.channel,
        target_count  = target_count,
        scheduled_at  = payload.scheduled_at,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    await _log(db, "Campaign Agent",
               f"Campaign created: '{c.name}' targeting {c.target_count} prospects")
    return c


@campaign_router.post("/policy-wise", response_model=CampaignResponse)
async def create_policy_wise_campaign(
    payload: PolicyCampaignCreate,
    bg_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # 1. Fetch Policy
    result = await db.execute(select(Policy).where(Policy.id == payload.policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")

    # 2. Query matching prospects
    q_count = select(func.count(ProspectAudience.id)).where(
        func.lower(ProspectAudience.recommended_product) == policy.name.lower(),
        func.lower(ProspectAudience.outreach_channel) == "email",
        ProspectAudience.email.isnot(None),
        ProspectAudience.email != ""
    )
    target_count = await db.scalar(q_count) or 0

    # 3. Create Campaign record
    campaign_name = payload.name or f"Campaign for {policy.name}"
    campaign_desc = payload.description or f"Policy-wise email campaign targeting prospects recommended for {policy.name}"
    c = Campaign(
        name          = campaign_name,
        description   = campaign_desc,
        campaign_type = payload.campaign_type or "cross_sell",
        channel       = payload.channel,
        status        = "active",
        target_count  = target_count,
        launched_at   = datetime.utcnow(),
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    
    await _log(db, "Campaign Agent",
               f"Policy-wise campaign '{c.name}' created/launched targeting {c.target_count} prospects", "success")

    # 4. Trigger background outreach
    if target_count > 0:
        bg_tasks.add_task(_run_policy_campaign_outreach_bg, c.id, policy.name)
    else:
        c.status = "completed"
        c.completed_at = datetime.utcnow()
        await db.commit()

    return c



async def _run_campaign_outreach_bg(campaign_id: str):
    async with AsyncSessionLocal() as db:
        try:
            c = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
            if not c:
                return

            prospects = (
                await db.execute(
                    select(ProspectAudience)
                    .where(ProspectAudience.priority_type == c.campaign_type)
                )
            ).scalars().all()

            sent_count = 0
            for p in prospects:
                if not p.email:
                    continue
                try:
                    msg_text = await llm.draft_outreach_message(
                        prospect={"name": p.name, "age": p.age, "location": p.location,
                                  "behavioral_signals": p.behavioral_signals or [],
                                  "ai_context": p.ai_context or ""},
                        policy={"name": p.recommended_product or ""},
                        channel=c.channel,
                    )
                    subject = f"Your personalized {c.campaign_type.replace('_', ' ')} recommendation"
                    
                    # Generate HTML body with tracking
                    base_url = get_settings().API_BASE_URL.rstrip('/')
                    open_track_url = f"{base_url}/api/campaigns/track/{c.id}/{p.id}/open"
                    click_track_url = f"{base_url}/api/campaigns/track/{c.id}/{p.id}/click"
                    
                    html_content = f"""
                    <html>
                      <body style="font-family: sans-serif; color: #333; line-height: 1.6;">
                        <p>{msg_text.replace(chr(10), '<br>')}</p>
                        
                        <div style="margin-top: 30px; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f8f9fa;">
                          <h3 style="margin-top: 0; color: #2c3e50;">Recommendation Specifically For You</h3>
                          <p>Based on your profile, we strongly recommend <strong>{p.recommended_product if p.recommended_product else 'one of our premium tailored policies'}</strong>.</p>
                          <a href="{click_track_url}" style="display: inline-block; margin-top: 10px; padding: 12px 24px; background-color: #007bff; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: bold;">View Your Policy & Claim Now</a>
                        </div>
                        
                        <!-- Invisible Tracking Pixel -->
                        <img src="{open_track_url}" width="1" height="1" style="display:none;" alt="" />
                      </body>
                    </html>
                    """
                    
                    success = await email_service.send_email_async(
                        to_email=p.email,
                        subject=subject,
                        body_text=msg_text,
                        html_body=html_content
                    )
                    
                    if success:
                        c.sent_count += 1
                        await db.commit()
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Error sending to {p.email}: {e}")

            await _log(db, "Campaign Agent", f"Campaign '{c.name}' email outreach complete. Sent: {sent_count}.", "success")
            await db.commit()
        except Exception as e:
            logger.error(f"Background campaign error: {e}")
            await db.rollback()

async def _run_policy_campaign_outreach_bg(campaign_id: str, policy_name: str):
    async with AsyncSessionLocal() as db:
        try:
            c = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
            if not c:
                return

            prospects = (
                await db.execute(
                    select(ProspectAudience)
                    .where(
                        func.lower(ProspectAudience.recommended_product) == policy_name.lower(),
                        func.lower(ProspectAudience.outreach_channel) == "email",
                        ProspectAudience.email.isnot(None),
                        ProspectAudience.email != ""
                    )
                )
            ).scalars().all()

            sent_count = 0
            for p in prospects:
                try:
                    msg_text = await llm.draft_outreach_message(
                        prospect={"name": p.name, "age": p.age, "location": p.location,
                                  "behavioral_signals": p.behavioral_signals or [],
                                  "ai_context": p.ai_context or ""},
                        policy={"name": p.recommended_product or ""},
                        channel=c.channel,
                    )
                    subject = f"Your personalized {p.recommended_product} recommendation"
                    
                    # Generate HTML body with tracking
                    base_url = get_settings().API_BASE_URL.rstrip('/')
                    open_track_url = f"{base_url}/api/campaigns/track/{c.id}/{p.id}/open"
                    click_track_url = f"{base_url}/api/campaigns/track/{c.id}/{p.id}/click"
                    
                    html_content = f"""
                    <html>
                      <body style="font-family: sans-serif; color: #333; line-height: 1.6;">
                        <p>{msg_text.replace(chr(10), '<br>')}</p>
                        
                        <div style="margin-top: 30px; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f8f9fa;">
                          <h3 style="margin-top: 0; color: #2c3e50;">Recommendation Specifically For You</h3>
                          <p>Based on your profile, we strongly recommend <strong>{p.recommended_product}</strong>.</p>
                          <a href="{click_track_url}" style="display: inline-block; margin-top: 10px; padding: 12px 24px; background-color: #007bff; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: bold;">View Your Policy & Claim Now</a>
                        </div>
                        
                        <!-- Invisible Tracking Pixel -->
                        <img src="{open_track_url}" width="1" height="1" style="display:none;" alt="" />
                      </body>
                    </html>
                    """
                    
                    success = await email_service.send_email_async(
                        to_email=p.email,
                        subject=subject,
                        body_text=msg_text,
                        html_body=html_content
                    )
                    
                    if success:
                        c.sent_count += 1
                        await db.commit()
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Error sending to {p.email}: {e}")

            c.status = "completed"
            c.completed_at = datetime.utcnow()
            await _log(db, "Campaign Agent", f"Policy-wise campaign '{c.name}' email outreach complete. Sent: {sent_count}.", "success")
            await db.commit()
        except Exception as e:
            logger.error(f"Background policy-wise campaign error: {e}")
            await db.rollback()

@campaign_router.post("/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, bg_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campaign not found")
    c.status      = "active"
    c.launched_at = datetime.utcnow()
    await _log(db, "Campaign Agent",
               f"Campaign launched: '{c.name}' ({c.target_count} prospects)", "success")
               
    if c.channel.lower() == "email":
        bg_tasks.add_task(_run_campaign_outreach_bg, campaign_id)
        
    return {"status": "active", "launched_at": c.launched_at,
            "campaign_id": campaign_id, "targets": c.target_count}


@campaign_router.get("/track/{campaign_id}/{prospect_id}/open")
async def track_campaign_open(campaign_id: str, prospect_id: str, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if c:
        c.opened_count += 1
        await db.commit()
    # 1x1 transparent GIF
    pixel = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
    return Response(content=pixel, media_type="image/gif")

@campaign_router.get("/track/{campaign_id}/{prospect_id}/click")
async def track_campaign_click(campaign_id: str, prospect_id: str, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if c:
        c.converted_count += 1
        await db.commit()
    # Redirect to a dummy success page or returning a message
    return HTMLResponse("<html><head><style>body{font-family:sans-serif;text-align:center;padding:50px;}</style></head><body><h2>Success!</h2><p>You have successfully claimed your recommended policy.</p></body></html>")

@campaign_router.get("/{campaign_id}/generate-messages")
async def generate_campaign_messages(
    campaign_id: str,
    sample_count: int = 3,
    db: AsyncSession = Depends(get_db),
):
    """Use Mistral to draft sample outreach messages for the campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campaign not found")

    # Fetch a few target prospects
    prospects = (
        await db.execute(
            select(ProspectAudience)
            .where(ProspectAudience.priority_type == c.campaign_type.replace("_", "_"))
            .limit(sample_count)
        )
    ).scalars().all()

    messages = []
    for p in prospects:
        try:
            msg = await llm.draft_outreach_message(
                prospect={"name": p.name, "age": p.age, "location": p.location,
                          "behavioral_signals": p.behavioral_signals or [],
                          "ai_context": p.ai_context or ""},
                policy={"name": p.recommended_product or ""},
                channel=c.channel,
            )
            messages.append({"prospect_id": p.id, "name": p.name, "message": msg})
        except Exception:
            pass

    return {"campaign_id": campaign_id, "channel": c.channel, "messages": messages}


# ════════════════════════════════════════════════════════════
#  AGENT LOGS
# ════════════════════════════════════════════════════════════
log_router = APIRouter(prefix="/api/logs", tags=["Logs"])

@log_router.get("/", response_model=list[LogResponse])
async def get_logs(agent: str | None = None, limit: int = 50,
                   db: AsyncSession = Depends(get_db)):
    q = select(AgentLog).order_by(desc(AgentLog.created_at)).limit(limit)
    if agent:
        q = q.where(AgentLog.agent_name == agent)
    return (await db.execute(q)).scalars().all()


# ── Utility ───────────────────────────────────────────────
def _safe_int(val: Any) -> int | None:
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None


