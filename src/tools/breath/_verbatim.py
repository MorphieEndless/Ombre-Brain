"""Stored-content rendering for breath compatibility.

This module is intentionally small so the compatibility patch can be removed
without touching retrieval, ranking, or bucket storage.
"""

from utils import count_tokens_approx


def stored_bucket_content(bucket: dict) -> str:
    """Return the bucket body without stripping or normalizing any character."""
    content = bucket.get("content", "")
    if not isinstance(content, str):
        raise TypeError("bucket content must be a string")
    return content


def render_stored_bucket(bucket: dict, metadata_header: str) -> tuple[str, int]:
    """Render metadata around, but never inside, the stored bucket body."""
    # Temporary compatibility patch: force breath to return stored bucket
    # content verbatim. Remove after upstream breath fixes content reconstruction.
    rendered = f"{metadata_header}\n{stored_bucket_content(bucket)}"
    return rendered, count_tokens_approx(rendered)
