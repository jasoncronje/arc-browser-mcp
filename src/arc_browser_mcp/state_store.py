from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from arc_browser_mcp.models import ArcFolderRecord, ArcSpaceRecord, ArcTabRecord, SourceInfo
from arc_browser_mcp.url_utils import (
    apple_time_to_datetime,
    duplicate_key_for_url,
    extract_domain,
    normalize_text,
)

ARC_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Arc"


@dataclass(frozen=True)
class ArcStateSnapshot:
    spaces: list[ArcSpaceRecord]
    folders: list[ArcFolderRecord]
    tabs: list[ArcTabRecord]
    recovery_candidates: dict[str, list[dict[str, object]]]
    warnings: list[str]


class ArcStateStore:
    def __init__(
        self,
        sidebar_path: Path | None = None,
        archive_path: Path | None = None,
        command_ranking_path: Path | None = None,
        backup_paths: list[Path] | None = None,
    ) -> None:
        self.sidebar_path = sidebar_path or ARC_SUPPORT_DIR / "StorableSidebar.json"
        self.archive_path = archive_path or ARC_SUPPORT_DIR / "StorableArchiveItems.json"
        self.command_ranking_path = (
            command_ranking_path
            or ARC_SUPPORT_DIR / "StorableCommandBarAdditionalRanking.json"
        )
        self.backup_paths = backup_paths

    def load(self, *, include_recovery: bool = False) -> ArcStateSnapshot:
        payload = json.loads(self.sidebar_path.read_text())
        snapshot = _SidebarParser(payload=payload, path=self.sidebar_path).parse()
        if not include_recovery:
            return snapshot
        return replace(
            snapshot,
            recovery_candidates=self._recovery_candidates(snapshot.tabs),
        )

    def _backup_paths(self) -> list[Path]:
        if self.backup_paths is not None:
            return self.backup_paths
        return sorted(self.sidebar_path.parent.glob("StorableSidebar.*.json"))

    def _recovery_candidates(
        self,
        current_tabs: list[ArcTabRecord],
    ) -> dict[str, list[dict[str, object]]]:
        missing_tabs = {tab.id: tab for tab in current_tabs if tab.is_missing_url}
        missing_tab_ids = set(missing_tabs)
        candidates: dict[str, list[dict[str, object]]] = {
            tab_id: [] for tab_id in missing_tab_ids
        }
        if not missing_tab_ids:
            return candidates

        for path in self._backup_paths():
            if not path.exists():
                continue
            try:
                backup_snapshot = _SidebarParser(
                    payload=json.loads(path.read_text()),
                    path=path,
                ).parse()
            except (OSError, json.JSONDecodeError):
                continue

            for tab in backup_snapshot.tabs:
                if tab.id in missing_tab_ids and tab.url:
                    candidates[tab.id].append(
                        {
                            "url": tab.url,
                            "title": tab.title,
                            "source": path.name,
                            "match": "same_tab_id_in_state_backup",
                            "confidence": "high",
                        }
                    )
        self._add_json_recovery_candidates(
            path=self.archive_path,
            missing_tabs=missing_tabs,
            candidates=candidates,
            match="matching_title_in_archive",
        )
        self._add_json_recovery_candidates(
            path=self.command_ranking_path,
            missing_tabs=missing_tabs,
            candidates=candidates,
            match="matching_title_in_command_ranking",
        )
        return candidates

    def _add_json_recovery_candidates(
        self,
        *,
        path: Path,
        missing_tabs: dict[str, ArcTabRecord],
        candidates: dict[str, list[dict[str, object]]],
        match: str,
    ) -> None:
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return

        seen = {
            (tab_id, str(candidate.get("url")), str(candidate.get("source")))
            for tab_id, tab_candidates in candidates.items()
            for candidate in tab_candidates
        }
        titles = {
            tab_id: normalize_text(tab.title)
            for tab_id, tab in missing_tabs.items()
            if normalize_text(tab.title)
        }
        for record in _iter_json_records(payload):
            url = _first_string(record, ("url", "URL", "savedURL", "savedUrl", "href"))
            title = _first_string(record, ("title", "savedTitle", "saved_title", "name"))
            if not url or not title:
                continue
            normalized_title = normalize_text(title)
            for tab_id, missing_title in titles.items():
                key = (tab_id, url, path.name)
                if normalized_title != missing_title or key in seen:
                    continue
                candidates[tab_id].append(
                    {
                        "url": url,
                        "title": title,
                        "source": path.name,
                        "match": match,
                        "confidence": "medium",
                    }
                )
                seen.add(key)


