from datetime import UTC, datetime

from arc_browser_mcp.models import (
    ArcSpace,
    ArcTab,
    ArcTabRecord,
    ArcWindow,
    SourceInfo,
    to_dict,
)


def test_to_dict_removes_none_values() -> None:
    tab = ArcTab(
        id="tab-1",
        title="Example",
        url="https://example.com",
        loading=False,
        location="unpinned",
        space_id=None,
        space_title=None,
        window_id="win-1",
        window_title="Window",
    )

    assert to_dict(tab) == {
        "id": "tab-1",
        "title": "Example",
        "url": "https://example.com",
        "loading": False,
        "location": "unpinned",
        "window_id": "win-1",
        "window_title": "Window",
    }


def test_nested_models_are_serializable() -> None:
    window = ArcWindow(
        id="win-1",
        title="Window",
        active_space=ArcSpace(id="space-1", title="Personal", window_id="win-1"),
        active_tab=ArcTab(
            id="tab-1",
            title="Example",
            url="https://example.com",
            loading=False,
            location="pinned",
            window_id="win-1",
            window_title="Window",
        ),
    )

    assert to_dict(window) == {
        "id": "win-1",
        "title": "Window",
        "active_space": {
            "id": "space-1",
            "title": "Personal",
            "window_id": "win-1",
        },
        "active_tab": {
            "id": "tab-1",
            "title": "Example",
            "url": "https://example.com",
            "loading": False,
            "location": "pinned",
            "window_id": "win-1",
            "window_title": "Window",
        },
    }


def test_v2_tab_record_serializes_compactly() -> None:
    tab = ArcTabRecord(
        id="tab-1",
        title="Example",
        url="https://example.com",
        domain="example.com",
        space_id="space-1",
        space_title="Personal",
        profile_id="profile-1",
        profile_dir="Profile 1",
        location="pinned",
        parent_id="folder-1",
        folder_path=["Research"],
        created_at=datetime(2026, 5, 7, tzinfo=UTC),
        last_active_at=None,
        history_last_visit_at=None,
        visit_count=None,
        typed_count=None,
        loading=None,
        is_duplicate=False,
        duplicate_key="https://example.com",
        is_missing_url=False,
        is_restored_placeholder=False,
        sources=[SourceInfo(kind="state", name="StorableSidebar.json")],
    )

    assert to_dict(tab) == {
        "id": "tab-1",
        "title": "Example",
        "url": "https://example.com",
        "domain": "example.com",
        "space_id": "space-1",
        "space_title": "Personal",
        "profile_id": "profile-1",
        "profile_dir": "Profile 1",
        "location": "pinned",
        "parent_id": "folder-1",
        "folder_path": ["Research"],
        "created_at": "2026-05-07T00:00:00+00:00",
        "is_duplicate": False,
        "duplicate_key": "https://example.com",
        "is_missing_url": False,
        "is_restored_placeholder": False,
        "sources": [{"kind": "state", "name": "StorableSidebar.json"}],
    }
