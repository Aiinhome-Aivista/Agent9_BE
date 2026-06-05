"""
ArangoDB Client — ARIES Knowledge Graph
========================================
Collections (vertices):
  - policies          Policy product nodes
  - prospect_nodes    Prospect audience nodes (lightweight refs)
  - signal_nodes      Propensity signal nodes (age groups, life events, behaviours)

Edge Collections:
  - policy_targets    Policy → Signal  (what signals a policy targets)
  - prospect_signals  Prospect → Signal (what signals a prospect exhibits)
  - recommendations   Prospect → Policy (AI-ranked recommendations)
"""

from arango import ArangoClient
from arango.database import StandardDatabase
from .config import get_settings
import logging

logger = logging.getLogger("aries.arango")
settings = get_settings()

_db: StandardDatabase | None = None

VERTEX_COLLECTIONS = ["policies", "prospect_nodes", "signal_nodes"]
EDGE_COLLECTIONS   = ["policy_targets", "prospect_signals", "recommendations"]


def get_arango_db() -> StandardDatabase:
    global _db
    if _db is None:
        raise RuntimeError("ArangoDB not initialised — call init_arango() first.")
    return _db


def init_arango() -> None:
    """Connect to ArangoDB and ensure collections exist."""
    global _db
    try:
        client = ArangoClient(hosts=settings.ARANGO_URL)
        sys_db = client.db("_system", username=settings.ARANGO_USER,
                           password=settings.ARANGO_PASSWORD)

        # Create application database if absent
        if not sys_db.has_database(settings.ARANGO_DB):
            sys_db.create_database(settings.ARANGO_DB)
            logger.info("ArangoDB: created database '%s'", settings.ARANGO_DB)

        _db = client.db(settings.ARANGO_DB,
                        username=settings.ARANGO_USER,
                        password=settings.ARANGO_PASSWORD)

        # Ensure vertex collections
        for name in VERTEX_COLLECTIONS:
            if not _db.has_collection(name):
                _db.create_collection(name)
                logger.info("ArangoDB: created collection '%s'", name)

        # Ensure edge collections
        for name in EDGE_COLLECTIONS:
            if not _db.has_collection(name):
                _db.create_collection(name, edge=True)
                logger.info("ArangoDB: created edge collection '%s'", name)

        # Create named graph if absent
        if not _db.has_graph("aries_graph"):
            _db.create_graph(
                "aries_graph",
                edge_definitions=[
                    {
                        "edge_collection": "policy_targets",
                        "from_vertex_collections": ["policies"],
                        "to_vertex_collections":   ["signal_nodes"],
                    },
                    {
                        "edge_collection": "prospect_signals",
                        "from_vertex_collections": ["prospect_nodes"],
                        "to_vertex_collections":   ["signal_nodes"],
                    },
                    {
                        "edge_collection": "recommendations",
                        "from_vertex_collections": ["prospect_nodes"],
                        "to_vertex_collections":   ["policies"],
                    },
                ],
            )
            logger.info("ArangoDB: created graph 'aries_graph'")

        logger.info("ArangoDB ready at %s / %s", settings.ARANGO_URL, settings.ARANGO_DB)
    except Exception as exc:
        logger.error("ArangoDB init failed: %s", exc)
        raise


# ── Graph Write Helpers ────────────────────────────────────

def upsert_policy_vertex(policy_id: str, name: str, policy_type: str,
                         targets: list[str]) -> str:
    """Insert/update a policy vertex and its signal edges."""
    db = get_arango_db()
    key = f"policy_{policy_id.replace('-', '_')}"
    col = db.collection("policies")

    if col.has(key):
        col.update({"_key": key, "name": name, "type": policy_type})
    else:
        col.insert({"_key": key, "id": policy_id, "name": name, "type": policy_type})

    # Upsert signal nodes and edges
    sig_col  = db.collection("signal_nodes")
    edge_col = db.collection("policy_targets")

    for signal in targets:
        sig_key = _make_key(signal)
        if not sig_col.has(sig_key):
            sig_col.insert({"_key": sig_key, "label": signal})

        edge_key = f"{key}_{sig_key}"
        if not edge_col.has(edge_key):
            edge_col.insert({
                "_key":  edge_key,
                "_from": f"policies/{key}",
                "_to":   f"signal_nodes/{sig_key}",
                "weight": 1.0,
            })

    return f"policies/{key}"


def upsert_prospect_vertex(prospect_id: str, name: str, signals: list[str],
                           recommended_policy_id: str | None = None) -> str:
    db = get_arango_db()
    key = f"prospect_{prospect_id.replace('-', '_')}"
    col = db.collection("prospect_nodes")

    if col.has(key):
        col.update({"_key": key, "name": name})
    else:
        col.insert({"_key": key, "id": prospect_id, "name": name})

    sig_col  = db.collection("signal_nodes")
    edge_col = db.collection("prospect_signals")
    for signal in signals:
        sig_key = _make_key(signal)
        if not sig_col.has(sig_key):
            sig_col.insert({"_key": sig_key, "label": signal})
        edge_key = f"{key}_{sig_key}"
        if not edge_col.has(edge_key):
            edge_col.insert({
                "_key":  edge_key,
                "_from": f"prospect_nodes/{key}",
                "_to":   f"signal_nodes/{sig_key}",
            })

    if recommended_policy_id:
        rec_col  = db.collection("recommendations")
        pol_key  = f"policy_{recommended_policy_id.replace('-', '_')}"
        rec_edge = f"rec_{key}_{pol_key}"
        if not rec_col.has(rec_edge):
            rec_col.insert({
                "_key":  rec_edge,
                "_from": f"prospect_nodes/{key}",
                "_to":   f"policies/{pol_key}",
            })

    return f"prospect_nodes/{key}"


def get_knowledge_graph_data() -> dict:
    """Return full graph for frontend visualisation."""
    db = get_arango_db()
    vertices, edges = [], []

    for col_name, v_type in [("policies", "policy"), ("signal_nodes", "signal"),
                              ("prospect_nodes", "prospect")]:
        for doc in db.collection(col_name).all():
            vertices.append({"id": doc["_id"], "type": v_type,
                              "label": doc.get("name") or doc.get("label", ""),
                              "data": doc})

    for col_name in EDGE_COLLECTIONS:
        for doc in db.collection(col_name).all():
            edges.append({"from": doc["_from"], "to": doc["_to"],
                          "type": col_name, "weight": doc.get("weight", 1.0)})

    return {
        "vertices": vertices,
        "edges":    edges,
        "stats": {
            "policy_count":   db.collection("policies").count(),
            "signal_count":   db.collection("signal_nodes").count(),
            "prospect_count": db.collection("prospect_nodes").count(),
            "edge_count":     sum(db.collection(c).count() for c in EDGE_COLLECTIONS),
        },
    }


def _make_key(text: str) -> str:
    """Generate a safe ArangoDB key from any string."""
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:64]
