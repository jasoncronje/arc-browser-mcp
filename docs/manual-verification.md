# Manual Verification

Run these checks on macOS with Arc installed. Mutating checks affect visible Arc state, so use disposable tabs and URLs.

## Automated read-only smoke

Run the local smoke command first:

```bash
uv run arc-browser-mcp smoke --read-only
```

This checks read-only inventory tools, including `arc_get_overview` and
`arc_query_tabs`, without calling mutating tools.

## Read-only inventory

1. Open Arc.
2. Run `uv run arc-browser-mcp smoke --read-only`.
3. Confirm `arc_get_overview` and `arc_query_tabs` pass.
4. In an MCP client, call `arc_get_overview`.
5. Confirm counts roughly match Arc's visible Space/sidebar inventory.
6. Call `arc_query_tabs` with a known title, domain, Space id, and `location`.
7. Confirm returned rows include explicit tab ids and compact metadata.
8. Call `arc_get_sidebar_tree` for a known Space.
9. Confirm pinned, unpinned, and folder structure are represented.
10. Call `arc_search_history` for a recent known page.
11. Confirm history rows include profile and visit metadata.

## Background read behavior

1. Open Arc.
2. Switch focus to another app.
3. Call `arc_get_overview`.
4. Confirm Spaces and tab counts are returned and Arc does not become frontmost.

## Mutating behavior

1. Call `arc_get_overview` and note the current Space and active tab.
2. Call `arc_query_tabs`, then copy known Space and tab ids for the checks below.
3. Call `arc_focus_space` with another Space id.
4. Confirm Arc changes active Space.
5. Call `arc_select_tab` with a known tab id.
6. Confirm Arc selects that tab.
7. Call `arc_create_tab` with the current Space id, current window id when
   available, and `https://example.com`.
8. Confirm the result includes a new explicit `tab_id`.
9. Call `arc_open_url` with that returned tab id and another disposable URL.
10. Confirm only that tab navigates.
11. Call `arc_reload_tabs` with exactly that disposable tab id.
12. Confirm the tab reloads.
13. Call `arc_close_tabs` with exactly that disposable tab id.
14. Confirm only the disposable tab closes. Destructive actions require explicit tab ids.

## Batch close safety

1. Create two disposable tabs with `arc_create_tab`.
2. Copy the returned tab ids.
3. Call `arc_close_tabs` with `dry_run: true`.
4. Confirm no tab closes.
5. Call `arc_close_tabs` with exactly one disposable tab id.
6. Confirm only that tab closes.

## Opt-in tools

1. Without env vars, call `arc_execute_javascript` with a disposable or known `tab_id` and harmless JavaScript:

   ```json
   {
     "tab_id": "known-tab-id",
     "javascript": "1 + 1"
   }
   ```

2. Confirm the tool reports that `ARC_MCP_ENABLE_JAVASCRIPT=1` is required.
3. Set `ARC_MCP_ENABLE_JAVASCRIPT=1` only in a test client config.
4. Call `arc_execute_javascript` with a disposable or known `tab_id` and harmless JavaScript:

   ```json
   {
     "tab_id": "known-tab-id",
     "javascript": "1 + 1"
   }
   ```

5. Confirm the result is returned for only the explicit tab id.
