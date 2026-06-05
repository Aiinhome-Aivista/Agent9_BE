"""
ChromaDB Client — ARIES AI Vector Store
=========================================
Collections:
  policy_documents   Full policy text → embeddings (semantic search)
  prospect_contexts  Prospect behaviour text → embeddings (matching)
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from .config import get_settings
import logging

logger = logging.getLogger("aries.chroma")
settings = get_settings()
print("MISTRAL KEY:", settings.MISTRAL_API_KEY)
from typing import Optional

_client = None
_embedder: SentenceTransformer | None = None


def get_chroma() -> chromadb.HttpClient:
    global _client
    if _client is None:
        raise RuntimeError("ChromaDB not initialised.")
    return _client


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        raise RuntimeError("Embedder not initialised.")
    return _embedder


# def init_chroma() -> None:
#     global _client, _embedder
#     try:
#         _client = chromadb.HttpClient(
#             host=settings.CHROMA_HOST,
#             # port=settings.CHROMA_PORT,
#             settings=ChromaSettings(anonymized_telemetry=False),
#         )
#         _client.heartbeat()

#         # Ensure collections exist
#         for col in [settings.CHROMA_POLICY_COLLECTION, settings.CHROMA_PROSPECT_COLLECTION]:
#             _client.get_or_create_collection(
#                 name=col,
#                 metadata={"hnsw:space": "cosine"},
#             )

#         # Load sentence transformer (downloads once, then cached)
#         _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)

#         logger.info("ChromaDB ready at %s:%s", settings.CHROMA_HOST, settings.CHROMA_PORT)
#         logger.info("Embedding model '%s' loaded.", settings.EMBEDDING_MODEL)
#     except Exception as exc:
#         logger.error("ChromaDB init failed: %s", exc)
#         raise

def init_chroma() -> None:
    global _client, _embedder

    try:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_HOST,
            settings=ChromaSettings(
                anonymized_telemetry=False
            ),
        )

        # Ensure collections exist
        for col in [
            settings.CHROMA_POLICY_COLLECTION,
            settings.CHROMA_PROSPECT_COLLECTION,
        ]:
            _client.get_or_create_collection(
                name=col,
                metadata={"hnsw:space": "cosine"},
            )

        _embedder = SentenceTransformer(
            settings.EMBEDDING_MODEL
        )

        logger.info(
            "ChromaDB persistent storage ready at %s",
            settings.CHROMA_HOST
        )

        logger.info(
            "Embedding model '%s' loaded.",
            settings.EMBEDDING_MODEL
        )

    except Exception as exc:
        logger.error("ChromaDB init failed: %s", exc)
        raise
# ── Policy Indexing ────────────────────────────────────────

def index_policy(policy_id: str, name: str, policy_type: str,
                 features: list[str], targets: list[str],
                 full_text: str = "") -> None:
    """Embed and store policy in the policy_documents collection."""
    client = get_chroma()
    embedder = get_embedder()
    col = client.get_collection(settings.CHROMA_POLICY_COLLECTION)

    # Build rich text for embedding
    text = (
        f"Policy: {name}\n"
        f"Type: {policy_type}\n"
        f"Features: {', '.join(features)}\n"
        f"Target audience: {', '.join(targets)}\n"
        f"{full_text}"
    ).strip()

    embedding = embedder.encode(text).tolist()

    col.upsert(
        ids=[policy_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[{"name": name, "type": policy_type,
                    "features": ";".join(features),
                    "targets":  ";".join(targets)}],
    )
    logger.info("Indexed policy '%s' in ChromaDB.", name)


def index_prospect_context(prospect_id: str, name: str,
                           signals: list[str], context: str) -> None:
    """Embed and store prospect behavioural context."""
    client = get_chroma()
    embedder = get_embedder()
    col = client.get_collection(settings.CHROMA_PROSPECT_COLLECTION)

    text = f"Prospect: {name}\nSignals: {', '.join(signals)}\nContext: {context}"
    embedding = embedder.encode(text).tolist()

    col.upsert(
        ids=[prospect_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[{"name": name, "signals": ";".join(signals)}],
    )


def search_matching_policies(prospect_signals: list[str],
                             n_results: int = 5) -> list[dict]:
    """Semantic search — find best matching policies for a prospect's signals."""
    client = get_chroma()
    embedder = get_embedder()
    col = client.get_collection(settings.CHROMA_POLICY_COLLECTION)

    query_text = "Customer signals: " + ", ".join(prospect_signals)
    query_embedding = embedder.encode(query_text).tolist()

    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, col.count() or 1),
        include=["documents", "metadatas", "distances"],
    )

    matches = []
    for i, (doc, meta, dist) in enumerate(
        zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
    ):
        matches.append({
            "rank":        i + 1,
            "name":        meta.get("name", ""),
            "type":        meta.get("type", ""),
            "similarity":  round(1 - dist, 3),
            "document":    doc,
        })
    return matches


def search_similar_prospects(prospect_context: str, n_results: int = 5) -> list[dict]:
    """Find similar prospects (for pattern matching / campaign targeting)."""
    client = get_chroma()
    embedder = get_embedder()
    col = client.get_collection(settings.CHROMA_PROSPECT_COLLECTION)

    if col.count() == 0:
        return []

    embedding = embedder.encode(prospect_context).tolist()
    results = col.query(
        query_embeddings=[embedding],
        n_results=min(n_results, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    return [
        {
            "name":       meta.get("name", ""),
            "similarity": round(1 - dist, 3),
            "signals":    meta.get("signals", "").split(";"),
        }
        for meta, dist in zip(results["metadatas"][0], results["distances"][0])
    ]


def get_collection_stats() -> dict:
    client = get_chroma()
    return {
        "policy_count":   client.get_collection(settings.CHROMA_POLICY_COLLECTION).count(),
        "prospect_count": client.get_collection(settings.CHROMA_PROSPECT_COLLECTION).count(),
        "embedding_model": settings.EMBEDDING_MODEL,
    }
