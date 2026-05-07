from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ArcSpace:
    id: str
    title: str
    window_id: str | None = None
    window_title: str | None = None
    tab_count: int | None = None


@dataclass(frozen=True)
class ArcTab:
    id: str
    title: str
    url: str
    loading: bool
    location: str
    space_id: str | None = None
    space_title: str | None = None
    window_id: str | None = None
    window_title: str | None = None


@dataclass(frozen=True)
class ArcWindow:
    id: str
    title: str
    active_space: ArcSpace | None = None
    active_tab: ArcTab | None = None


@dataclass(frozen=True)
class SourceInfo:
    kind: str
    name: str
    path: str | None = None


@dataclass(frozen=True)
class ArcFolderRecord:
    id: str
    title: str
    space_id: str
    location: str
    parent_id: str | None
    folder_path: list[str]
    child_count: int
    tab_count: int
    sources: list[SourceInfo]


@dataclass(frozen=True)
class ArcSpaceRecord:
    id: str
    title: str
    profile_id: str | None
    profile_dir: str | None
    window_id: str | None
    pinned_container_id: str | None
    unpinned_container_id: str | None
    counts: dict[str, int]
    sources: list[SourceInfo]


@dataclass(frozen=True)
class ArcHistoryRecord:
    id: str
    url: str
    title: str
    domain: str | None
    profile_id: str
    profile_dir: str
    last_visit_at: datetime | None
    visit_count: int | None
    typed_count: int | None
    hidden: bool
    sources: list[SourceInfo]


@dataclass(frozen=True)
class ArcTabRecord:
    id: str
    title: str
    url: str
    domain: str | None
    space_id: str | None
    space_title: str | None
    profile_id: str | None
    profile_dir: str | None
    location: str
    parent_id: str | None
    folder_path: list[str]
    created_at: datetime | None
    last_active_at: datetime | None
    history_last_visit_at: datetime | None
    visit_count: int | None
    typed_count: int | None
    loading: bool | None
    is_duplicate: bool
    duplicate_key: str | None
    is_missing_url: bool
    is_restored_placeholder: bool
    sources: list[SourceInfo]


def to_dict(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return to_dict(asdict(value))
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return _strip_none({key: to_dict(item) for key, item in value.items()})
    return value


def _strip_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_strip_none(item) for item in value]
    return value
