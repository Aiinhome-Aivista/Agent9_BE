"""
Mistral LLM Client — ARIES Intelligence Layer
===============================================
All AI-powered features use Mistral Small Latest:
  - CSV field mapping & prospect extraction
  - Policy document feature extraction
  - Prospect propensity scoring & ranking
  - Deep prospect analysis & pitch generation
  - Renewal risk scoring
  - Personalised outreach message drafting
"""

import json
import re
import logging
# from mistralai import Mistral
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from .config import get_settings

logger = logging.getLogger("aries.mistral")
settings = get_settings()

_client: MistralClient | None = None


def get_mistral() -> MistralClient:
    global _client
    if _client is None:
        _client = MistralClient(api_key=settings.MISTRAL_API_KEY)
    return _client


async def _chat(system: str, user: str, json_mode: bool = False) -> str:
    """Core wrapper around Mistral chat completion."""

    client = get_mistral()

    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]

    kwargs = {
        "model": settings.MISTRAL_MODEL,
        "messages": messages,
        "max_tokens": settings.MISTRAL_MAX_TOKENS,
        "temperature": settings.MISTRAL_TEMPERATURE,
    }
    
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat(**kwargs)

    content = response.choices[0].message.content or ""

    # Remove markdown wrappers
    content = re.sub(r"```json|```", "", content).strip()

    return content

# def _parse_json(text: str) -> dict | list:
#     clean = re.sub(r"```(?:json)?|```", "", text).strip()
#     return json.loads(clean)
def _parse_json(text: str) -> dict | list:
    """
    Safely extract JSON from Mistral responses.
    """

    try:
        # Remove markdown wrappers
        clean = re.sub(r"```json|```", "", text).strip()

        # Extract first JSON object or array
        match = re.search(r"(\{.*\}|\[.*\])", clean, re.DOTALL)

        if not match:
            raise ValueError("No JSON found in response")

        json_text = match.group(1)

        return json.loads(json_text)

    except Exception as exc:
        logger.error("JSON Parse Error: %s", exc)
        logger.error("Raw LLM response:\n%s", text)

        raise ValueError(
            f"Invalid JSON returned from Mistral: {exc}"
        )

# ── 1. CSV Analysis ────────────────────────────────────────

async def analyze_csv(csv_content: str, source_name: str = "upload.csv") -> dict:
    """
    Analyze raw CSV text → field mappings + extracted prospects.
    Returns JSON conforming to CSVAnalyzeResponse schema.
    """
    system = """You are the Connector Agent for an insurance AI platform.
Analyze the provided CSV data and return ONLY a valid JSON object with this exact structure:
{
  "detected_fields": [...column names found...],
  "mappings": {"csv_column": "prospect_table_field"},
  "missing_fields": [...important fields not found...],
  "sample_prospects": [{
    "name": "", "email": "", "age": null, "location": "",
    "income_bracket": "", "behavioral_signals": [], "life_events": []
  }],
  "record_count": 0,
  "ingestion_summary": "one sentence summary"
}

Standard prospect_table_field values: name, email, phone, age, location,
income_bracket, occupation, behavioral_signals, life_events, existing_policies.
Extract up to 3 sample prospects from the data."""

    user = f"CSV file: {source_name}\n\nContent (first 3000 chars):\n{csv_content[:3000]}"
    raw = await _chat(system, user, json_mode=True)
    return _parse_json(raw)


# ── 2. Policy Document Extraction ─────────────────────────

async def extract_policy_features(policy_text: str, policy_name: str) -> dict:
    """
    Extract structured features from a policy document.
    Returns: {features, propensity_targets, coverage_summary, key_exclusions}
    """
    system = """You are the Policy Warehouse Agent for an insurance platform.
Extract structured information from the insurance policy document and return ONLY valid JSON:
{
  "features": ["key feature 1", ...],
  "propensity_targets": ["target signal 1", ...],
  "coverage_summary": "2-sentence summary",
  "key_exclusions": ["exclusion 1", ...],
  "ideal_customer_profile": "1 sentence description",
  "usp": "unique selling point in 1 sentence"
}"""

    user = f"Policy name: {policy_name}\n\nDocument content:\n{policy_text[:4000]}"
    raw = await _chat(system, user, json_mode=True)
    return _parse_json(raw)


async def analyze_policy_document(policy_text: str, filename: str) -> dict:
    """
    Analyze a policy document and return structured policy metadata,
    preview text, and a relevance score.
    """
    system = """You are an insurance policy document extraction assistant.
Analyze the document text and return ONLY valid JSON with the following fields:
{
  "name": "",
  "policy_type": "Life|Health|Motor|Property|Commercial|Travel",
  "coverage_range": "",
  "premium_range": "",
  "eligibility": "",
  "features": ["feature 1", ...],
  "propensity_targets": ["target signal 1", ...],
  "preview": "One or two sentence summary of the policy content.",
  "relevance_score": 0
}
If a field is unavailable, return an empty string or empty list.
If coverage_range, premium_range, or eligibility data are present, extract them exactly as found; for example:
  "coverage_range": "5,00,00,000",
  "premium_range": "6,500",
  "eligibility": "18 - 60"
The relevance_score must be a number from 0 to 100 indicating the likelihood this is an insurance policy document."""

    user = f"Filename: {filename}\n\nDocument content:\n{policy_text[:10000]}"
    raw = await _chat(system, user, json_mode=True)
    return _parse_json(raw)


