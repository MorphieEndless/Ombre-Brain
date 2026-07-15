from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "frontend" / "dashboard.html"


def _quick_save_source() -> str:
    html = DASHBOARD.read_text(encoding="utf-8")
    start = html.index("async function _saveEnvKeys(")
    end = html.index("async function saveCompressKey()", start)
    return html[start:end]


def test_quick_env_save_requires_http_and_payload_success():
    source = _quick_save_source()

    assert "var responseFailed = !r.ok || !d || !d.ok" in source
    assert "if (responseFailed && savedKeys.length === 0)" in source
    assert "HTTP ' + r.status" in source
    assert "保存失败 / Save failed" in source


def test_quick_env_save_confirms_every_requested_field_before_green_success():
    source = _quick_save_source()

    requested = "Object.keys(updates || {})"
    missing = "updatedKeys.indexOf(key) === -1"
    safe_success = "if (!responseFailed && !responsePartial"
    positive_feedback = "color:var(--positive,#7EAD68)"

    assert requested in source
    assert "Array.isArray(d.updated)" in source
    assert missing in source
    assert safe_success in source
    assert source.index(safe_success) < source.index(positive_feedback)


def test_quick_env_save_surfaces_warnings_as_partial_or_failed():
    source = _quick_save_source()

    assert "Array.isArray(d.warnings)" in source
    assert "部分保存 / Partially saved" in source
    assert "color:var(--warning,#B89762)" in source
    assert "警告 / Warning:" in source
    assert "savedKeys.length > 0" in source
    assert "服务器未确认任何请求字段" in source


def test_quick_env_save_honors_partial_and_persistence_contract():
    source = _quick_save_source()

    assert "var responsePartial = !!(d && d.partial)" in source
    assert "Array.isArray(d.persisted)" in source
    assert "unpersistedKeys.length === 0" in source
    assert "未持久化 / Not persisted:" in source
    assert "if (savedKeys.length > 0)" in source
    assert "refreshEnvConfig();" in source


def test_main_env_save_flow_is_left_intact():
    html = DASHBOARD.read_text(encoding="utf-8")
    start = html.index("async function saveEnvConfig()")
    end = html.index("async function _saveEnvKeys(", start)
    source = html[start:end]

    assert "var r = await authFetch('/api/env-config'" in source
    assert "refreshEnvConfig();" in source
    assert "已保存：" in source
