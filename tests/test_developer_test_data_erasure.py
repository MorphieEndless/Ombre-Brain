from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_only_creation_marked_test_bucket_can_be_hard_deleted(bucket_mgr):
    real_id = await bucket_mgr.create(content="a real memory", domain=["life"])
    test_id = await bucket_mgr.create(
        content="synthetic memory for a test",
        domain=["test"],
        source_tool="hold",
        test_data=True,
    )

    test_bucket = await bucket_mgr.get(test_id)
    assert test_bucket["metadata"]["provenance"] == {
        "kind": "test",
        "created_by": "hold",
        "erasable": True,
    }

    refused = await bucket_mgr.hard_delete_test_bucket(real_id, reason="should fail")
    assert refused == {"ok": False, "error": "not_erasable_test_data"}
    assert await bucket_mgr.get(real_id) is not None

    erased_path = Path(test_bucket["path"])
    erased = await bucket_mgr.hard_delete_test_bucket(test_id, reason="test cleanup")
    assert erased == {"ok": True, "deleted": test_id}
    assert not erased_path.exists()
    assert await bucket_mgr.get(test_id) is None


def test_dashboard_separates_normal_batch_actions_from_developer_erasure():
    text = Path("frontend/dashboard.html").read_text(encoding="utf-8")
    assert "全选当前筛选" in text
    assert "/api/buckets/batch" in text
    assert "body.developer-mode .developer-only" in text
    assert "/api/developer/buckets/hard-delete" in text
    assert "DELETE TEST DATA" in text


def test_dashboard_chick_is_draggable_and_remembers_a_safe_position():
    text = Path("frontend/dashboard.html").read_text(encoding="utf-8")
    assert "installPetDrag" in text
    assert "setPointerCapture" in text
    assert "ombreChickPosition" in text
    assert "clampPetPosition" in text
    assert "可恶的人类！" in text
    assert "touch-action: none" in text
    assert "dropRemark" in text
    assert "这位置以前是我的。" in text
    assert "你找什么？我帮你啄。" in text
    assert "你怎么还没睡？" in text
    assert "天旋地转……你礼貌吗？" in text
    assert "play-dead" in text
    assert "sleeping" in text
    assert "我会替你放远一点。" in text
    assert "护目镜戴好，开始实验。" in text
    assert "假的，清理完了。" in text
    assert "这条不行。" in text
    assert "……算了，原谅你。" in text


def test_dashboard_chick_can_be_tickled_and_reacts_to_real_system_states():
    text = Path("frontend/dashboard.html").read_text(encoding="utf-8")

    assert "TICKLE_LINES" in text
    assert "canvasX - spriteX" in text
    assert "lastPetAction==='tickle'" in text
    assert "别碰我。" in text
    assert "下次再碰我就把你的桶全归档。" in text
    assert "别挠了，痒。" in text
    assert "chickReactForApiProblem" in text
    assert "最近发现你有429的问题" in text
    assert "你的key坏了" in text
    assert "你喂了我一段话但我没消化成功" in text
    assert "正在重新理解所有的记忆" in text
    assert "这里什么都没有" in text
    assert "找不到我自己" in text
    assert "正在忘记一些不重要的事" in text
