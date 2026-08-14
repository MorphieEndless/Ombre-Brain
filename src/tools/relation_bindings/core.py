"""Reversible, bucket-to-bucket Relation V1 operations."""
from __future__ import annotations
from typing import Any
from ombrebrain.storage.relation_store import MAX_ACTIVE_RELATION_LINKS, MAX_RELATION_LINKS, normalize_relation_label, normalize_relation_links, normalize_relation_type
from .. import _runtime as rt
from ..source_read.core import _normalized_title
from ..plan.core import is_letter_bucket

def _ordinary(bucket: Any, bucket_id: str = "") -> bool:
    meta = (bucket.get("metadata") if isinstance(bucket, dict) else getattr(bucket, "metadata", {})) or {}
    kind = str(meta.get("type") or "dynamic").strip().lower()
    if kind == "archived" and bucket_id:
        snapshot = rt.bucket_mgr.footprint_snapshot()
        kind = str(snapshot.original_kind(bucket_id, meta) or "dynamic").strip().lower()
    return kind not in {"plan", "feel", "letter", "i", "i_candidate", "identity"} and not is_letter_bucket({"metadata": meta})

def _access(post: Any, bucket_id: str, expected_title: str) -> str:
    meta = getattr(post, "metadata", {}) or {}
    if not _ordinary({"metadata": meta}, bucket_id): return "Relation V1 only permits ordinary memory buckets."
    if not _ordinary({"metadata": meta}): return "Relation V1 只允许普通记忆桶。"
    actual = _normalized_title(meta.get("title"))
    return "标题不匹配，拒绝修改 Relation。" if not actual or actual != expected_title else ""

async def _get(bucket_id: str):
    return await getattr(rt.bucket_mgr, "get_including_archive", rt.bucket_mgr.get)(bucket_id)

async def attach(bucket_id: str, expected_title: str, target_bucket_id: str, relation_type: str, label: str = "") -> str:
    if not isinstance(target_bucket_id, str):
        return "relation_attach 拒绝：target_bucket_id 必须是字符串。"
    bucket_id, target_bucket_id, expected_title = str(bucket_id or "").strip(), str(target_bucket_id or "").strip(), _normalized_title(expected_title)
    if not bucket_id or not target_bucket_id or not expected_title: return "relation_attach 需要 bucket_id、expected_title 与 target_bucket_id。"
    if bucket_id == target_bucket_id: return "relation_attach 拒绝：不允许同桶自环。"
    try: relation_type, label = normalize_relation_type(relation_type), normalize_relation_label(label)
    except ValueError as exc: return f"relation_attach 拒绝：{exc}"
    source, target = await _get(bucket_id), await _get(target_bucket_id)
    if source and target and (not _ordinary(source, bucket_id) or not _ordinary(target, target_bucket_id)):
        return "Relation V1 only permits ordinary memory buckets."
    if not source or not target: return "relation_attach 拒绝：source 与 target 都必须真实存在。"
    if not _ordinary(source) or not _ordinary(target): return "Relation V1 只允许普通记忆桶。"
    candidate = {"target_bucket_id": target_bucket_id, "type": relation_type, "label": label, "status": "active"}
    def mutation(post: Any):
        err = _access(post, bucket_id, expected_title)
        if err: return False, err
        try: links = normalize_relation_links(post.metadata.get("relation_links"))
        except ValueError: return False, "该桶的 relation_links 格式无效，拒绝修改。"
        key = (target_bucket_id, relation_type, label)
        for slot, link in enumerate(links, 1):
            if (link["target_bucket_id"], link["type"], link["label"]) == key:
                return False, f"relation_attach {'ok' if link['status']=='active' else 'detached'} bucket_id={bucket_id} slot={slot}" + ("；请使用 relation_restore。" if link['status']=='detached' else "")
        if len(links) >= MAX_RELATION_LINKS: return False, f"relation_attach 拒绝：relation_links 上限 {MAX_RELATION_LINKS}。"
        if sum(x['status']=='active' for x in links) >= MAX_ACTIVE_RELATION_LINKS: return False, f"relation_attach 拒绝：活动 relation_links 上限 {MAX_ACTIVE_RELATION_LINKS}。"
        links.append(candidate); post["relation_links"] = links
        return True, f"relation_attach ok bucket_id={bucket_id} slot={len(links)} status=active"
    return (await rt.bucket_mgr.mutate_relation_links(bucket_id, mutation)) or f"未找到桶 {bucket_id}。"

async def _change(bucket_id: str, expected_title: str, relation_slot: int, status: str) -> str:
    action = "restore" if status == "active" else "detach"; expected_title = _normalized_title(expected_title)
    if isinstance(relation_slot, bool) or not isinstance(relation_slot, int) or relation_slot < 1: return "relation_slot 必须是从 1 开始的整数。"
    def mutation(post: Any):
        err = _access(post, str(bucket_id or '').strip(), expected_title)
        if err: return False, err
        try: links = normalize_relation_links(post.metadata.get("relation_links"))
        except ValueError: return False, "该桶的 relation_links 格式无效，拒绝修改。"
        if relation_slot > len(links): return False, f"relation_slot={relation_slot} 不存在。"
        link = links[relation_slot-1]
        if link['status'] == status: return False, f"relation_{action} ok bucket_id={bucket_id} slot={relation_slot} status={status}"
        if status == 'active' and sum(x['status']=='active' for x in links) >= MAX_ACTIVE_RELATION_LINKS: return False, f"relation_restore 拒绝：活动 relation_links 上限 {MAX_ACTIVE_RELATION_LINKS}。"
        link['status']=status; post['relation_links']=links
        return True, f"relation_{action} ok bucket_id={bucket_id} slot={relation_slot} status={status}"
    return (await rt.bucket_mgr.mutate_relation_links(str(bucket_id or '').strip(), mutation)) or f"未找到桶 {bucket_id}。"
async def detach(bucket_id: str, expected_title: str, relation_slot: int) -> str: return await _change(bucket_id, expected_title, relation_slot, 'detached')
async def restore(bucket_id: str, expected_title: str, relation_slot: int) -> str: return await _change(bucket_id, expected_title, relation_slot, 'active')
