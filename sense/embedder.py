"""
embedder.py
Embeds text chunks using sentence-transformers all-MiniLM-L6-v2.
Stores vectors in a local Qdrant collection named after the farm.
Deduplicates by post_id so re-runs don't re-embed known content.
"""

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)


_MODEL_NAME = "all-MiniLM-L6-v2"
_VECTOR_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_client(config: dict) -> QdrantClient:
    # Qdrant runs locally in-process by default (no server needed for dev)
    return QdrantClient(path="./qdrant_storage")


def _ensure_collection(client: QdrantClient, collection_name: str) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=_VECTOR_DIM, distance=Distance.COSINE),
        )


def _get_embedded_post_ids(client: QdrantClient, collection_name: str) -> set[str]:
    """Scroll through all points to collect already-indexed post IDs."""
    known = set()
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=None,
            limit=1000,
            offset=offset,
            with_payload=["post_id"],
            with_vectors=False,
        )
        for r in records:
            known.add(r.payload["post_id"])
        if offset is None:
            break
    return known


def embed_and_store(chunks: list[dict], config: dict) -> None:
    """
    Embed all chunks and upsert into Qdrant.
    Skips chunks whose post_id is already in the collection.
    """
    farm_name = config["farm"]["name"]
    client = _get_client(config)
    _ensure_collection(client, farm_name)

    known_ids = _get_embedded_post_ids(client, farm_name)
    new_chunks = [c for c in chunks if c["post_id"] not in known_ids]

    if not new_chunks:
        print(f"[embedder] No new chunks to embed (all {len(chunks)} already indexed).")
        return

    model = SentenceTransformer(_MODEL_NAME)
    texts = [c["text"] for c in new_chunks]
    vectors = model.encode(texts, show_progress_bar=True, batch_size=64)

    points = [
        PointStruct(
            id=abs(hash(c["chunk_id"])) % (10 ** 12),  # stable numeric ID from chunk_id
            vector=vectors[i].tolist(),
            payload={
                "chunk_id": c["chunk_id"],
                "post_id": c["post_id"],
                "farm": c["farm"],
                "subreddit": c["subreddit"],
                "text": c["text"],
                "chunk_index": c["chunk_index"],
            },
        )
        for i, c in enumerate(new_chunks)
    ]

    client.upsert(collection_name=farm_name, points=points)
    print(f"[embedder] Embedded and stored {len(points)} new chunks into '{farm_name}' collection.")


def run(chunks: list[dict], config: dict) -> None:
    """Entry point called by main.py."""
    embed_and_store(chunks, config)


if __name__ == "__main__":
    import json
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    with open("output/chunks.json") as f:
        chunks = json.load(f)

    run(chunks, cfg)
