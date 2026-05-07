from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from .errors import ArcBrowserMCPError
from .models import ArcSpace, ArcTab, ArcWindow, to_dict
from .url_utils import duplicate_key_for_url


class ReadOnlyArcAdapter(Protocol):
    def get_active_context(self, window_id: str | None = None) -> ArcWindow: ...

    def list_spaces(self, window_id: str | None = None) -> list[ArcSpace]: ...

    def list_tabs(
        self,
        *,
        window_id: str | None = None,
        space_id: str | None = None,
    ) -> list[ArcTab]: ...


class ArcIndexProvider(Protocol):
    def get(self, *, include_recovery: bool = False) -> Any: ...


class ArcHistorySearchProvider(Protocol):
    def search(self, **kwargs: Any) -> list[Any]: ...


class MutatingArcAdapter(ReadOnlyArcAdapter, Protocol):
    def focus_space(self, space_id: str) -> dict[str, object]: ...

    def select_tab(self, tab_id: str) -> dict[str, object]: ...

    def close_tab(self, tab_id: str) -> dict[str, object]: ...

    def close_tabs(
        self,
        tab_ids: list[str],
        dry_run: bool = False,
    ) -> dict[str, object]: ...

    def open_url(self, url: str, tab_id: str | None = None) -> dict[str, object]: ...

    def reload_tab(self, tab_id: str) -> dict[str, object]: ...

    def reload_tabs(self, tab_ids: list[str]) -> dict[str, object]: ...

    def execute_javascript(self, tab_id: str, javascript: str) -> dict[str, object]: ...

    def add_tab_to_space(
        self,
        space_id: str,
        url: str,
        window_id: str | None = None,
    ) -> dict[str, object]: ...


def handle_get_overview(index_cache: ArcIndexProvider, **kwargs: Any) -> dict[str, Any]:
    return index_cache.get().overview(**kwargs)


def handle_query_tabs(index_cache: ArcIndexProvider, **kwargs: Any) -> dict[str, Any]:
    return index_cache.get().query_tabs(**kwargs)


