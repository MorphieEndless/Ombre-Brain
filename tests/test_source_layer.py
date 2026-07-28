from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import tools._runtime as rt
from ombrebrain.storage.source_store import (
    SourceStore,
    normalize_source_ranges,
)
from tools.source_read import dispatch as source_read
from tools.hold import dispatch as hold


def test_source_store_is_content_addressed_and_verifies_integrity(tmp_path):
    store = SourceStore(tmp_path)
    ref = store.put("第一行\n第二行\n第三行\n")
    assert store.put("第一行\n第二行\n第三行\n") == ref
    assert len(list((tmp_path / "_sources").glob("*.source"))) == 1
    assert store.read(ref) == "第一行\n第二行\n第三行\n"

    (tmp_path / "_sources" / f"{ref}.source").write_text("被篡改", encoding="utf-8")
    with pytest.raises(OSError, match="完整性"):
        store.read(ref)


def test_source_ranges_are_normalized_and_selected(tmp_path):
    store = SourceStore(tmp_path)
    ranges = normalize_source_ranges([[3, 3], [1, 2], [5, 5]])
    assert ranges == [[1, 3], [5, 5]]
    assert store.select_ranges("一\n二\n三\n四\n五\n", ranges) == "一\n二\n三\n五\n"


@pytest.mark.asyncio
async def test_source_read_requires_exact_bucket_and_title(
    bucket_mgr, monkeypatch
):
    store = SourceStore(bucket_mgr.base_dir)
    ref = store.put("开场\nwife 喔，不是 girlfriend 喔。\n直接 wife。\n尾声\n")
    bucket_id = await bucket_mgr.create(
        content="她注意到我直接用了 wife，我们就这个称呼笑了一阵。",
        title="wife",
        source_refs=[{"ref": ref, "ranges": [[2, 3]]}],
    )
    monkeypatch.setattr(rt, "bucket_mgr", bucket_mgr, raising=False)
    monkeypatch.setattr(rt, "source_store", store, raising=False)
    monkeypatch.setattr(rt, "logger", MagicMock(), raising=False)

    denied = await source_read(bucket_id, "直接确认关系")
    assert "标题不匹配" in denied

    event = await source_read(bucket_id, "wife", scope="event")
    assert "wife 喔" in event
    assert "直接 wife" in event
    assert "开场" not in event
    assert "尾声" not in event

    full = await source_read(bucket_id, "wife", scope="full_source")
    assert "开场" in full and "尾声" in full


@pytest.mark.asyncio
async def test_source_read_pages_without_silent_truncation(bucket_mgr, monkeypatch):
    store = SourceStore(bucket_mgr.base_dir)
    original = "段落内容。" * 3000
    ref = store.put(original)
    bucket_id = await bucket_mgr.create(
        content="分页测试正文",
        title="分页测试",
        source_refs=[{"ref": ref, "ranges": []}],
    )
    monkeypatch.setattr(rt, "bucket_mgr", bucket_mgr, raising=False)
    monkeypatch.setattr(rt, "source_store", store, raising=False)

    first = await source_read(
        bucket_id, "分页测试", scope="full_source", max_tokens=300
    )
    assert "next_cursor=0" not in first
    next_cursor = int(first.split("next_cursor=", 1)[1].splitlines()[0])
    second = await source_read(
        bucket_id,
        "分页测试",
        scope="full_source",
        cursor=next_cursor,
        max_tokens=300,
    )
    assert f"cursor={next_cursor}" in second


@pytest.mark.asyncio
async def test_hold_explicit_title_wins_over_model_suggestion(
    bucket_mgr, monkeypatch
):
    class Dehydrator:
        async def analyze(self, _content):
            return {
                "domain": ["恋爱"],
                "valence": 0.8,
                "arousal": 0.4,
                "tags": ["称呼"],
                "suggested_name": "直接确认关系",
            }

        def invalidate_cache(self, _content):
            return None

    class Decay:
        async def ensure_started(self):
            return None

    monkeypatch.setattr(rt, "config", {"limits": {}, "merge_threshold": 75})
    monkeypatch.setattr(rt, "bucket_mgr", bucket_mgr)
    monkeypatch.setattr(rt, "dehydrator", Dehydrator())
    monkeypatch.setattr(rt, "decay_engine", Decay())
    monkeypatch.setattr(rt, "logger", MagicMock())
    monkeypatch.setattr(rt, "fire_webhook", None)
    monkeypatch.setattr(rt, "mark_op", None)

    result = await hold(
        content="她说 wife 喔，不是 girlfriend 喔。",
        title="wife",
    )
    bucket_id = result.split("→", 1)[1].split()[0]
    bucket = await bucket_mgr.get(bucket_id)
    assert bucket["metadata"]["title"] == "wife"
    assert bucket["metadata"]["name"].endswith(" wife")
