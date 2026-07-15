from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "frontend" / "dashboard.html"


def _dashboard_section(start_marker: str, end_marker: str) -> str:
    html = DASHBOARD.read_text(encoding="utf-8")
    start = html.index(start_marker)
    end = html.index(end_marker, start)
    return html[start:end]


def test_bucket_reload_preserves_active_filter_and_page():
    source = _dashboard_section(
        "async function loadBuckets()", "function updateStats()"
    )

    assert "buildFilters();" in source
    assert "renderBuckets(filterBuckets(allBuckets), true);" in source
    assert "renderBuckets(allBuckets);" not in source


def test_filter_rebuild_restores_active_filter_without_listener_leaks():
    source = _dashboard_section("function buildFilters()", "function filterBuckets(")

    assert "if (!availableFilters.includes(currentFilter)) currentFilter = 'all';" in source
    assert "t.key === currentFilter ? 'active' : ''" in source
    assert "key === currentFilter ? 'active' : ''" in source
    assert "filters.onclick = function(e)" in source
    assert "filters.addEventListener('click'" not in source


def test_bucket_renderer_only_resets_page_for_an_explicit_view_change():
    source = _dashboard_section("function renderBuckets(", "function gotoBucketPage(")

    assert "function renderBuckets(buckets, preservePage)" in source
    assert "if (!preservePage) bucketPage = 1;" in source


def test_clearing_search_restores_the_active_filter_not_the_all_view():
    source = _dashboard_section(
        "document.getElementById('search-input').addEventListener",
        "async function loadBuckets()",
    )

    assert source.count("else renderBuckets(filterBuckets(allBuckets));") == 2
    assert "else renderBuckets(allBuckets);" not in source


def test_pin_and_edit_refreshes_are_awaited():
    pin_source = _dashboard_section("async function bucketPin(", "async function bucketAnchor(")
    edit_source = _dashboard_section(
        "async function bucketSaveEdit(", "async function maybeShowOnboarding("
    )

    assert "await loadBuckets();" in pin_source
    assert "await loadBuckets();" in edit_source
