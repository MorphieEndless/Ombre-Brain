import json
from pathlib import Path
import shutil
import subprocess

import pytest


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

    assert "if (!domains.has(currentFilter.slice(7))) currentFilter = 'all';" in source
    assert "!visibleDomains.includes(currentDomain)" in source
    assert "visibleDomains[visibleDomains.length - 1] = currentDomain;" in source
    assert "var active = t.key === currentFilter;" in source
    assert "var active = key === currentFilter;" in source
    assert "aria-pressed" in source
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


def test_bucket_pager_has_first_last_and_direct_page_navigation():
    source = _dashboard_section("function _bucketPagerHtml(", "function _paintBuckets(")

    assert '<nav class="bucket-pager" aria-label="记忆桶分页">' in source
    assert "gotoBucketPage(1)" in source
    assert "gotoBucketPage(' + totalPages + ')" in source
    assert 'id="bucket-page-input" type="number"' in source
    assert 'min="1" max="' in source
    assert 'step="1"' in source
    assert "jumpToBucketPage()" in source
    assert 'role="status" aria-live="polite"' in source


def test_empty_bucket_view_resets_page_and_selection_state():
    source = _dashboard_section("function _paintBuckets()", "function _localBucketMatches(")
    empty_branch = source[source.index("if (!visible.length)") : source.index("// 分页：")]

    assert "bucketPage = 1;" in empty_branch
    assert "syncBucketSelectionUi();" in empty_branch


def test_bucket_sort_is_persisted_sent_to_api_and_resets_page():
    html = DASHBOARD.read_text(encoding="utf-8")
    state_source = _dashboard_section("const BASE = location.origin", "function setDeveloperMode(")
    load_source = _dashboard_section("async function loadBuckets()", "function updateStats()")

    assert 'id="bucket-sort"' in html
    assert '<option value="score">综合分优先</option>' in html
    assert '<option value="created_desc">最新创建优先</option>' in html
    assert '<option value="created_asc">最早创建优先</option>' in html
    assert "['score', 'created_desc', 'created_asc']" in state_source
    assert "localStorage.getItem('ombreBucketSort')" in state_source
    assert "localStorage.setItem('ombreBucketSort', bucketSort)" in state_source
    assert "bucketPage = 1;" in state_source
    assert "await loadBuckets();" in state_source
    assert "'?sort=' + encodeURIComponent(requestedSort)" in load_source
    assert "generation !== bucketLoadGeneration" in load_source


def test_time_views_use_created_and_invalid_dates_never_render_nan():
    render_source = _dashboard_section("function _paintBuckets()", "function _localBucketMatches(")
    time_source = _dashboard_section("function parseBucketDate(", "function feelFace(")

    assert "firstValidBucketTime(b.created_epoch_ms, b.created)" in render_source
    assert "b.last_active_epoch_ms, b.last_active, b.created_epoch_ms, b.created" in render_source
    assert "'创建 ' + formatCompactBucketTime(shownTime)" in render_source
    assert "Number.isNaN(d.getTime()) ? null : d" in time_source
    assert "if (!d) return '—';" in time_source


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_filter_rebuild_keeps_selected_domain_outside_visible_top_ten():
    source = _dashboard_section("function buildFilters()", "function filterBuckets(")
    script = """
let currentFilter = 'domain:d11';
let allBuckets = Array.from({length: 12}, (_, i) => ({domain: ['d' + i]}));
function escAttr(value) { return String(value); }
function esc(value) { return String(value); }
const filterElement = {innerHTML: '', onclick: null};
const document = {getElementById() { return filterElement; }};
""" + source + """
buildFilters();
const retained = currentFilter;
const retainedButton = filterElement.innerHTML.includes('data-filter="domain:d11"');
allBuckets = allBuckets.slice(0, 11);
buildFilters();
process.stdout.write(JSON.stringify([retained, retainedButton, currentFilter]));
"""
    completed = subprocess.run(
        [shutil.which("node"), "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == ["domain:d11", True, "all"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_server_epoch_wins_over_browser_local_naive_time():
    source = _dashboard_section("function parseBucketDate(", "function feelFace(")
    script = source + """
const normalized = firstValidBucketTime(0, '1970-01-01T00:00:00');
const fallback = firstValidBucketTime(NaN, '2000-01-01T00:00:00Z');
process.stdout.write(JSON.stringify([normalized.getTime(), fallback.getTime()]));
"""
    completed = subprocess.run(
        [shutil.which("node"), "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [0, 946684800000]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_page_normalizer_runtime_boundaries():
    source = _dashboard_section(
        "function _normalizeBucketPage(", "function _visibleBucketTotalPages("
    )
    script = source + """
const values = [
  _normalizeBucketPage(3, 5, 1),
  _normalizeBucketPage(0, 5, 3),
  _normalizeBucketPage(99, 5, 3),
  _normalizeBucketPage(2.9, 5, 1),
  _normalizeBucketPage('', 5, 3),
  _normalizeBucketPage('not-a-page', 5, 3),
  _normalizeBucketPage(Infinity, 5, 3),
  _normalizeBucketPage(1, 0, 5),
  _normalizeBucketPage(null, 5, 0),
];
process.stdout.write(JSON.stringify(values));
"""
    completed = subprocess.run(
        [shutil.which("node"), "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [3, 1, 5, 2, 3, 3, 3, 1, 1]
