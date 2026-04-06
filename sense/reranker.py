"""
reranker.py
Two-stage retrieval:
  1. Dense vector search via Qdrant (top_k_retrieval candidates)
  2. Cross-encoder reranking with ms-marco-MiniLM-L-6-v2 (top_k_rerank final)

Returns top_k_rerank chunk dicts ranked by cross-encoder relevance score.
"""

from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient


_EMBED_MODEL = "all-MiniLM-L6-v2"
_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_client() -> QdrantClient:
    return QdrantClient(path="./qdrant_storage")


def retrieve_and_rerank(query: str, config: dict) -> list[dict]:
    """
    Given a query string, return the top_k_rerank most relevant chunks.

    Args:
        query: Free-text query, usually the theory topic / core claim.
        config: Parsed config.yaml dict.

    Returns:
        List of chunk dicts sorted by cross-encoder score, highest first.
    """
    farm_name = config["farm"]["name"]
    top_k_retrieval = config["sense"]["top_k_retrieval"]
    top_k_rerank = config["sense"]["top_k_rerank"]

    # Stage 1: dense retrieval
    embed_model = SentenceTransformer(_EMBED_MODEL)
    query_vec = embed_model.encode(query).tolist()

    client = _get_client()
    result = client.query_points(
        collection_name=farm_name,
        query=query_vec,
        limit=top_k_retrieval,
        with_payload=True,
    )

    hits = result.points
    if not hits:
        return []

    candidates = [h.payload for h in hits]

    # Stage 2: cross-encoder reranking
    cross_encoder = CrossEncoder(_RERANK_MODEL)
    pairs = [(query, c["text"]) for c in candidates]
    scores = cross_encoder.predict(pairs)

    ranked = sorted(
        zip(candidates, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    return [chunk for chunk, _ in ranked[:top_k_rerank]]


def run(query: str, config: dict) -> list[dict]:
    """Entry point called by context_builder.py."""
    chunks = retrieve_and_rerank(query, config)
    print(f"[reranker] Returned {len(chunks)} canon chunks for query: '{query[:60]}...'")
    return chunks


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    q = "Why haven't we detected any alien civilisations despite billions of potential stars?"
    results = run(q, cfg)
    for i, r in enumerate(results):
        print(f"\n--- Chunk {i+1} [{r['subreddit']}] ---")
        print(r["text"][:300])
