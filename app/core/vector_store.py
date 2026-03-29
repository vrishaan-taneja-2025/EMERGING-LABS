import json
import os
import threading
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover
    SentenceTransformer = None  # type: ignore


class VectorStoreError(Exception):
    pass


class FaissVectorStore:
    def __init__(
        self,
        model_name: str | None = None,
        index_path: str | None = None,
        metadata_path: str | None = None,
    ):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.index_path = Path(index_path or os.getenv("VECTOR_INDEX_PATH", "app/data/vector.index"))
        self.metadata_path = Path(metadata_path or os.getenv("VECTOR_METADATA_PATH", "app/data/vector_metadata.json"))

        self._lock = threading.RLock()
        self._model: Any = None
        self._index: Any = None
        self._metadata: dict[str, Any] = {"next_id": 1, "items": {}}

        self._ensure_storage_dir()
        self._load_state()

    def _ensure_storage_dir(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_model(self):
        if self._model is not None:
            return
        if np is None:
            raise VectorStoreError("numpy is not installed")
        if SentenceTransformer is None:
            raise VectorStoreError("sentence-transformers is not installed")
        self._model = SentenceTransformer(self.model_name)

    def _encode(self, texts: list[str]) -> np.ndarray:
        self._ensure_model()
        vectors = self._model.encode(  # type: ignore[union-attr]
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        if vectors.ndim == 1:
            vectors = np.expand_dims(vectors, axis=0)
        return np.asarray(vectors, dtype=np.float32)

    def _create_empty_index(self, dimension: int):
        if faiss is None:
            raise VectorStoreError("faiss-cpu is not installed")
        base = faiss.IndexFlatIP(dimension)
        self._index = faiss.IndexIDMap2(base)

    def _load_state(self):
        with self._lock:
            if self.metadata_path.exists():
                with self.metadata_path.open("r", encoding="utf-8") as fp:
                    self._metadata = json.load(fp)

            if self.index_path.exists():
                if faiss is None:
                    raise VectorStoreError("faiss-cpu is not installed")
                self._index = faiss.read_index(str(self.index_path))

    def _persist(self):
        if self._index is not None and faiss is not None:
            faiss.write_index(self._index, str(self.index_path))
        with self.metadata_path.open("w", encoding="utf-8") as fp:
            json.dump(self._metadata, fp)

    def _id_for_external(self, external_id: str) -> int | None:
        for idx, item in self._metadata["items"].items():
            if item["external_id"] == external_id:
                return int(idx)
        return None

    def count(self) -> int:
        with self._lock:
            return len(self._metadata["items"])

    def upsert_documents(self, docs: list[dict[str, Any]]) -> dict[str, Any]:
        if not docs:
            return {"upserted": 0}

        texts = [str(doc["text"]) for doc in docs]
        vectors = self._encode(texts)

        with self._lock:
            if self._index is None:
                self._create_empty_index(vectors.shape[1])

            for row_idx, doc in enumerate(docs):
                external_id = str(doc["external_id"])
                existing_id = self._id_for_external(external_id)

                if existing_id is not None and faiss is not None:
                    self._index.remove_ids(np.array([existing_id], dtype=np.int64))
                    internal_id = existing_id
                else:
                    internal_id = int(self._metadata["next_id"])
                    self._metadata["next_id"] = internal_id + 1

                vector = np.expand_dims(vectors[row_idx], axis=0)
                ids = np.array([internal_id], dtype=np.int64)
                self._index.add_with_ids(vector, ids)

                self._metadata["items"][str(internal_id)] = {
                    "external_id": external_id,
                    "text": texts[row_idx],
                    "metadata": doc.get("metadata") or {},
                }

            self._persist()
            return {"upserted": len(docs), "count": len(self._metadata["items"])}

    def delete_document(self, external_id: str) -> bool:
        with self._lock:
            internal_id = self._id_for_external(external_id)
            if internal_id is None:
                return False

            if self._index is not None and faiss is not None:
                self._index.remove_ids(np.array([internal_id], dtype=np.int64))

            self._metadata["items"].pop(str(internal_id), None)
            self._persist()
            return True

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []

        vector = self._encode([query])
        filters = filters or {}

        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return []

            candidate_k = max(top_k * 5, top_k)
            scores, ids = self._index.search(vector, candidate_k)

            results: list[dict[str, Any]] = []
            for score, idx in zip(scores[0], ids[0]):
                if idx == -1:
                    continue

                item = self._metadata["items"].get(str(int(idx)))
                if not item:
                    continue

                metadata = item.get("metadata") or {}
                if filters and any(metadata.get(key) != value for key, value in filters.items()):
                    continue

                results.append(
                    {
                        "external_id": item["external_id"],
                        "text": item["text"],
                        "metadata": metadata,
                        "score": float(score),
                    }
                )

                if len(results) >= top_k:
                    break

            return results


vector_store = FaissVectorStore()