def _pairs(value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return [(str(key), _unwrap_value_record(item)) for key, item in value.items()]
    if not isinstance(value, list):
        return []

    if _is_flat_pair_list(value):
        return [
            (str(value[index]), _unwrap_value_record(value[index + 1]))
            for index in range(0, len(value), 2)
        ]

    pairs: list[tuple[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            if "key" in item:
                pairs.append((str(item["key"]), _unwrap_value_record(item.get("value"))))
            elif len(item) == 1:
                key, pair_value = next(iter(item.items()))
                pairs.append((str(key), _unwrap_value_record(pair_value)))
        elif isinstance(item, list | tuple) and len(item) == 2:
            pairs.append((str(item[0]), _unwrap_value_record(item[1])))
    return pairs


def _is_flat_pair_list(value: list[Any]) -> bool:
    if len(value) % 2 != 0:
        return False
    return all(
        not isinstance(value[index], dict | list | tuple)
        for index in range(0, len(value), 2)
    )


def _unwrap_value_record(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _iter_json_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        records.append(value)
        for item in value.values():
            records.extend(_iter_json_records(item))
    elif isinstance(value, list):
        for item in value:
            records.extend(_iter_json_records(item))
    return records


def _first_string(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _child_ids(item: dict[str, Any]) -> list[str]:
    children = (
        item.get("childrenIds")
        or item.get("childrenIDs")
        or item.get("childIds")
        or item.get("childIDs")
        or []
    )
    if isinstance(children, dict):
        children = children.get("_0") or children.get("items") or []
    return [str(child_id) for child_id in children if child_id]


def _space_profile_dir(space_model: dict[str, Any]) -> tuple[str | None, str | None]:
    profile = space_model.get("profile") or space_model.get("profileID") or {}
    if isinstance(profile, str):
        return profile, None

    custom = profile.get("custom", {}) if isinstance(profile, dict) else {}
    if not isinstance(custom, dict):
        return None, None

    profile_data = custom.get("_0") or custom.get(0) or {}
    if not isinstance(profile_data, dict):
        return None, None
    directory_basename = profile_data.get("directoryBasename")
    return directory_basename, directory_basename


class _SidebarParser:
    def __init__(self, payload: dict[str, Any], path: Path) -> None:
        self.payload = payload
        self.path = path
        self.source = SourceInfo(kind="state", name=path.name, path=str(path))
        self.items: dict[str, dict[str, Any]] = {}
        self.folders: list[ArcFolderRecord] = []
        self.tabs: list[ArcTabRecord] = []
        self.warnings: list[str] = []

    def parse(self) -> ArcStateSnapshot:
        sync_data = self.payload.get("firebaseSyncState", {}).get("syncData", {})
        self.items = {
            item_id: item
            for item_id, item in _pairs(sync_data.get("items", []))
            if isinstance(item, dict)
        }
        spaces = [self._space_with_counts(space) for space in self._parse_spaces(sync_data)]
        self._mark_duplicates()
        return ArcStateSnapshot(
            spaces=spaces,
            folders=self.folders,
            tabs=self.tabs,
            recovery_candidates={},
            warnings=self.warnings,
        )

    def _parse_spaces(self, sync_data: dict[str, Any]) -> list[ArcSpaceRecord]:
        spaces: list[ArcSpaceRecord] = []
        for space_id, space_model in _pairs(sync_data.get("spaceModels", [])):
            if not isinstance(space_model, dict):
                continue

            containers = dict(_pairs(space_model.get("containerIDs", [])))
            pinned_container_id = containers.get("pinned") or containers.get("pinned-root")
            unpinned_container_id = containers.get("unpinned") or containers.get("unpinned-root")
            profile_id, profile_dir = _space_profile_dir(space_model)
            space = ArcSpaceRecord(
                id=space_id,
                title=space_model.get("title") or "",
                profile_id=profile_id,
                profile_dir=profile_dir,
                window_id=None,
                pinned_container_id=pinned_container_id,
                unpinned_container_id=unpinned_container_id,
                counts={},
                sources=[self.source],
            )
            spaces.append(space)
            if pinned_container_id:
                self._walk_children(
                    parent_id=pinned_container_id,
                    space=space,
                    location="pinned",
                    folder_path=[],
                )
            if unpinned_container_id:
                self._walk_children(
                    parent_id=unpinned_container_id,
                    space=space,
                    location="unpinned",
                    folder_path=[],
                )
        return spaces

    def _walk_children(
        self,
        parent_id: str,
        space: ArcSpaceRecord,
        location: str,
        folder_path: list[str],
    ) -> int:
        tab_count = 0
        for child_id in _child_ids(self.items.get(parent_id, {})):
            item = self.items.get(child_id)
            if item is None:
                self.warnings.append(f"Missing sidebar item: {child_id}")
                continue

            tab_data = self._tab_data(item)
            if tab_data is not None:
                self.tabs.append(
                    self._tab_record(
                        item_id=child_id,
                        item=item,
                        tab=tab_data,
                        space=space,
                        location=location,
                        parent_id=parent_id,
                        folder_path=folder_path,
                    )
                )
                tab_count += 1
                continue

            title = self._item_title(item)
            child_folder_path = [*folder_path, title] if title else folder_path
            folder_tab_count = self._walk_children(
                parent_id=child_id,
                space=space,
                location=location,
                folder_path=child_folder_path,
            )
            self.folders.append(
                ArcFolderRecord(
                    id=child_id,
                    title=title,
                    space_id=space.id,
                    location=location,
                    parent_id=item.get("parentID") or item.get("parentId") or parent_id,
                    folder_path=child_folder_path,
                    child_count=len(_child_ids(item)),
                    tab_count=folder_tab_count,
                    sources=[self.source],
                )
            )
            tab_count += folder_tab_count
        return tab_count

    def _tab_record(
        self,
        item_id: str,
        item: dict[str, Any],
        tab: dict[str, Any],
        space: ArcSpaceRecord,
        location: str,
        parent_id: str,
        folder_path: list[str],
    ) -> ArcTabRecord:
        title = tab.get("savedTitle") or self._item_title(item)
        url = tab.get("savedURL") or tab.get("savedUrl") or tab.get("url") or ""
        return ArcTabRecord(
            id=item_id,
            title=title,
            url=url,
            domain=extract_domain(url),
            space_id=space.id,
            space_title=space.title,
            profile_id=space.profile_id,
            profile_dir=space.profile_dir,
            location=location,
            parent_id=item.get("parentID") or item.get("parentId") or parent_id,
            folder_path=folder_path,
            created_at=apple_time_to_datetime(_first_present(item, "createdAt", "created_at")),
            last_active_at=apple_time_to_datetime(
                _first_present(tab, "timeLastActiveAt", "lastActiveAt", "last_active_at")
            ),
            history_last_visit_at=None,
            visit_count=None,
            typed_count=None,
            loading=None,
            is_duplicate=False,
            duplicate_key=duplicate_key_for_url(url),
            is_missing_url=url == "",
            is_restored_placeholder=url == "" and title != "",
            sources=[self.source],
        )

    def _space_with_counts(self, space: ArcSpaceRecord) -> ArcSpaceRecord:
        space_tabs = [tab for tab in self.tabs if tab.space_id == space.id]
        return replace(
            space,
            counts={
                "pinned": sum(1 for tab in space_tabs if tab.location == "pinned"),
                "unpinned": sum(1 for tab in space_tabs if tab.location == "unpinned"),
                "folders": sum(1 for folder in self.folders if folder.space_id == space.id),
                "missing_urls": sum(1 for tab in space_tabs if tab.is_missing_url),
            },
        )

    def _mark_duplicates(self) -> None:
        key_counts = Counter(tab.duplicate_key for tab in self.tabs if tab.duplicate_key)
        self.tabs = [
            replace(tab, is_duplicate=key_counts[tab.duplicate_key] > 1)
            if tab.duplicate_key
            else tab
            for tab in self.tabs
        ]

    @staticmethod
    def _tab_data(item: dict[str, Any]) -> dict[str, Any] | None:
        data = item.get("data", {})
        tab = data.get("tab") if isinstance(data, dict) else None
        return tab if isinstance(tab, dict) else None

    @staticmethod
    def _item_title(item: dict[str, Any]) -> str:
        if item.get("title"):
            return item["title"]
        data = item.get("data", {})
        if isinstance(data, dict):
            return data.get("title") or ""
        return ""


def _first_present(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None
