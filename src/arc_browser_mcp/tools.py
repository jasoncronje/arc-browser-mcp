from __future__ import annotations

from typing import Any

from .arc import ArcAdapter
from .handlers import (
    MutatingArcAdapter,
    handle_analyze_tabs,
    handle_close_tabs,
    handle_create_tab,
    handle_execute_javascript,
    handle_focus_space,
    handle_get_overview,
    handle_get_sidebar_tree,
    handle_get_tab,
    handle_open_url,
    handle_query_tabs,
    handle_reload_tabs,
    handle_search_history,
    handle_select_tab,
)
from .history_store import ArcHistoryStore
from .index import ArcIndexCache

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
}

MUTATING_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
}

DESTRUCTIVE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
}


def register_tools(
    mcp: Any,
    adapter: MutatingArcAdapter | None = None,
    index_cache: Any | None = None,
    history_store: Any | None = None,
) -> None:
    arc = adapter if adapter is not None else ArcAdapter()
    cache = index_cache if index_cache is not None else ArcIndexCache()
    history = history_store if history_store is not None else ArcHistoryStore()

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def arc_get_overview() -> dict[str, Any]:
        """Get compact Arc inventory, counts, source health, and live context when available."""
        return handle_get_overview(cache)

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def arc_query_tabs(
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
        """List, filter, and search Arc tabs using the fast local Arc index."""
        return handle_query_tabs(
            cache,
            query=query,
            space_id=space_id,
            location=location,
            folder_id=folder_id,
            domain=domain,
            missing_url=missing_url,
            duplicate_key=duplicate_key,
            limit=limit,
            cursor=cursor,
        )

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def arc_get_tab(tab_id: str, include_recovery: bool = False) -> dict[str, Any]:
        """Get a full normalized Arc tab record by explicit tab id."""
        return handle_get_tab(cache, tab_id=tab_id, include_recovery=include_recovery)

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def arc_get_sidebar_tree(
        space_id: str | None = None,
        include_tabs: bool = False,
    ) -> dict[str, Any]:
        """Get Arc Space, pinned, unpinned, and folder hierarchy."""
        return handle_get_sidebar_tree(cache, space_id=space_id, include_tabs=include_tabs)

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def arc_search_history(
        query: str | None = None,
        domain: str | None = None,
        profile_id: str | None = None,
        include_hidden: bool = False,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search Arc Chromium history snapshots across local profiles."""
        return handle_search_history(
            history,
            query=query,
            domain=domain,
            profile_id=profile_id,
            include_hidden=include_hidden,
            limit=limit,
            cursor=cursor,
        )

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def arc_analyze_tabs(
        analyses: list[str],
        limit: int = 50,
        include_evidence: bool = True,
        stale_before: str | None = None,
    ) -> dict[str, Any]:
        """Analyze Arc tabs for duplicates, stale tabs, junk candidates, and missing URLs."""
        return handle_analyze_tabs(
            cache,
            analyses=analyses,
            limit=limit,
            include_evidence=include_evidence,
            stale_before=stale_before,
        )

    @mcp.tool(annotations=MUTATING_ANNOTATIONS)
    def arc_create_tab(
        space_id: str,
        url: str,
        window_id: str | None = None,
        select: bool = True,
    ) -> dict[str, object]:
        """Create a new Arc tab in an explicit Space and return its verified tab id."""
        return handle_create_tab(
            arc,
            space_id=space_id,
            url=url,
            window_id=window_id,
            select=select,
        )

    @mcp.tool(annotations=MUTATING_ANNOTATIONS)
    def arc_focus_space(space_id: str) -> dict[str, object]:
        """Focus an Arc Space by explicit id. This changes visible Arc state."""
        return handle_focus_space(arc, space_id=space_id)

    @mcp.tool(annotations=MUTATING_ANNOTATIONS)
    def arc_select_tab(tab_id: str) -> dict[str, object]:
        """Select an Arc tab by explicit id. This changes visible Arc state."""
        return handle_select_tab(arc, tab_id=tab_id)

    @mcp.tool(annotations=MUTATING_ANNOTATIONS)
    def arc_open_url(url: str, tab_id: str | None = None) -> dict[str, object]:
        """Navigate a specific Arc tab, or the active tab when explicitly omitted."""
        return handle_open_url(arc, url=url, tab_id=tab_id)

    @mcp.tool(annotations=MUTATING_ANNOTATIONS)
    def arc_reload_tabs(tab_ids: list[str]) -> dict[str, object]:
        """Reload one or more Arc tabs by explicit tab id."""
        return handle_reload_tabs(arc, tab_ids=tab_ids)

    @mcp.tool(annotations=DESTRUCTIVE_ANNOTATIONS)
    def arc_close_tabs(tab_ids: list[str], dry_run: bool = False) -> dict[str, object]:
        """Close one or more Arc tabs by explicit tab id. Use dry_run to preview."""
        return handle_close_tabs(arc, tab_ids=tab_ids, dry_run=dry_run)

    @mcp.tool(annotations=MUTATING_ANNOTATIONS)
    def arc_execute_javascript(tab_id: str, javascript: str) -> dict[str, object]:
        """Execute JavaScript in an Arc tab. Disabled unless ARC_MCP_ENABLE_JAVASCRIPT=1."""
        return handle_execute_javascript(arc, tab_id=tab_id, javascript=javascript)
