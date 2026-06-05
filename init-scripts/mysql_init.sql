-- ═══════════════════════════════════════════════════════════
--  ARIES — MySQL Schema
--  Relational store: prospects, policies, campaigns, imports
-- ═══════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS aries_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aries_db;

-- ── CSV / CRM Import Sources ──────────────────────────────
CREATE TABLE IF NOT EXISTS data_sources (
    id            VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
    source_type   ENUM('csv','mysql_crm','zoho_crm') NOT NULL,
    name          VARCHAR(255) NOT NULL,
    filename      VARCHAR(255),
    record_count  INT          DEFAULT 0,
    field_map     JSON,
    status        ENUM('pending','processing','ingested','error') DEFAULT 'pending',
    error_msg     TEXT,
    ingested_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_type (source_type),
    INDEX idx_status (status)
);

-- ── Prospective Target Audience Table ─────────────────────
CREATE TABLE IF NOT EXISTS prospect_audience (
    id                   VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
    source_id            VARCHAR(36),
    name                 VARCHAR(255) NOT NULL,
    email                VARCHAR(255),
    phone                VARCHAR(30),
    age                  INT,
    location             VARCHAR(255),
    income_bracket       VARCHAR(100),
    occupation           VARCHAR(255),
    existing_policies    JSON         COMMENT 'Array of current policy IDs/names',
    behavioral_signals   JSON         COMMENT 'Array of observed behavior strings',
    life_events          JSON         COMMENT 'Recent life events: marriage, home purchase, etc.',
    propensity_score     FLOAT        DEFAULT 0,
    recommended_product  VARCHAR(255),
    priority_type        ENUM('new_policy','renewal','cross_sell') DEFAULT 'new_policy',
    outreach_channel     VARCHAR(100),
    urgency_level        ENUM('Critical','High','Medium','Low') DEFAULT 'Medium',
    ai_context           TEXT         COMMENT 'AI-generated prospect context',
    crm_reference_id     VARCHAR(255),
    is_contacted         BOOLEAN      DEFAULT FALSE,
    created_at           DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE SET NULL,
    INDEX idx_score (propensity_score DESC),
    INDEX idx_priority (priority_type),
    INDEX idx_urgency (urgency_level),
    INDEX idx_location (location),
    FULLTEXT idx_signals (ai_context)
);

-- ── Insurance Policy Products ─────────────────────────────
CREATE TABLE IF NOT EXISTS policies (
    id                  VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
    name                VARCHAR(255) NOT NULL,
    policy_type         ENUM('Life','Health','Motor','Property','Commercial','Travel') NOT NULL,
    coverage_range      VARCHAR(100),
    premium_range       VARCHAR(100),
    eligibility         VARCHAR(255),
    features            JSON         COMMENT 'Array of feature strings',
    propensity_targets  JSON         COMMENT 'Target audience signal tags',
    document_path       VARCHAR(500) COMMENT 'Uploaded document file path',
    is_indexed          BOOLEAN      DEFAULT FALSE COMMENT 'Indexed in ChromaDB + ArangoDB',
    chroma_collection   VARCHAR(100) DEFAULT 'policy_documents',
    arango_vertex_id    VARCHAR(100),
    doc_count           INT          DEFAULT 0,
    embedding_model     VARCHAR(100),
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_type (policy_type),
    INDEX idx_indexed (is_indexed)
);

-- ── Renewal Tracking ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS renewals (
    id                  VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
    prospect_id         VARCHAR(36)  NOT NULL,
    policy_id           VARCHAR(36)  NOT NULL,
    policy_name         VARCHAR(255),
    expiry_date         DATE         NOT NULL,
    days_to_expiry      INT          GENERATED ALWAYS AS (DATEDIFF(expiry_date, CURDATE())) VIRTUAL,
    retention_score     FLOAT        DEFAULT 0,
    churn_risk          ENUM('High','Medium','Low') DEFAULT 'Medium',
    renewal_action      VARCHAR(255),
    renewal_status      ENUM('pending','contacted','renewed','lapsed') DEFAULT 'pending',
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prospect_id) REFERENCES prospect_audience(id) ON DELETE CASCADE,
    FOREIGN KEY (policy_id)   REFERENCES policies(id)          ON DELETE CASCADE,
    INDEX idx_expiry (expiry_date),
    INDEX idx_days (days_to_expiry),
    INDEX idx_retention (retention_score DESC)
);

-- ── Outreach Campaigns ────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
    id              VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    campaign_type   ENUM('new_policy','renewal','cross_sell','retention') NOT NULL,
    channel         VARCHAR(100) COMMENT 'Email, WhatsApp, SMS, Phone, LinkedIn',
    status          ENUM('draft','scheduled','active','paused','completed') DEFAULT 'draft',
    target_count    INT          DEFAULT 0,
    sent_count      INT          DEFAULT 0,
    opened_count    INT          DEFAULT 0,
    converted_count INT          DEFAULT 0,
    scheduled_at    DATETIME,
    launched_at     DATETIME,
    completed_at    DATETIME,
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_type (campaign_type)
);

-- ── Campaign ↔ Prospect Link ──────────────────────────────
CREATE TABLE IF NOT EXISTS campaign_prospects (
    campaign_id     VARCHAR(36) NOT NULL,
    prospect_id     VARCHAR(36) NOT NULL,
    outreach_status ENUM('queued','sent','opened','clicked','converted','bounced') DEFAULT 'queued',
    sent_at         DATETIME,
    PRIMARY KEY (campaign_id, prospect_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (prospect_id) REFERENCES prospect_audience(id) ON DELETE CASCADE
);

-- ── Agent Run Logs ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_logs (
    id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
    agent_name  VARCHAR(100) NOT NULL,
    event_type  ENUM('info','success','warning','error') DEFAULT 'info',
    message     TEXT         NOT NULL,
    metadata    JSON,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent (agent_name),
    INDEX idx_time  (created_at DESC)
);

-- ── Seed: sample agent logs ───────────────────────────────
INSERT INTO agent_logs (agent_name, event_type, message) VALUES
('Orchestrator',    'info',    'ARIES platform initialized. All agents online.'),
('Policy Warehouse','info',    'Ready to accept policy document uploads.'),
('Connector',       'info',    'Awaiting CSV data or CRM connection.'),
('Prospect Agent',  'info',    'Propensity model loaded and ready.');
