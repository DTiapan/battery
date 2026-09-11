from typing import List, Optional
from fastembed import TextEmbedding
from battery.config import EMBEDDING_MODEL

_embedding_instance: Optional[TextEmbedding] = None

def get_embedder() -> TextEmbedding:
    """Returns a lazily initialized TextEmbedding singleton instance."""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = TextEmbedding(model_name=EMBEDDING_MODEL)
    return _embedding_instance

def embed_text(text: str) -> List[float]:
    """Generates a normalized float vector for a single text snippet."""
    embedder = get_embedder()
    embeddings = list(embedder.embed([text]))
    return [float(val) for val in embeddings[0]]

def embed_batch(texts: List[str]) -> List[List[float]]:
    """Generates normalized float vectors for a batch of text snippets."""
    if not texts:
        return []
    embedder = get_embedder()
    embeddings = list(embedder.embed(texts))
    return [[float(val) for val in emb] for emb in embeddings]
