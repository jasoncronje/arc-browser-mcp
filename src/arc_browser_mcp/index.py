from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from arc_browser_mcp.history_store import ArcHistoryStore
from arc_browser_mcp.models import ArcFolderRecord, ArcSpaceRecord, ArcTabRecord, to_dict
from arc_browser_mcp.state_store import ArcStateStore
from arc_browser_mcp.url_utils import duplicate_key_for_url, extract_domain, normalize_text

StateSignature = tuple[tuple[str, int, int], ...] | None


class ArcIndexCache:
    def __init__(
        self,
        *,
        state_store: ArcStateStore | None = None,
        history_store: ArcHistoryStore | None = None,
    ) -> None:
        self.state_store = state_store or ArcStateStore()
        self.history_store = history_store or ArcHistoryStore()
        self._index: ArcIndex | None = None
        self._state_signature: StateSignature = None

    def get(self, *, include_recovery: bool = False) -> ArcIndex:
        state_signature = _state_signature(self.state_store)
        if (
            self._index is None
            or include_recovery
            or state_signature != self._state_signature
        ):
            snapshot = self.state_store.load(include_recovery=include_recovery)
            self._index = ArcIndex(
                spaces=snapshot.spaces,
                folders=snapshot.folders,
                tabs=snapshot.tabs,
                recovery_candidates=snapshot.recovery_candidates,
                warnings=snapshot.warnings,
                history_store=self.history_store,
            )
            self._state_signature = state_signature
        return self._index


