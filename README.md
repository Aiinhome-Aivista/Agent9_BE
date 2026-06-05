# ARIES — Agentic Revenue Intelligence Engine for Sales
> Insurance Distribution, Marketing & Renewals Platform  
> PwC Agentic AI Design · v2.1.0

---

## Stack

| Layer          | Technology              | Port  |
|----------------|-------------------------|-------|
| Frontend UI    | React 18 + Vite 6       | 3000  |
| Backend APIs   | FastAPI (Python 3.12)   | 8080  |
| Relational DB  | MySQL 8.0               | 3306  |
| Graph / KG DB  | ArangoDB 3.11           | 8529  |
| Vector DB      | ChromaDB (local)        | 8001  |
| LLM            | Mistral Small Latest    | —     |
| Embeddings     | all-MiniLM-L6-v2        | —     |

---

## Agent Hierarchy

```
Orchestrator Agent
├── Connector Agent          CSV parser · MySQL CRM · ZOHO OAuth
│   ├── CSV Parser Sub-agent
│   └── CRM Sync Sub-agent
├── Policy Warehouse Agent   Document upload · ChromaDB index · ArangoDB KG
│   ├── KG Builder Sub-agent
│   └── Vector Index Sub-agent
├── Prospect Agent           Propensity scoring · Deep analysis (Mistral)
│   └── Mistral Ranker Sub-agent
└── Campaign Execution Agent CRUD · Launch · Message generation (Mistral)
```

---

## Quickstart

```bash
# 1. Clone and configure
cp .env.example .env
# Add your MISTRAL_API_KEY to .env

# 2. Start all services
docker compose up -d

# 3. Open
#   Frontend:    http://localhost:3000
#   API Docs:    http://localhost:8080/api/docs
#   ArangoDB UI: http://localhost:8529  (root / arangoroot)

# Local backend dev (no Docker)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080

# Local frontend dev
cd frontend
npm install
npm run dev
```

---

## Data Flow

```
CSV / CRM
   │
   ▼
Connector Agent ──► MySQL (prospect_audience)
                           │
                           ▼
                    Prospect Agent
                    ├── ChromaDB semantic match
                    └── Mistral scoring ──► propensity_score, urgency, channel

Policy upload
   │
   ▼
Policy Warehouse ──► ChromaDB (policy_documents)
                  └─► ArangoDB (aries_graph)
                           │
                           ▼
                    Knowledge Graph
                    policies ──► signal_nodes ◄── prospect_nodes

Campaign Agent ──► Mistral message drafting ──► Multi-channel outreach
```

---

## Key API Endpoints

```
GET  /api/dashboard/metrics         Dashboard KPIs

POST /api/connector/csv/analyze     Mistral field mapping
POST /api/connector/csv/ingest      CSV → MySQL
POST /api/connector/crm/mysql/test  Test external MySQL CRM
POST /api/connector/crm/zoho/sync   ZOHO OAuth sync

GET  /api/policy/list               All policies
POST /api/policy/create             Create policy
POST /api/policy/upload             Upload PDF doc + Mistral extraction
POST /api/policy/{id}/index         → ChromaDB + ArangoDB
GET  /api/policy/knowledge-graph    Full graph data

GET  /api/prospects/new             Ranked new policy prospects
GET  /api/prospects/renewals        Ranked renewal list
POST /api/prospects/run-scoring     Trigger Mistral batch scoring
POST /api/prospects/analyze/{id}    Deep single prospect analysis

GET  /api/campaigns/                List campaigns
POST /api/campaigns/                Create campaign
POST /api/campaigns/{id}/launch     Launch
GET  /api/campaigns/{id}/generate-messages  Mistral outreach drafts

GET  /api/logs/                     Agent activity log
```

---

## MySQL Tables

- `data_sources` — ingested CSV/CRM files
- `prospect_audience` — full target audience with AI scores
- `policies` — insurance product catalog
- `renewals` — upcoming renewal tracking
- `campaigns` — outreach campaign records
- `campaign_prospects` — campaign↔prospect link table
- `agent_logs` — pipeline audit trail

## ArangoDB Graph (`aries_graph`)

| Collection        | Type   | Description                    |
|-------------------|--------|--------------------------------|
| policies          | Vertex | Policy product nodes           |
| prospect_nodes    | Vertex | Prospect reference nodes       |
| signal_nodes      | Vertex | Propensity signal nodes        |
| policy_targets    | Edge   | Policy → Signal                |
| prospect_signals  | Edge   | Prospect → Signal              |
| recommendations   | Edge   | Prospect → Policy (AI ranked)  |

## ChromaDB Collections

| Collection          | Content                        | Model              |
|---------------------|--------------------------------|--------------------|
| policy_documents    | Full policy text embeddings    | all-MiniLM-L6-v2   |
| prospect_contexts   | Prospect behaviour embeddings  | all-MiniLM-L6-v2   |
