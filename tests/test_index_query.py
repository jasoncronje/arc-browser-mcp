from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arc_browser_mcp.index import ArcIndexCache
from arc_browser_mcp.models import (
    ArcFolderRecord,
    ArcHistoryRecord,
    ArcSpaceRecord,
    ArcTabRecord,
    SourceInfo,
)
from arc_browser_mcp.state_store import ArcStateSnapshot


class FakeStateStore:
    def load(self, *, include_recovery: bool = False) -> ArcStateSnapshot:
        source = SourceInfo(kind="state", name="fixture")
        created_at = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        last_active_at = datetime(2026, 5, 1, 13, 0, tzinfo=UTC)
        return ArcStateSnapshot(
            spaces=[
                ArcSpaceRecord(
                    id="space-1",
                    title="Personal",
                    profile_id="Profile 1",
                    profile_dir="Profile 1",
                    window_id=None,
                    pinned_container_id="pinned-root",
                    unpinned_container_id="unpinned-root",
                    counts={"pinned": 1, "unpinned": 1, "folders": 1, "missing_urls": 0},
                    sources=[source],
                )
            ],
            folders=[
                ArcFolderRecord(
                    id="folder-1",
                    title="Research",
                    space_id="space-1",
                    location="unpinned",
                    parent_id="unpinned-root",
                    folder_path=["Research"],
                    child_count=1,
                    tab_count=1,
                    sources=[source],
                )
            ],
            tabs=[
                ArcTabRecord(
                    id="tab-1",
                    title="Python Docs",
                    url="https://docs.python.org/3/",
                    domain="docs.python.org",
                    space_id="space-1",
                    space_title="Personal",
                    profile_id="Profile 1",
                    profile_dir="Profile 1",
                    location="pinned",
                    parent_id="pinned-root",
                    folder_path=[],
                    created_at=created_at,
                    last_active_at=last_active_at,
                    history_last_visit_at=None,
                    visit_count=None,
                    typed_count=None,
                    loading=False,
                    is_duplicate=False,
                    duplicate_key="https://docs.python.org/3",
                    is_missing_url=False,
                    is_restored_placeholder=False,
                    sources=[source],
                ),
                ArcTabRecord(
                    id="tab-2",
                    title="Example",
                    url="https://example.com/page",
                    domain="example.com",
                    space_id="space-1",
                    space_title="Personal",
                    profile_id="Profile 1",
                    profile_dir="Profile 1",
                    location="unpinned",
                    parent_id="folder-1",
                    folder_path=["Research"],
                    created_at=created_at,
                    last_active_at=last_active_at,
                    history_last_visit_at=None,
                    visit_count=None,
                    typed_count=None,
                    loading=False,
                    is_duplicate=False,
                    duplicate_key="https://example.com/page",
                    is_missing_url=False,
                    is_restored_placeholder=False,
                    sources=[source],
                ),
            ],
            recovery_candidates={},
            warnings=[],
        )


class FakeHistoryStore:
    def search(self, **kwargs: Any) -> list[Any]:
        return []


class FileBackedFakeStateStore:
    def __init__(self, sidebar_path: Path) -> None:
        self.sidebar_path = sidebar_path
        self.load_count = 0

    def load(self, *, include_recovery: bool = False) -> ArcStateSnapshot:
        self.load_count += 1
        source = SourceInfo(kind="state", name="fixture")
        return ArcStateSnapshot(
            spaces=[
                ArcSpaceRecord(
                    id="space-1",
                    title=self.sidebar_path.read_text(),
                    profile_id="Profile 1",
                    profile_dir="Profile 1",
                    window_id=None,
                    pinned_container_id="pinned-root",
                    unpinned_container_id=None,
                    counts={"pinned": 0, "unpinned": 0, "folders": 0, "missing_urls": 0},
                    sources=[source],
                )
            ],
            folders=[],
            tabs=[],
            recovery_candidates={},
            warnings=[],
        )


class RecordingHistoryStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> list[ArcHistoryRecord]:
        self.calls.append(kwargs)
        source = SourceInfo(kind="history", name="fixture")
        return [
            ArcHistoryRecord(
                id="history-1",
                url="https://example.com/page",
                title="Example History",
                domain="example.com",
                profile_id="Profile 1",
                profile_dir="Profile 1",
                last_visit_at=datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
                visit_count=3,
                typed_count=1,
                hidden=False,
                sources=[source],
            ),
            ArcHistoryRecord(
                id="history-2",
                url="https://example.com/other",
                title="Other History",
                domain="example.com",
                profile_id="Profile 1",
                profile_dir="Profile 1",
                last_visit_at=datetime(2026, 5, 1, 15, 0, tzinfo=UTC),
                visit_count=1,
                typed_count=0,
                hidden=False,
                sources=[source],
            ),
        ]


def test_index_overview_counts_tabs_and_spaces() -> None:
    overview = ArcIndexCache(
        state_store=FakeStateStore(),
        history_store=FakeHistoryStore(),
    ).get().overview()

    assert overview["totals"]["spaces"] == 1
    assert overview["totals"]["tabs"] == 2
    assert overview["totals"]["pinned"] == 1
    assert overview["spaces"][0]["title"] == "Personal"


def test_index_query_filters_by_text_location_and_folder() -> None:
    index = ArcIndexCache(
        state_store=FakeStateStore(),
        history_store=FakeHistoryStore(),
    ).get()

    pinned_result = index.query_tabs(query="python", location="pinned", limit=10)
    folder_result = index.query_tabs(folder_id="folder-1", limit=10)

    assert pinned_result["total"] == 1
    assert pinned_result["items"][0]["id"] == "tab-1"
    assert [item["id"] for item in folder_result["items"]] == ["tab-2"]


def test_index_get_tab_hydrates_full_record() -> None:
    tab = ArcIndexCache(
        state_store=FakeStateStore(),
        history_store=FakeHistoryStore(),
    ).get().get_tab("tab-2")

    assert tab["id"] == "tab-2"
    assert tab["folder_path"] == ["Research"]


def test_index_get_tab_includes_matching_history_entries() -> None:
    history_store = RecordingHistoryStore()

    tab = ArcIndexCache(
        state_store=FakeStateStore(),
        history_store=history_store,
    ).get().get_tab("tab-2")

    assert history_store.calls == [
        {"domain": "example.com", "include_hidden": True, "limit": 50}
    ]
    assert [entry["id"] for entry in tab["history_entries"]] == ["history-1"]
    assert tab["history_entries"][0]["url"] == "https://example.com/page"


def test_index_sidebar_tree_can_include_tabs() -> None:
    tree = ArcIndexCache(
        state_store=FakeStateStore(),
        history_store=FakeHistoryStore(),
    ).get().sidebar_tree(space_id="space-1", include_tabs=True)

    space = tree["spaces"][0]
    pinned_root = space["children"][0]
    unpinned_root = space["children"][1]
    folder = unpinned_root["children"][0]

    assert space["type"] == "space"
    assert space["id"] == "space-1"
    assert space["profile_dir"] == "Profile 1"
    assert pinned_root["type"] == "root"
    assert pinned_root["id"] == "pinned-root"
    assert pinned_root["location"] == "pinned"
    assert pinned_root["children"][0]["id"] == "tab-1"
    assert unpinned_root["type"] == "root"
    assert unpinned_root["id"] == "unpinned-root"
    assert unpinned_root["location"] == "unpinned"
    assert folder["type"] == "folder"
    assert folder["id"] == "folder-1"
    assert folder["tab_count"] == 1
    assert folder["children"][0]["id"] == "tab-2"


def test_index_cache_rebuilds_when_state_source_signature_changes(tmp_path: Path) -> None:
    sidebar_path = tmp_path / "StorableSidebar.json"
    sidebar_path.write_text("Personal")
    state_store = FileBackedFakeStateStore(sidebar_path)
    cache = ArcIndexCache(state_store=state_store, history_store=FakeHistoryStore())

    first_overview = cache.get().overview()
    sidebar_path.write_text("Personal Updated")
    second_overview = cache.get().overview()

    assert state_store.load_count == 2
    assert first_overview["spaces"][0]["title"] == "Personal"
    assert second_overview["spaces"][0]["title"] == "Personal Updated"
