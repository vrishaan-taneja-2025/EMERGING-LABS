from datetime import datetime, timedelta
import json
import os
import re
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth_guard import require_user
from app.core.intent_classifier import IntentClassifierError, intent_classifier
from app.core.vector_store import VectorStoreError, vector_store
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.telemetry_record import TelemetryRecord

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    days: int = Field(default=7, ge=1, le=365)
    top_k: int = Field(default=5, ge=1, le=20)


def _ask_ollama(prompt: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model = os.getenv("OLLAMA_MODEL", "tinyllama")
    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 80,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body)
            raw = str(parsed.get("response") or "").strip()
            if not raw:
                return "No response from Ollama."
            compact = " ".join(raw.split())
            words = compact.split(" ")
            if len(words) > 45:
                compact = " ".join(words[:45]).rstrip(".,;:") + "."
            return compact
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError):
        return "Ollama is unavailable right now."


def _build_ollama_prompt(user_message: str, intent: str, data: dict[str, Any]) -> str:
    compact_data = json.dumps(data, default=str)
    return (
        "You are an operations assistant.\n"
        "Rules:\n"
        "- Use ONLY the provided data.\n"
        "- Do not infer or expand abbreviations/status codes.\n"
        "- If data is missing, say 'Not available in current data'.\n"
        "- Keep response to 1-2 short sentences (max 45 words).\n"
        "- Return ONLY final answer text. Do not include labels like 'User question', 'Data', 'Items', or bullet lists.\n"
        f"Intent: {intent}\n"
        f"User question: {user_message}\n"
        f"Data: {compact_data}\n"
        "Answer:"
    )


def _fallback_answer(intent: str, data: dict[str, Any]) -> str:
    if intent == "temperature_anomaly":
        items = data.get("items") or []
        if not items:
            return "No recent temperature anomalies found in current data."
        first = items[0]
        return (
            f"{len(items)} recent anomaly records found. "
            f"Latest: {first.get('equipment_name', 'Unknown')} with {first.get('anomaly_message', 'anomaly')}."
        )
    if intent == "semantic_search":
        count = int(data.get("count") or 0)
        items = data.get("items") or []
        if count == 0:
            return "No matching equipment found in current data."
        names = []
        for item in items:
            metadata = item.get("metadata") or {}
            if metadata.get("equipment_name"):
                names.append(str(metadata["equipment_name"]))
        unique_names = list(dict.fromkeys(names))
        if unique_names:
            return f"Found {count} matches. Top equipment: {', '.join(unique_names[:3])}."
        return f"Found {count} matching records."
    if data.get("answer"):
        return str(data["answer"])
    if data.get("summary"):
        return str(data["summary"])
    return "Not available in current data."


def _clean_ollama_answer(intent: str, raw_answer: str, data: dict[str, Any]) -> str:
    if not raw_answer:
        return _fallback_answer(intent, data)

    lowered = raw_answer.lower()
    banned_markers = ("user question:", "data:", "items:", "window days", "id:")
    if any(marker in lowered for marker in banned_markers):
        return _fallback_answer(intent, data)

    cleaned = raw_answer.strip().strip("\"' ")
    if not cleaned:
        return _fallback_answer(intent, data)
    return cleaned


def _contains_overheat_hint(text: str) -> bool:
    lowered = text.lower()
    hints = {"overheat", "overheating", "high temp", "hot", "temperature"}
    return any(hint in lowered for hint in hints)


