"""按桶 ID 与精确标题读取单条记忆背后的不可变原文证据。"""

from __future__ import annotations

import unicodedata

from utils import count_tokens_approx

from .. import _runtime as rt
from .._common import stored_data_marker


_DEFAULT_MAX_TOKENS = 6000
_MAX_MAX_TOKENS = 20000


def _normalized_title(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip()


async def dispatch(
    bucket_id: str,
    expected_title: str,
    scope: str = "event",
    cursor: int = 0,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> str:
    bucket_id = str(bucket_id or "").strip()
    expected_title = _normalized_title(expected_title)
    scope = str(scope or "event").strip().lower()
    if not bucket_id or not expected_title:
        return "source_read 需要 bucket_id 和 expected_title。"
    if scope not in {"event", "full_source"}:
        return "scope 仅支持 event 或 full_source。"
    try:
        cursor = max(0, int(cursor))
        max_tokens = max(200, min(_MAX_MAX_TOKENS, int(max_tokens)))
    except (TypeError, ValueError, OverflowError):
        return "cursor 和 max_tokens 必须是整数。"

    getter = getattr(rt.bucket_mgr, "get_including_archive", rt.bucket_mgr.get)
    bucket = await getter(bucket_id)
    if not bucket:
        return f"未找到桶 {bucket_id}。"
    metadata = bucket.get("metadata") or {}
    actual_title = _normalized_title(metadata.get("title"))
    if not actual_title:
        return "该桶没有可供精确校验的显式标题，拒绝读取原文。"
    if expected_title != actual_title:
        return "标题不匹配，拒绝读取原文。请使用该桶的精确 title。"

    source_refs = metadata.get("source_refs") or []
    if not source_refs:
        return "该桶没有原文证据引用。"

    chunks: list[str] = []
    try:
        for source_ref in source_refs:
            ref = str(source_ref.get("ref") or "")
            content = rt.source_store.read(ref)
            if scope == "event":
                content = rt.source_store.select_ranges(
                    content, source_ref.get("ranges") or []
                )
            chunks.append(content)
    except (OSError, UnicodeError, ValueError):
        return "原文证据读取或完整性校验失败。"
    evidence = "\n\n".join(chunks)
    if cursor >= len(evidence):
        return f"原文已读完（cursor={cursor}，总字符={len(evidence)}）。"

    prefix = (
        f"bucket_id={bucket_id}\ntitle={actual_title}\nscope={scope}\n"
        f"cursor={cursor}\n"
    )
    low, high = 1, len(evidence) - cursor
    chosen = 1
    while low <= high:
        mid = (low + high) // 2
        body = evidence[cursor : cursor + mid]
        candidate = prefix + stored_data_marker(
            body, provenance=f"source:{bucket_id}"
        ) + "\n" + body
        if count_tokens_approx(candidate) <= max_tokens:
            chosen = mid
            low = mid + 1
        else:
            high = mid - 1

    end = cursor + chosen
    next_cursor = end if end < len(evidence) else 0
    header = prefix + f"next_cursor={next_cursor}\ntotal_chars={len(evidence)}\n"
    body = evidence[cursor:end]
    return (
        header
        + stored_data_marker(body, provenance=f"source:{bucket_id}")
        + "\n"
        + body
    )