# ── 3. Prospect Scoring & Ranking ─────────────────────────

async def score_and_rank_prospects(
    prospects_data: list[dict],
    available_policies: list[dict],
    priority_type: str = "new_policy",
) -> list[dict]:
    """
    Score and rank prospects against available policies.
    Returns sorted list with propensity_score, recommended_product,
    urgency_level, outreach_channel, ai_context.
    """
    system = f"""You are the Prospect Intelligence Agent for an insurance distribution platform.
Analyze each prospect against the available policies.

Return ONLY raw valid JSON array.
DO NOT include markdown.
DO NOT include explanations.
DO NOT truncate output.
Each prospect object must include:
  "id", "propensity_score" (0-100 float), "recommended_product",
  "urgency_level" (Critical/High/Medium/Low), "outreach_channel",
  "ai_context" (2-3 sentence explanation of why this prospect is a match),
  "behavioral_signals" (list of observed signal strings)

Priority type: {priority_type}
Sort by propensity_score descending."""

    user = (
        f"Prospects ({len(prospects_data)} total):\n"
        f"{json.dumps(prospects_data[:5], indent=2)}\n\n"
        f"Available policies:\n{json.dumps(available_policies, indent=2)}"
    )
    raw = await _chat(system, user, json_mode=True)
    result = _parse_json(raw)
    return result if isinstance(result, list) else result.get("prospects", [])


# ── 4. Deep Prospect Analysis ─────────────────────────────

async def analyze_prospect_deep(
    prospect: dict,
    matched_policies: list[dict],
    analysis_type: str = "full",
) -> dict:
    """
    Generate deep, actionable analysis for a single prospect.
    Returns structured insight for the sales/RM agent.
    """
    system = """You are the Prospect Intelligence Agent providing a deep analysis for a field sales agent.
Be specific, practical, and concise. Return ONLY valid JSON:
{
  "analysis": "comprehensive 3-4 paragraph analysis",
  "key_insights": ["insight 1", "insight 2", "insight 3"],
  "talking_points": ["opening line", "value proposition", "handle objection", "close"],
  "risk_factors": ["risk 1", ...],
  "next_action": "specific next step",
  "best_time": "recommended outreach timing",
  "objection_handlers": {"likely objection": "response"},
  "cross_sell_opportunity": "next product to pitch after conversion"
}"""

    user = (
        f"Prospect details:\n{json.dumps(prospect, indent=2)}\n\n"
        f"Matched policies:\n{json.dumps(matched_policies, indent=2)}\n\n"
        f"Analysis type: {analysis_type}"
    )
    raw = await _chat(system, user, json_mode=True)
    return _parse_json(raw)


# ── 5. Renewal Risk Scoring ────────────────────────────────

async def score_renewal_risk(
    renewal_data: list[dict],
    policy_details: dict,
) -> list[dict]:
    """
    Assess churn risk and retention approach for renewal prospects.
    Returns each renewal with retention_score, churn_risk, renewal_action, ai_context.
    """
    system = """You are the Renewal Intelligence Agent. Score churn risk for each renewal prospect.
Return ONLY valid JSON array. Each item must include:
  "id", "retention_score" (0-100, higher = easier to retain),
  "churn_risk" (High/Medium/Low), "renewal_action" (specific action string),
  "urgency_level" (Critical/High/Medium/Low), "ai_context" (2-sentence insight),
  "recommended_offer" (what incentive or product change to offer)"""

    user = (
        f"Renewal prospects:\n{json.dumps(renewal_data, indent=2)}\n\n"
        f"Policy context:\n{json.dumps(policy_details, indent=2)}"
    )
    raw = await _chat(system, user, json_mode=True)
    result = _parse_json(raw)
    return result if isinstance(result, list) else result.get("renewals", [])


# ── 6. Outreach Message Drafting ──────────────────────────

async def draft_outreach_message(
    prospect: dict,
    policy: dict,
    channel: str,
    tone: str = "professional_warm",
) -> str:
    """Generate personalised outreach message for a prospect."""
    system = f"""You are a senior insurance relationship manager drafting a personalised outreach message.
Channel: {channel}. Tone: {tone}.
Write a compelling, non-generic message. For email include subject + body.
Keep it concise: email ≤150 words, WhatsApp/SMS ≤60 words, phone script ≤120 words."""

    user = (
        f"Prospect: {prospect.get('name')}, {prospect.get('age')}y, {prospect.get('location')}\n"
        f"Signals: {', '.join(prospect.get('behavioral_signals', []))}\n"
        f"Recommended policy: {policy.get('name')}\n"
        f"Context: {prospect.get('ai_context', '')}"
    )
    return await _chat(system, user)
