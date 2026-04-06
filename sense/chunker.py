"""
chunker.py
Splits cleaned post body into overlapping token chunks.
Tags each chunk with post_id and farm name for Qdrant storage.

Uses a word-level approximation for token counting (1 word ≈ 1 token)
which is accurate enough for chunk boundary purposes and avoids a
tokenizer dependency at this stage.
"""


def _word_tokenize(text: str) -> list[str]:
    return text.split()


def chunk_text(
    text: str,
    chunk_size: int = 200,
    chunk_overlap: int = 20,
) -> list[str]:
    """Split text into overlapping chunks by word count."""
    words = _word_tokenize(text)
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - chunk_overlap
    return chunks


def chunk_post(post: dict, config: dict) -> list[dict]:
    """
    Takes a classified post dict and returns a list of chunk dicts
    ready for the embedder.
    """
    sense_cfg = config["sense"]
    farm_name = config["farm"]["name"]
    post_id = post["post_id"]

    # Combine title and body so the theory framing is in every chunk window
    full_text = f"{post['title']}. {post['body']}".strip()
    if not full_text or full_text == ".":
        return []

    raw_chunks = chunk_text(
        full_text,
        chunk_size=sense_cfg["chunk_size"],
        chunk_overlap=sense_cfg["chunk_overlap"],
    )

    return [
        {
            "chunk_id": f"{post_id}_{i}",
            "post_id": post_id,
            "farm": farm_name,
            "subreddit": post["subreddit"],
            "text": chunk,
            "chunk_index": i,
        }
        for i, chunk in enumerate(raw_chunks)
    ]


def run(classified_posts: list[dict], config: dict) -> list[dict]:
    """Entry point called by main.py."""
    all_chunks = []
    for post in classified_posts:
        all_chunks.extend(chunk_post(post, config))
    print(f"[chunker] Produced {len(all_chunks)} chunks from {len(classified_posts)} posts.")
    return all_chunks


if __name__ == "__main__":
    import json
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    with open("output/classified_posts.json") as f:
        posts = json.load(f)

    chunks = run(posts, cfg)
    with open("output/chunks.json", "w") as f:
        json.dump(chunks, f, indent=2)
    print(f"Wrote {len(chunks)} chunks to output/chunks.json")
