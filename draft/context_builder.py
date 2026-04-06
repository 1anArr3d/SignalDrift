"""
context_builder.py
Assembles the final context object passed to all LLM draft agents.

Fields:
  the_theory  — cleaned post body (the raw theory being explored)
  the_debate  — classified comment buckets from comment_extractor
  the_canon   — top 5 reranked chunks from sense layer
  the_signal  — engagement metadata (upvote_ratio, num_comments)
"""

from sense import reranker


def build_context(post: dict, config: dict) -> dict:
    """
    Args:
        post: A classified post dict (output of comment_extractor.run).
        config: Parsed config.yaml dict.

    Returns:
        Context object dict with four canonical fields.
    """
    query = post.get("core_claim") or post.get("title", "")
    canon_chunks = reranker.run(query, config)

    return {
        "the_theory": {
            "title": post["title"],
            "body": post["body"],
            "core_claim": post.get("core_claim", ""),
            "subreddit": post["subreddit"],
            "post_id": post["post_id"],
        },
        "the_debate": post.get("classified_comments", {}),
        "the_canon": canon_chunks,
        "the_signal": {
            "upvote_ratio": post["upvote_ratio"],
            "num_comments": post["num_comments"],
            "score": post["score"],
        },
    }


def run(post: dict, config: dict) -> dict:
    """Entry point called by main.py."""
    ctx = build_context(post, config)
    print(f"[context_builder] Built context for post '{post['post_id']}' "
          f"with {len(ctx['the_canon'])} canon chunks.")
    return ctx
