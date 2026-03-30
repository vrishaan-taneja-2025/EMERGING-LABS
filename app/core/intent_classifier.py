import os
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore

try:
    from fastembed import TextEmbedding
except ImportError:  # pragma: no cover
    TextEmbedding = None  # type: ignore


class IntentClassifierError(Exception):
    pass


class IntentClassifier:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv(
            "INTENT_EMBEDDING_MODEL",
            "BAAI/bge-small-en-v1.5",
        )
        self._model: Any = None
        self._intent_vectors: dict[str, Any] = {}
        self._keyword_hints: dict[str, set[str]] = {
            "temperature_anomaly": {
                "overheat",
                "overheating",
                "temperature",
                "hot",
                "anomaly",
                "anomalies",
                "spike",
                "alert",
                "alerts",
            },
            "semantic_search": {
                "find",
                "search",
                "lookup",
                "show",
                "list",
                "equipment",
                "battery",
                "ups",
                "cooling",
                "server",
            },
            "rag_query": {
                "summarize",
                "summary",
                "explain",
                "why",
                "insight",
                "overview",
                "what",
                "how",
            },
        }
        self._ensure_model()
        self._build_intent_vectors()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if np is None:
            raise IntentClassifierError("numpy is not installed")
        if TextEmbedding is None:
            raise IntentClassifierError("fastembed is not installed")
        self._model = TextEmbedding(model_name=self.model_name)

    def _embed_texts(self, texts: list[str]) -> Any:
        self._ensure_model()
        vectors = list(self._model.embed(texts))  # type: ignore[union-attr]
        return np.asarray(vectors, dtype=np.float32)

    def _normalize(self, vec: Any) -> Any:
        denom = np.linalg.norm(vec)
        if denom == 0:
            return vec
        return vec / denom

    def _build_intent_vectors(self) -> None:
        examples: dict[str, list[str]] = {
            "temperature_anomaly": [
                "show recent temperature anomalies",
                "temperature spikes in the last week",
                "overheating alerts",
                "temperature sensor anomaly",
                "high temperature anomalies",
            ],
            "semantic_search": [
                "find equipment with battery issues",
                "search for UPS in hall",
                "lookup equipment details",
                "search by description",
                "find cooling units with status",
            ],
            "rag_query": [
                "summarize current anomalies",
                "why are alerts happening",
                "give insights about equipment",
                "what is the status of cooling units",
                "explain recent alerts",
            ],
        }

        for intent, texts in examples.items():
            vectors = self._embed_texts(texts)
            centroid = vectors.mean(axis=0)
            self._intent_vectors[intent] = self._normalize(centroid)

    def classify(self, text: str) -> dict[str, Any]:
        if not text.strip():
            raise IntentClassifierError("query is empty")
        lowered = text.lower()
        keyword_scores: dict[str, float] = {}
        for intent, keywords in self._keyword_hints.items():
            keyword_scores[intent] = float(sum(1 for word in keywords if word in lowered))

        vector = self._normalize(self._embed_texts([text])[0])
        embedding_scores = {
            intent: float(np.dot(vector, intent_vec))
            for intent, intent_vec in self._intent_vectors.items()
        }
        combined_scores = {
            intent: embedding_scores[intent] + (0.12 * keyword_scores[intent])
            for intent in self._intent_vectors
        }
        best_intent = max(combined_scores, key=combined_scores.get)
        return {
            "intent": best_intent,
            "scores": combined_scores,
            "embedding_scores": embedding_scores,
            "keyword_scores": keyword_scores,
        }


intent_classifier = IntentClassifier()
