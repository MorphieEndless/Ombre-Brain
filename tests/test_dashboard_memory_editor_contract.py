import json
from pathlib import Path

import pytest

import web.buckets as buckets_web


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "frontend" / "dashboard.html"


class FakeMCP:
    def __init__(self):
        self.routes = {}

    def custom_route(self, path, methods):
        def decorator(handler):
            for method in methods:
                self.routes[(method, path)] = handler
            return handler

        return decorator


class JsonRequest:
    def __init__(self, *, path_params=None):
        self.path_params = path_params or {}
        self.headers = {}
        self.query_params = {}


class FakeDecayEngine:
    def calculate_score(self, _metadata):
        return 1.0


class FakeBucketManager:
    def __init__(self, bucket):
        self.bucket = bucket

    async def list_all(self, *, include_archive=False):
        assert include_archive is True
        return [self.bucket]

    async def get(self, bucket_id):
        return self.bucket if bucket_id == self.bucket["id"] else None

    async def get_triggered_feels(self, _bucket_id):
        return []


def _payload(response):
    return json.loads(response.body.decode("utf-8"))


def _dashboard_function(name, next_name):
    html = DASHBOARD.read_text(encoding="utf-8")
    start = html.index(f"function {name}(")
    end = html.index(f"function {next_name}(", start)
    return html[start:end]


@pytest.mark.asyncio
async def test_bucket_detail_preserves_raw_content_and_separates_display_text(
    monkeypatch,
):
    raw_content = "before [[Target|Alias]] and [[Target#Section]] after"
    bucket = {
        "id": "memory-1",
        "metadata": {"name": "Linked memory", "type": "dynamic"},
        "content": raw_content,
    }
    manager = FakeBucketManager(bucket)
    monkeypatch.setattr(buckets_web.sh, "_require_auth", lambda _request: None)
    monkeypatch.setattr(buckets_web.sh, "bucket_mgr", manager, raising=False)
    monkeypatch.setattr(
        buckets_web.sh, "decay_engine", FakeDecayEngine(), raising=False
    )
    mcp = FakeMCP()
    buckets_web.register(mcp)

    list_response = await mcp.routes[("GET", "/api/buckets")](JsonRequest())
    detail_response = await mcp.routes[("GET", "/api/bucket/{bucket_id}")](
        JsonRequest(path_params={"bucket_id": "memory-1"})
    )
    listed = _payload(list_response)[0]
    detail = _payload(detail_response)

    assert listed["content_preview"] == (
        "before Target|Alias and Target#Section after"
    )
    assert detail["content"] == raw_content
    assert detail["display_content"] == listed["content_preview"]


def test_dashboard_uses_display_text_for_preview_and_raw_content_for_editor():
    source = _dashboard_function("showDetail", "bucketPin")

    assert "typeof b.display_content === 'string'" in source
    assert "esc(displayContent)" in source
    assert "_content_for_edit: b.content" in source
    assert "'<div class=\"detail-content\">' + esc(b.content)" not in source


def test_editor_preserves_special_and_future_bucket_types():
    render_source = _dashboard_function("renderEditForm", "bucketSaveEdit")
    save_source = _dashboard_function("bucketSaveEdit", "maybeShowOnboarding")

    assert (
        "const editableTypes = ['dynamic','permanent','feel','plan','letter']"
        in render_source
    )
    assert "const currentType = String(meta.type || 'dynamic')" in render_source
    assert "[currentType].concat(editableTypes)" in render_source
    assert "meta.pinned && typeIsEditable" in render_source
    assert "? ['permanent', 'dynamic']" in render_source
    assert "currentType === t ? 'selected' : ''" in render_source
    assert "typeIsEditable ? '' : 'disabled" in render_source
    assert "if (typeEl && !typeEl.disabled) body.type = typeEl.value" in save_source
    assert "type: document.getElementById('edit-type').value" not in save_source


def test_editor_submits_metadata_using_storage_field_names():
    source = _dashboard_function("bucketSaveEdit", "maybeShowOnboarding")

    assert "dont_surface: document.getElementById('edit-dont-surface').checked" in source
    assert "why_remembered: document.getElementById('edit-why').value" in source
    assert "if (weightEl) body.weight = parseFloat(weightEl.value) / 100" in source


def test_editor_keeps_pin_type_and_importance_constraints_in_sync():
    render_source = _dashboard_function("renderEditForm", "syncEditPinConstraints")
    sync_source = _dashboard_function("syncEditPinConstraints", "bucketSaveEdit")
    save_source = _dashboard_function("bucketSaveEdit", "maybeShowOnboarding")

    assert "onchange=\"syncEditPinConstraints('type')\"" in render_source
    assert "syncEditPinConstraints('importance')" in render_source
    assert "onchange=\"syncEditPinConstraints('pinned')\"" in render_source
    assert "typeEl.value = 'permanent';" in sync_source
    assert "importanceEl.value = '10';" in sync_source
    assert "pinnedEl.checked = false;" in sync_source
    assert "syncEditPinConstraints('save');" in save_source
    assert save_source.index("syncEditPinConstraints('save');") < save_source.index(
        "const body = {"
    )