class ArcIndex:
    def __init__(
        self,
        *,
        spaces: list[ArcSpaceRecord],
        folders: list[ArcFolderRecord],
        tabs: list[ArcTabRecord],
        recovery_candidates: dict[str, list[dict[str, object]]],
        warnings: list[str],
        history_store: ArcHistoryStore,
    ) -> None:
        self.spaces = spaces
        self.folders = folders
        self.tabs = tabs
        self.recovery_candidates = recovery_candidates
        self.warnings = warnings
        self.history_store = history_store
        self.tabs_by_id = {tab.id: tab for tab in tabs}
        self.folders_by_id = {folder.id: folder for folder in folders}
        self.spaces_by_id = {space.id: space for space in spaces}

    def overview(self) -> dict[str, Any]:
        return {
            "totals": {
                "spaces": len(self.spaces),
                "tabs": len(self.tabs),
                "pinned": sum(1 for tab in self.tabs if tab.location == "pinned"),
                "unpinned": sum(1 for tab in self.tabs if tab.location == "unpinned"),
                "folders": len(self.folders),
                "missing_urls": sum(1 for tab in self.tabs if tab.is_missing_url),
                "duplicates": sum(1 for tab in self.tabs if tab.is_duplicate),
            },
            "spaces": [to_dict(space) for space in self.spaces],
            "warnings": self.warnings,
        }

    def query_tabs(
        self,
        *,
        query: str | None = None,
        space_id: str | None = None,
        location: str | None = None,
        folder_id: str | None = None,
        domain: str | None = None,
        missing_url: bool | None = None,
        duplicate_key: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        matching_tabs = [
            tab
            for tab in self.tabs
            if self._matches_tab(
                tab,
                query=query,
                space_id=space_id,
                location=location,
                folder_id=folder_id,
                domain=domain,
                missing_url=missing_url,
                duplicate_key=duplicate_key,
            )
        ]
        start = _cursor_to_offset(cursor)
        end = start + max(limit, 0)
        next_cursor = str(end) if end < len(matching_tabs) else None
        return {
            "total": len(matching_tabs),
            "cursor": next_cursor,
            "items": [self._compact_tab(tab) for tab in matching_tabs[start:end]],
        }

    def _matches_tab(
        self,
        tab: ArcTabRecord,
        *,
        query: str | None,
        space_id: str | None,
        location: str | None,
        folder_id: str | None,
        domain: str | None,
        missing_url: bool | None,
        duplicate_key: str | None,
    ) -> bool:
        if space_id and tab.space_id != space_id:
            return False
        if location and tab.location != location:
            return False
        if folder_id and tab.parent_id != folder_id:
            return False
        if domain and tab.domain != _normalize_domain(domain):
            return False
        if missing_url is not None and tab.is_missing_url != missing_url:
            return False
        if duplicate_key and tab.duplicate_key != duplicate_key:
            return False
        if query:
            searchable = normalize_text(f"{tab.title} {tab.url} {tab.domain or ''}")
            return normalize_text(query) in searchable
        return True

    def _compact_tab(self, tab: ArcTabRecord) -> dict[str, Any]:
        return {
            "id": tab.id,
            "title": tab.title,
            "url": tab.url,
            "domain": tab.domain,
            "space_id": tab.space_id,
            "space_title": tab.space_title,
            "location": tab.location,
            "folder_path": tab.folder_path,
            "is_duplicate": tab.is_duplicate,
            "is_missing_url": tab.is_missing_url,
            "sources": to_dict(tab.sources),
        }

    def analyze_tabs(
        self,
        *,
        analyses: list[str],
        stale_before: datetime | None = None,
        limit: int = 50,
        include_evidence: bool = True,
    ) -> dict[str, Any]:
        groups: list[dict[str, Any]] = []
        for analysis in analyses:
            if analysis == "duplicates":
                groups.extend(self._duplicate_groups(include_evidence=include_evidence))
            elif analysis == "missing_url":
                groups.extend(self._missing_url_groups(include_evidence=include_evidence))
            elif analysis == "stale":
                groups.extend(
                    self._stale_groups(
                        stale_before=stale_before,
                        include_evidence=include_evidence,
                    )
                )
            elif analysis == "junk":
                groups.extend(self._junk_groups(include_evidence=include_evidence))
            elif analysis == "missing_url_recovery":
                groups.extend(
                    self._missing_url_recovery_groups(include_evidence=include_evidence)
                )
        return {"groups": groups[:limit], "total": len(groups)}

    def _duplicate_groups(self, *, include_evidence: bool) -> list[dict[str, Any]]:
        tabs_by_key: dict[str, list[ArcTabRecord]] = {}
        for tab in self.tabs:
            if tab.duplicate_key is None:
                continue
            tabs_by_key.setdefault(tab.duplicate_key, []).append(tab)

        groups: list[dict[str, Any]] = []
        for duplicate_key, tabs in tabs_by_key.items():
            if len(tabs) < 2:
                continue
            group: dict[str, Any] = {
                "analysis_type": "duplicates",
                "group_id": f"duplicate:{duplicate_key}",
                "reason": "Multiple active tabs share the same normalized URL.",
                "confidence": "high",
                "tab_ids": [tab.id for tab in tabs],
                "recommended_keep_tab_id": tabs[0].id,
                "suggested_action": (
                    "Informational only: review explicit tab IDs before closing duplicates."
                ),
                "duplicate_key": duplicate_key,
            }
            if include_evidence:
                group["evidence"] = {"tabs": [self._compact_tab(tab) for tab in tabs]}
            groups.append(group)
        return groups

    def _missing_url_groups(self, *, include_evidence: bool) -> list[dict[str, Any]]:
        tabs = [tab for tab in self.tabs if tab.is_missing_url]
        if not tabs:
            return []
        group: dict[str, Any] = {
            "analysis_type": "missing_url",
            "group_id": "missing_url:all",
            "reason": (
                "Tabs in current Arc state without saved URLs need hydration or "
                "recovery before action."
            ),
            "confidence": "high",
            "tab_ids": [tab.id for tab in tabs],
            "suggested_action": "Informational only: hydrate or recover URLs before taking action.",
        }
        if include_evidence:
            group["evidence"] = {"tabs": [self._compact_tab(tab) for tab in tabs]}
        return [group]

    def _activity_time(self, tab: ArcTabRecord) -> datetime | None:
        return tab.last_active_at or tab.history_last_visit_at or tab.created_at

    def _stale_groups(
        self,
        *,
        stale_before: datetime | None,
        include_evidence: bool,
    ) -> list[dict[str, Any]]:
        if stale_before is None:
            return []
        tabs = [
            tab
            for tab in self.tabs
            if (activity_time := self._activity_time(tab)) is not None
            and activity_time < stale_before
        ]
        if not tabs:
            return []
        stale_before_value = stale_before.isoformat()
        group: dict[str, Any] = {
            "analysis_type": "stale",
            "group_id": f"stale:before:{stale_before_value}",
            "reason": f"Tabs have no known activity after {stale_before_value}.",
            "confidence": "medium",
            "tab_ids": [tab.id for tab in tabs],
            "suggested_action": (
                "Informational only: review explicit tab IDs before closing stale tabs."
            ),
            "stale_before": stale_before_value,
        }
        if include_evidence:
            group["evidence"] = {
                "tabs": [
                    self._compact_tab(tab)
                    | {"activity_time": self._activity_time(tab).isoformat()}
                    for tab in tabs
                    if self._activity_time(tab) is not None
                ]
            }
        return [group]

    def _junk_groups(self, *, include_evidence: bool) -> list[dict[str, Any]]:
        tabs = [tab for tab in self.tabs if self._looks_like_junk(tab)]
        if not tabs:
            return []
        group: dict[str, Any] = {
            "analysis_type": "junk",
            "group_id": "junk:heuristic",
            "reason": (
                "Tabs match low-confidence clutter heuristics such as browser, login, "
                "or search URLs."
            ),
            "confidence": "low",
            "tab_ids": [tab.id for tab in tabs],
            "suggested_action": (
                "Informational only: inspect explicit tab IDs before taking action."
            ),
        }
        if include_evidence:
            group["evidence"] = {"tabs": [self._compact_tab(tab) for tab in tabs]}
        return [group]

    def _looks_like_junk(self, tab: ArcTabRecord) -> bool:
        url = tab.url.lower()
        domain = (tab.domain or "").lower()
        return (
            url.startswith("chrome://")
            or "search?" in url
            or any(part in domain for part in ("login", "auth", "signin", "accounts"))
        )

    def _missing_url_recovery_groups(self, *, include_evidence: bool) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for tab_id, candidates in self.recovery_candidates.items():
            group: dict[str, Any] = {
                "analysis_type": "missing_url_recovery",
                "group_id": f"missing_url_recovery:{tab_id}",
                "reason": "Missing URL tab has one or more possible recovery candidates.",
                "confidence": "medium",
                "tab_ids": [tab_id],
                "suggested_action": (
                    "Informational only: use recovery candidates to hydrate before taking action."
                ),
            }
            if include_evidence:
                group["evidence"] = {"candidates": candidates}
            groups.append(group)
        return groups

    def get_tab(self, tab_id: str) -> dict[str, Any] | None:
        tab = self.tabs_by_id.get(tab_id)
        if tab is None:
            return None
        hydrated = to_dict(tab)
        if tab_id in self.recovery_candidates:
            hydrated["recovery_candidates"] = self.recovery_candidates[tab_id]
        hydrated["history_entries"] = self._history_entries(tab)
        return hydrated

    def _history_entries(self, tab: ArcTabRecord) -> list[dict[str, Any]]:
        if tab.domain is None:
            return []
        rows = self.history_store.search(
            domain=tab.domain,
            include_hidden=True,
            limit=50,
        )
        return [
            to_dict(row)
            for row in rows
            if row.url == tab.url
            or (
                tab.duplicate_key is not None
                and duplicate_key_for_url(row.url) == tab.duplicate_key
            )
        ]

    def sidebar_tree(
        self,
        *,
        space_id: str | None = None,
        include_tabs: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        spaces = [space for space in self.spaces if space_id is None or space.id == space_id]
        return {
            "spaces": [self._space_node(space, include_tabs=include_tabs) for space in spaces]
        }

    def _space_node(
        self,
        space: ArcSpaceRecord,
        *,
        include_tabs: bool,
    ) -> dict[str, Any]:
        children = [
            root
            for root in (
                self._root_node(
                    space=space,
                    root_id=space.pinned_container_id,
                    location="pinned",
                    include_tabs=include_tabs,
                ),
                self._root_node(
                    space=space,
                    root_id=space.unpinned_container_id,
                    location="unpinned",
                    include_tabs=include_tabs,
                ),
            )
            if root is not None
        ]
        return {"type": "space", **to_dict(space), "children": children}

    def _root_node(
        self,
        *,
        space: ArcSpaceRecord,
        root_id: str | None,
        location: str,
        include_tabs: bool,
    ) -> dict[str, Any] | None:
        if root_id is None:
            return None
        children = [
            self._folder_node(folder, include_tabs=include_tabs)
            for folder in self.folders
            if folder.space_id == space.id and folder.parent_id == root_id
        ]
        if include_tabs:
            children.extend(
                self._compact_tab(tab) | {"type": "tab"}
                for tab in self.tabs
                if tab.space_id == space.id and tab.parent_id == root_id
            )
        location_tabs = [
            tab
            for tab in self.tabs
            if tab.space_id == space.id and tab.location == location
        ]
        return {
            "type": "root",
            "id": root_id,
            "location": location,
            "children": children,
            "counts": {
                "tabs": len(location_tabs),
                "folders": sum(
                    1
                    for folder in self.folders
                    if folder.space_id == space.id and folder.location == location
                ),
                "missing_urls": sum(1 for tab in location_tabs if tab.is_missing_url),
            },
        }

    def _folder_node(
        self,
        folder: ArcFolderRecord,
        *,
        include_tabs: bool,
    ) -> dict[str, Any]:
        children = [
            self._folder_node(child, include_tabs=include_tabs)
            for child in self.folders
            if child.parent_id == folder.id
        ]
        if include_tabs:
            children.extend(
                self._compact_tab(tab) | {"type": "tab"}
                for tab in self.tabs
                if tab.parent_id == folder.id
            )
        return {
            "type": "folder",
            **to_dict(folder),
            "children": children,
        }

    def _parent_is_folder(self, item: ArcFolderRecord | ArcTabRecord) -> bool:
        return item.parent_id in self.folders_by_id


def _cursor_to_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(int(cursor), 0)
    except ValueError:
        return 0


def _normalize_domain(domain: str) -> str | None:
    return extract_domain(domain) or domain.lower().removeprefix("www.")


def _state_signature(state_store: object) -> StateSignature:
    signature: list[tuple[str, int, int]] = []
    for attr in ("sidebar_path", "archive_path", "command_ranking_path"):
        path = getattr(state_store, attr, None)
        if path is None:
            continue
        path = Path(path)
        if not path.exists():
            continue
        stat = path.stat()
        signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature) if signature else None