def handle_get_tab(
    index_cache: ArcIndexProvider,
    tab_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return index_cache.get(
        include_recovery=kwargs.get("include_recovery", False)
    ).get_tab(tab_id)


def handle_get_sidebar_tree(
    index_cache: ArcIndexProvider,
    **kwargs: Any,
) -> dict[str, Any]:
    return index_cache.get().sidebar_tree(**kwargs)


def handle_analyze_tabs(index_cache: ArcIndexProvider, **kwargs: Any) -> dict[str, Any]:
    include_recovery = "missing_url_recovery" in kwargs.get("analyses", [])
    if "stale_before" in kwargs:
        kwargs = {**kwargs, "stale_before": _parse_iso_datetime(kwargs["stale_before"])}
    return index_cache.get(include_recovery=include_recovery).analyze_tabs(**kwargs)


def handle_search_history(
    history_store: ArcHistorySearchProvider,
    **kwargs: Any,
) -> dict[str, Any]:
    limit = int(kwargs.pop("limit", 50))
    cursor = int(kwargs.pop("cursor", 0) or 0)
    fetch_limit = cursor + limit + 1
    rows = history_store.search(limit=fetch_limit, **kwargs)
    page = rows[cursor : cursor + limit]
    has_next_page = len(rows) > cursor + limit
    next_cursor = str(cursor + limit) if has_next_page else None
    total = cursor + limit + 1 if has_next_page else len(rows)
    return {"total": total, "cursor": next_cursor, "items": to_dict(page)}


def handle_get_active_context(
    adapter: ReadOnlyArcAdapter,
    window_id: str | None = None,
) -> dict[str, Any]:
    return to_dict(adapter.get_active_context(window_id=window_id))


def handle_list_spaces(
    adapter: ReadOnlyArcAdapter,
    window_id: str | None = None,
) -> list[dict[str, Any]]:
    return to_dict(adapter.list_spaces(window_id=window_id))


def handle_list_tabs(
    adapter: ReadOnlyArcAdapter,
    window_id: str | None = None,
    space_id: str | None = None,
) -> list[dict[str, Any]]:
    return to_dict(adapter.list_tabs(window_id=window_id, space_id=space_id))


def handle_focus_space(adapter: MutatingArcAdapter, space_id: str) -> dict[str, object]:
    return adapter.focus_space(space_id)


def handle_select_tab(adapter: MutatingArcAdapter, tab_id: str) -> dict[str, object]:
    return adapter.select_tab(tab_id)


def handle_close_tab(adapter: MutatingArcAdapter, tab_id: str) -> dict[str, object]:
    return adapter.close_tab(tab_id)


def handle_close_tabs(
    adapter: MutatingArcAdapter,
    tab_ids: list[str],
    dry_run: bool = False,
) -> dict[str, object]:
    clean_tab_ids = _require_explicit_tab_ids(tab_ids)
    close_tabs = getattr(adapter, "close_tabs", None)
    if close_tabs is not None:
        return close_tabs(clean_tab_ids, dry_run=dry_run)
    if dry_run:
        return {
            "results": [
                {"tab_id": tab_id, "closed": False, "dry_run": True}
                for tab_id in clean_tab_ids
            ]
        }
    return {"results": [adapter.close_tab(tab_id) for tab_id in clean_tab_ids]}


def handle_open_url(
    adapter: MutatingArcAdapter,
    url: str,
    tab_id: str | None = None,
) -> dict[str, object]:
    return adapter.open_url(url, tab_id=tab_id)


def handle_reload_tab(adapter: MutatingArcAdapter, tab_id: str) -> dict[str, object]:
    return adapter.reload_tab(tab_id)


def handle_reload_tabs(
    adapter: MutatingArcAdapter,
    tab_ids: list[str],
) -> dict[str, object]:
    clean_tab_ids = _require_explicit_tab_ids(tab_ids)
    reload_tabs = getattr(adapter, "reload_tabs", None)
    if reload_tabs is not None:
        return reload_tabs(clean_tab_ids)
    return {"results": [adapter.reload_tab(tab_id) for tab_id in clean_tab_ids]}


def handle_create_tab(
    adapter: MutatingArcAdapter,
    *,
    space_id: str,
    url: str,
    window_id: str | None = None,
    select: bool = True,
    verify_timeout_seconds: float = 5.0,
) -> dict[str, object]:
    clean_space_id = space_id.strip()
    clean_url = url.strip()
    if not clean_space_id:
        raise ArcBrowserMCPError("explicit space_id is required.")
    if not clean_url:
        raise ArcBrowserMCPError("url is required.")

    before_ids = {
        tab.id
        for tab in adapter.list_tabs(space_id=clean_space_id, window_id=window_id)
        if tab.id
    }
    adapter.add_tab_to_space(clean_space_id, clean_url, window_id=window_id)
    created_tab = _wait_for_created_tab(
        adapter,
        space_id=clean_space_id,
        window_id=window_id,
        url=clean_url,
        before_ids=before_ids,
        timeout_seconds=verify_timeout_seconds,
    )
    if created_tab is None:
        raise ArcBrowserMCPError("Could not verify created tab in requested Space.")
    if select:
        adapter.select_tab(created_tab.id)
    return {
        "tab_id": created_tab.id,
        "space_id": clean_space_id,
        "url": created_tab.url,
        "selected": select,
    }


def handle_execute_javascript(
    adapter: MutatingArcAdapter,
    tab_id: str,
    javascript: str,
    *,
    enabled: bool | None = None,
) -> dict[str, object]:
    if enabled is None:
        enabled = os.getenv("ARC_MCP_ENABLE_JAVASCRIPT") == "1"
    if not enabled:
        raise ArcBrowserMCPError(
            "arc_execute_javascript is disabled. "
            "Set ARC_MCP_ENABLE_JAVASCRIPT=1 to enable it."
        )
    return adapter.execute_javascript(tab_id, javascript)


def handle_add_tab_to_space(
    adapter: MutatingArcAdapter,
    space_id: str,
    url: str,
    *,
    enabled: bool | None = None,
) -> dict[str, object]:
    if enabled is None:
        enabled = os.getenv("ARC_MCP_ENABLE_EXPERIMENTAL") == "1"
    if not enabled:
        raise ArcBrowserMCPError(
            "arc_add_tab_to_space is experimental. "
            "Set ARC_MCP_ENABLE_EXPERIMENTAL=1 to enable it."
        )
    return adapter.add_tab_to_space(space_id, url)


def _require_explicit_tab_ids(tab_ids: list[str]) -> list[str]:
    clean_tab_ids = [tab_id.strip() for tab_id in tab_ids]
    if not clean_tab_ids or any(not tab_id or ":" in tab_id for tab_id in clean_tab_ids):
        raise ArcBrowserMCPError("explicit tab_ids are required.")
    return clean_tab_ids


def _parse_iso_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ArcBrowserMCPError("stale_before must be an ISO datetime string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArcBrowserMCPError("stale_before must be an ISO datetime string.") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _wait_for_created_tab(
    adapter: MutatingArcAdapter,
    *,
    space_id: str,
    window_id: str | None,
    url: str,
    before_ids: set[str],
    timeout_seconds: float = 5.0,
    interval_seconds: float = 0.25,
) -> ArcTab | None:
    deadline = time.monotonic() + timeout_seconds
    expected_key = duplicate_key_for_url(url)
    while True:
        for tab in adapter.list_tabs(space_id=space_id, window_id=window_id):
            if tab.id in before_ids:
                continue
            if tab.url == url or duplicate_key_for_url(tab.url) == expected_key:
                return tab
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval_seconds)
