from __future__ import annotations

import json
from pathlib import Path

from arc_browser_mcp.state_store import ArcStateStore


def write_sidebar(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "firebaseSyncState": {
                    "syncData": {
                        "spaceModels": [
                            "space-1",
                            {
                                "lastChangeDate": 791596800,
                                "lastChangedDevice": "device-1",
                                "value": {
                                    "title": "Personal",
                                    "profile": {
                                        "custom": {
                                            "_0": {
                                                "directoryBasename": "Profile 1",
                                            }
                                        }
                                    },
                                    "containerIDs": [
                                        "pinned",
                                        {"value": "pinned-root"},
                                        "pinned-root",
                                        {"value": "pinned-root"},
                                        "unpinned",
                                        {"value": "unpinned-root"},
                                        "unpinned-root",
                                        {"value": "unpinned-root"},
                                    ],
                                },
                            },
                        ],
                        "items": [
                            "pinned-root",
                            {
                                "value": {
                                    "title": "Pinned Root",
                                    "childrenIds": ["pinned-tab"],
                                },
                            },
                            "unpinned-root",
                            {
                                "value": {
                                    "title": "Unpinned Root",
                                    "childrenIds": ["folder-1", "loose-tab", "missing-tab"],
                                },
                            },
                            "folder-1",
                            {
                                "value": {
                                    "title": "Research",
                                    "parentID": "unpinned-root",
                                    "childrenIds": ["folder-tab"],
                                },
                            },
                            "pinned-tab",
                            {
                                "lastChangeDate": 791596900,
                                "lastChangedDevice": "device-1",
                                "value": {
                                    "title": "Pinned Item",
                                    "parentID": "pinned-root",
                                    "createdAt": 0,
                                    "data": {
                                        "tab": {
                                            "savedTitle": "Pinned",
                                            "savedURL": "https://example.com/pinned",
                                            "timeLastActiveAt": 60,
                                        }
                                    }
                                },
                            },
                            "folder-tab",
                            {
                                "value": {
                                    "title": "Folder Item",
                                    "parentID": "folder-1",
                                    "createdAt": 120,
                                    "data": {
                                        "tab": {
                                            "savedTitle": "Folder Tab",
                                            "savedURL": "https://example.com/folder",
                                            "timeLastActiveAt": 180,
                                        }
                                    }
                                },
                            },
                            "loose-tab",
                            {
                                "value": {
                                    "title": "Loose Item",
                                    "parentID": "unpinned-root",
                                    "data": {
                                        "tab": {
                                            "savedTitle": "Python Docs",
                                            "savedURL": "https://docs.python.org/3/",
                                        }
                                    }
                                },
                            },
                            "missing-tab",
                            {
                                "value": {
                                    "title": "Restored Placeholder",
                                    "parentID": "unpinned-root",
                                    "data": {"tab": {}},
                                },
                            },
                        ],
                    }
                }
            }
        )
    )


def test_state_store_parses_spaces_locations_folders_and_missing_urls(tmp_path: Path) -> None:
    sidebar_path = tmp_path / "StorableSidebar.json"
    write_sidebar(sidebar_path)

    snapshot = ArcStateStore(sidebar_path=sidebar_path).load()

    assert [space.id for space in snapshot.spaces] == ["space-1"]
    assert snapshot.spaces[0].profile_id == "Profile 1"
    assert snapshot.spaces[0].profile_dir == "Profile 1"

    tabs = {tab.id: tab for tab in snapshot.tabs}
    assert tabs["pinned-tab"].location == "pinned"
    assert tabs["pinned-tab"].title == "Pinned"
    assert tabs["pinned-tab"].parent_id == "pinned-root"
    assert tabs["pinned-tab"].created_at is not None
    assert tabs["pinned-tab"].last_active_at is not None
    assert tabs["folder-tab"].location == "unpinned"
    assert tabs["folder-tab"].folder_path == ["Research"]
    assert tabs["folder-tab"].parent_id == "folder-1"
    assert tabs["loose-tab"].domain == "docs.python.org"
    assert tabs["missing-tab"].is_missing_url
    assert tabs["missing-tab"].is_restored_placeholder

    folders = {folder.id: folder for folder in snapshot.folders}
    assert folders["folder-1"].folder_path == ["Research"]
    assert folders["folder-1"].parent_id == "unpinned-root"
    assert folders["folder-1"].tab_count == 1


def test_state_store_collects_missing_url_recovery_candidates(tmp_path: Path) -> None:
    sidebar_path = tmp_path / "StorableSidebar.json"
    backup_path = tmp_path / "StorableSidebar.2026-05-01-00-00-00-000.json"
    archive_path = tmp_path / "StorableArchiveItems.json"
    command_path = tmp_path / "StorableCommandBarAdditionalRanking.json"
    write_sidebar(sidebar_path)

    sidebar_payload = json.loads(sidebar_path.read_text())
    items = sidebar_payload["firebaseSyncState"]["syncData"]["items"]
    missing_tab = items[items.index("missing-tab") + 1]
    missing_tab["value"]["data"]["tab"]["savedURL"] = "https://example.com/recovered"
    backup_path.write_text(json.dumps(sidebar_payload))
    archive_path.write_text(json.dumps({"items": []}))
    command_path.write_text(json.dumps({"version": 1, "dataByProfile": []}))

    store = ArcStateStore(
        sidebar_path=sidebar_path,
        archive_path=archive_path,
        command_ranking_path=command_path,
        backup_paths=[backup_path],
    )

    snapshot = store.load(include_recovery=True)

    candidate = snapshot.recovery_candidates["missing-tab"][0]
    assert candidate["url"] == "https://example.com/recovered"
    assert candidate["confidence"] == "high"
    assert candidate["match"] == "same_tab_id_in_state_backup"


def test_state_store_collects_archive_and_command_recovery_candidates(
    tmp_path: Path,
) -> None:
    sidebar_path = tmp_path / "StorableSidebar.json"
    archive_path = tmp_path / "StorableArchiveItems.json"
    command_path = tmp_path / "StorableCommandBarAdditionalRanking.json"
    write_sidebar(sidebar_path)
    archive_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Restored Placeholder",
                        "url": "https://example.com/from-archive",
                    }
                ]
            }
        )
    )
    command_path.write_text(
        json.dumps(
            {
                "dataByProfile": [
                    {
                        "records": [
                            {
                                "title": "Restored Placeholder",
                                "url": "https://example.com/from-command",
                            }
                        ]
                    }
                ]
            }
        )
    )

    store = ArcStateStore(
        sidebar_path=sidebar_path,
        archive_path=archive_path,
        command_ranking_path=command_path,
        backup_paths=[],
    )

    snapshot = store.load(include_recovery=True)

    candidates = snapshot.recovery_candidates["missing-tab"]
    assert {
        (candidate["url"], candidate["source"], candidate["match"])
        for candidate in candidates
    } == {
        (
            "https://example.com/from-archive",
            "StorableArchiveItems.json",
            "matching_title_in_archive",
        ),
        (
            "https://example.com/from-command",
            "StorableCommandBarAdditionalRanking.json",
            "matching_title_in_command_ranking",
        ),
    }


def test_state_store_defaults_to_arc_storable_paths() -> None:
    store = ArcStateStore()

    assert store.sidebar_path.name == "StorableSidebar.json"
    assert store.archive_path.name == "StorableArchiveItems.json"
    assert store.command_ranking_path.name == "StorableCommandBarAdditionalRanking.json"
