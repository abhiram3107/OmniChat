"""
Simple embedding helper using sentence-transformers.
"""
from typing import List
from sentence_transformers import SentenceTransformer
import os

_EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/e5-small-v2")
_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(_EMBED_MODEL)
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    m = get_model()
    # e5 expects "query: ..." / "passage: ..." formatting for best results
    return m.encode(texts, normalize_embeddings=True).tolist()


def embed_query(q: str) -> List[float]:
    return embed_texts([f"query: {q}"])[0]