def _temperature_anomaly_items(db: Session, query_text: str, days: int, top_k: int) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    records = (
        db.query(TelemetryRecord, Equipment)
        .join(Equipment, TelemetryRecord.equipment_id == Equipment.id)
        .filter(
            TelemetryRecord.created_at >= cutoff,
            TelemetryRecord.is_anomaly.is_(True),
            TelemetryRecord.temperature.isnot(None),
        )
        .order_by(TelemetryRecord.created_at.desc())
        .limit(max(top_k * 4, top_k))
        .all()
    )

    overheat_only = _contains_overheat_hint(query_text)
    results: list[dict[str, Any]] = []

    for record, equipment in records:
        anomaly_message = (record.anomaly_message or "").lower()
        if overheat_only:
            if "temperature" not in anomaly_message and (record.temperature is None or record.temperature < 30):
                continue

        results.append(
            {
                "id": record.id,
                "equipment_id": record.equipment_id,
                "equipment_name": equipment.name,
                "temperature": record.temperature,
                "status": record.status,
                "anomaly_message": record.anomaly_message,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
        )

        if len(results) >= top_k:
            break

    return results


def _equipment_docs_from_db(db: Session) -> list[dict[str, Any]]:
    equipments = db.query(Equipment).all()
    docs: list[dict[str, Any]] = []
    for eq in equipments:
        docs.append(
            {
                "external_id": f"equipment:{eq.id}",
                "text": (
                    f"Equipment {eq.name}. "
                    f"Type: {eq.equipment_type.name if eq.equipment_type else 'unknown'}. "
                    f"Location: {eq.place.name if eq.place else 'unknown'}. "
                    f"Status: {eq.status or 'unknown'}. "
                    f"Serviceability: {eq.serviceability or 'unknown'}. "
                    f"Remarks: {eq.remarks or 'none'}."
                ),
                "metadata": {
                    "kind": "equipment",
                    "equipment_id": eq.id,
                    "equipment_name": eq.name,
                    "equipment_type": eq.equipment_type.name if eq.equipment_type else None,
                    "place": eq.place.name if eq.place else None,
                    "status": eq.status,
                    "serviceability": eq.serviceability,
                },
            }
        )
    return docs


def _semantic_hits(db: Session, query: str, top_k: int) -> list[dict[str, Any]]:
    hits = vector_store.search(query=query, top_k=top_k)
    if hits:
        return hits

    # Bootstrap vector index lazily so semantic queries can work without manual sync.
    docs = _equipment_docs_from_db(db)
    if docs:
        vector_store.upsert_documents(docs)
        hits = vector_store.search(query=query, top_k=top_k)
    return hits


def _tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    normalized = []
    for token in tokens:
        if token == "batteries":
            normalized.append("battery")
        else:
            normalized.append(token)
    return [token for token in normalized if len(token) >= 3]


def _semantic_db_fallback(db: Session, query: str, top_k: int) -> list[dict[str, Any]]:
    tokens = _tokenize_query(query)
    if not tokens:
        return []

    rows = db.query(Equipment).all()
    scored: list[dict[str, Any]] = []
    for eq in rows:
        equipment_type = eq.equipment_type.name if eq.equipment_type else "unknown"
        place = eq.place.name if eq.place else "unknown"
        text = (
            f"Equipment {eq.name}. "
            f"Type: {equipment_type}. "
            f"Location: {place}. "
            f"Status: {eq.status or 'unknown'}. "
            f"Serviceability: {eq.serviceability or 'unknown'}. "
            f"Remarks: {eq.remarks or 'none'}."
        )
        lowered = text.lower()
        score = sum(1 for token in tokens if token in lowered)
        if score == 0:
            continue

        scored.append(
            {
                "external_id": f"equipment:{eq.id}",
                "text": text,
                "metadata": {
                    "kind": "equipment",
                    "equipment_id": eq.id,
                    "equipment_name": eq.name,
                    "equipment_type": equipment_type,
                    "place": place,
                    "status": eq.status,
                    "serviceability": eq.serviceability,
                },
                "score": float(score),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _semantic_hits_with_fallback(db: Session, query: str, top_k: int) -> list[dict[str, Any]]:
    try:
        hits = _semantic_hits(db=db, query=query, top_k=top_k)
    except VectorStoreError:
        hits = []

    if hits:
        return hits
    return _semantic_db_fallback(db=db, query=query, top_k=top_k)


def _is_anomaly_trend_query(text: str) -> bool:
    lowered = text.lower()
    anomaly_words = {"anomaly", "anomalies", "alert", "alerts", "overheat", "overheating"}
    trend_words = {"trend", "recent", "summary", "summarize", "last", "days"}
    return any(word in lowered for word in anomaly_words) and any(word in lowered for word in trend_words)


def _anomaly_trend_result(db: Session, days: int, top_k: int) -> dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    total_count = (
        db.query(func.count(TelemetryRecord.id))
        .filter(
            TelemetryRecord.created_at >= cutoff,
            TelemetryRecord.is_anomaly.is_(True),
        )
        .scalar()
    ) or 0

    trend_rows = (
        db.query(
            func.date(TelemetryRecord.created_at).label("day"),
            func.count(TelemetryRecord.id).label("count"),
        )
        .filter(
            TelemetryRecord.created_at >= cutoff,
            TelemetryRecord.is_anomaly.is_(True),
        )
        .group_by(func.date(TelemetryRecord.created_at))
        .order_by(func.date(TelemetryRecord.created_at).asc())
        .all()
    )

    recent_rows = (
        db.query(TelemetryRecord, Equipment)
        .join(Equipment, TelemetryRecord.equipment_id == Equipment.id)
        .filter(
            TelemetryRecord.created_at >= cutoff,
            TelemetryRecord.is_anomaly.is_(True),
        )
        .order_by(TelemetryRecord.created_at.desc())
        .limit(top_k)
        .all()
    )

    trend = [{"day": str(row.day), "count": int(row.count)} for row in trend_rows]
    recent_items = [
        {
            "equipment_id": record.equipment_id,
            "equipment_name": equipment.name,
            "temperature": record.temperature,
            "status": record.status,
            "anomaly_message": record.anomaly_message,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        for record, equipment in recent_rows
    ]

    if trend:
        peak = max(trend, key=lambda item: item["count"])
        answer = (
            f"{total_count} anomalies in the last {days} days. "
            f"Peak day: {peak['day']} with {peak['count']} anomalies."
        )
    else:
        answer = f"No anomalies recorded in the last {days} days."

    return {
        "answer": answer,
        "window_days": days,
        "count": int(total_count),
        "trend": trend,
        "recent_items": recent_items,
    }


def _rag_summary(question: str, hits: list[dict[str, Any]]) -> str:
    if not hits:
        return f"I could not find relevant indexed context for '{question}'."

    named_items = []
    for hit in hits:
        metadata = hit.get("metadata") or {}
        equipment_name = metadata.get("equipment_name")
        status = metadata.get("status")
        if equipment_name:
            if status:
                named_items.append(f"{equipment_name} ({status})")
            else:
                named_items.append(str(equipment_name))

    if named_items:
        unique_names = list(dict.fromkeys(named_items))
        return f"Relevant equipment based on your query: {', '.join(unique_names[:5])}."

    return f"Found {len(hits)} relevant context entries for '{question}'."


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db), user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    try:
        classification = intent_classifier.classify(payload.message)
    except IntentClassifierError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    intent = classification["intent"]

    if intent == "temperature_anomaly":
        items = _temperature_anomaly_items(
            db=db,
            query_text=payload.message,
            days=payload.days,
            top_k=payload.top_k,
        )
        result_data = {
            "window_days": payload.days,
            "count": len(items),
            "items": items,
        }
        answer = _clean_ollama_answer(
            intent,
            _ask_ollama(_build_ollama_prompt(payload.message, intent, result_data)),
            result_data,
        )
        return {"intent": intent, "answer": answer, "data": result_data}

    if intent == "semantic_search":
        hits = _semantic_hits_with_fallback(db=db, query=payload.message, top_k=payload.top_k)
        result_data = {
            "count": len(hits),
            "items": hits,
        }
        answer = _clean_ollama_answer(
            intent,
            _ask_ollama(_build_ollama_prompt(payload.message, intent, result_data)),
            result_data,
        )
        return {"intent": intent, "answer": answer, "data": result_data}

    if _is_anomaly_trend_query(payload.message):
        result_data = _anomaly_trend_result(db=db, days=payload.days, top_k=payload.top_k)
        answer = _clean_ollama_answer(
            "rag_query",
            _ask_ollama(_build_ollama_prompt(payload.message, "rag_query", result_data)),
            result_data,
        )
        return {"intent": "rag_query", "answer": answer, "data": result_data}

    hits = _semantic_hits_with_fallback(db=db, query=payload.message, top_k=payload.top_k)
    result_data = {
        "summary": _rag_summary(payload.message, hits),
        "count": len(hits),
        "context": [hit.get("text") for hit in hits],
        "hits": hits,
    }
    answer = _clean_ollama_answer(
        "rag_query",
        _ask_ollama(_build_ollama_prompt(payload.message, "rag_query", result_data)),
        result_data,
    )
    return {"intent": "rag_query", "answer": answer, "data": result_data}
