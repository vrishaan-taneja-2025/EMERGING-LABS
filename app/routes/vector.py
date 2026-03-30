from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_guard import require_user
from app.core.vector_store import VectorStoreError, vector_store
from app.db.session import get_db
from app.models.equipment import Equipment

router = APIRouter(prefix="/api/vector", tags=["Vector DB"])


class VectorDocument(BaseModel):
    external_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] | None = None


class VectorUpsertRequest(BaseModel):
    documents: list[VectorDocument]


class VectorSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] | None = None


class RagQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] | None = None
    system_prompt: str | None = None


def _to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return]
    return model.dict()  # type: ignore[no-any-return]


@router.get("/health")
def vector_health(user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    return {
        "provider": "faiss",
        "embedding_backend": "fastembed",
        "embedding_model": vector_store.model_name,
        "count": vector_store.count(),
    }


@router.post("/upsert")
def upsert_vectors(payload: VectorUpsertRequest, user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    try:
        result = vector_store.upsert_documents([_to_dict(doc) for doc in payload.documents])
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return result


@router.post("/search")
def search_vectors(payload: VectorSearchRequest, user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    try:
        results = vector_store.search(
            query=payload.query,
            top_k=payload.top_k,
            filters=payload.filters,
        )
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"results": results}


@router.delete("/documents/{external_id}")
def delete_vector(external_id: str, user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    try:
        removed = vector_store.delete_document(external_id)
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"deleted": True, "external_id": external_id}


@router.post("/sync/equipment")
def sync_equipment_vectors(
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    if hasattr(user, "status_code"):
        return user

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

    try:
        result = vector_store.upsert_documents(docs)
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result["synced_kind"] = "equipment"
    return result


@router.post("/rag/query")
def rag_query(payload: RagQueryRequest, user=Depends(require_user)):
    if hasattr(user, "status_code"):
        return user

    try:
        hits = vector_store.search(
            query=payload.question,
            top_k=payload.top_k,
            filters=payload.filters,
        )
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    default_system_prompt = (
        "You are an assistant for datacenter operations. "
        "Answer using only the provided context. "
        "If the context is insufficient, say that explicitly."
    )
    system_prompt = payload.system_prompt or default_system_prompt

    context_lines: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        context_lines.append(
            f"[{idx}] score={hit['score']:.4f} external_id={hit['external_id']}\n{hit['text']}"
        )

    context_block = "\n\n".join(context_lines) if context_lines else "No relevant context found."
    user_prompt = (
        f"Question: {payload.question}\n\n"
        f"Retrieved Context:\n{context_block}\n\n"
        "Provide a concise and factual answer."
    )

    return {
        "question": payload.question,
        "retrieval": {
            "top_k": payload.top_k,
            "filters": payload.filters or {},
            "hits": hits,
        },
        "model_payload": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        },
    }
