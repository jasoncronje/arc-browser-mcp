# Arc Browser MCP

Arc Browser MCP is a local stdio MCP server for inspecting and controlling
[Arc Browser](https://arc.net/) Spaces and tabs on macOS.

It gives MCP clients such as Codex, Claude Code, opencode, and Claude Desktop a
structured way to read Arc's local sidebar/history data and perform explicit
Arc actions like focusing Spaces, selecting tabs, creating tabs, navigating
tabs, reloading tabs, closing tabs, and optionally executing JavaScript.

## Why This Exists

I built this because my Arc setup had become a very specific kind of personal
knowledge system: lots of tabs, spread across lots of Spaces, quietly standing
in for bookmarks, reading lists, project context, and things I was definitely
going to deal with later.

That works until it does not. Once the browser becomes both workspace and
storage, it gets hard to tell what is still useful, what is duplicated, what
belongs in a second brain, and what can finally be closed. Arc Browser MCP makes
that state legible to local agents so they can help inspect, search, organize,
summarize, save, and clean up tabs with explicit user-controlled actions.

Arc automation is useful for focused browser actions, but it is not
the best source for a complete, background-safe inventory of Spaces, folders,
pinned and unpinned tabs, and history. In local testing with my Arc profile,
reading all tabs through Arc automation could take up to 30 seconds; reading the
same state from Arc's local JSON files took less than 10 ms, over 3,000x
faster. Mutations use Arc automation because those changes take effect
immediately without requiring a browser restart.

## Tools

The server exposes compact v2 tools grouped by behavior. Read tools inspect
local Arc data and do not intentionally change visible browser state. Create,
edit, and delete tools automate Arc and can change what is visible in the
browser.

### Read Tools

| Tool | Description |
| --- | --- |
| `arc_get_overview` | Returns a compact inventory of Arc Spaces, tab counts, pinned/unpinned counts, folder counts, missing URL counts, duplicate counts, and source warnings. |
| `arc_query_tabs` | Lists, filters, and searches active Arc tabs using the local Arc index. Supports `query`, `space_id`, `location`, `folder_id`, `domain`, `missing_url`, `duplicate_key`, `limit`, and `cursor`. |
| `arc_get_tab` | Returns a full normalized tab record for an explicit `tab_id`, including source metadata and matching history entries. Set `include_recovery` to include recovery candidates for tabs with missing URLs. |
| `arc_get_sidebar_tree` | Returns the Space, pinned, unpinned, and folder hierarchy. Set `include_tabs` to include compact tab records inside the tree. |
| `arc_search_history` | Searches local Arc Chromium history snapshots across profiles. Supports `query`, `domain`, `profile_id`, `include_hidden`, `limit`, and `cursor`. |
| `arc_analyze_tabs` | Analyzes tabs for `duplicates`, `missing_url`, `stale`, `junk`, and `missing_url_recovery`. Results are informational and include explicit tab IDs for review. |

### Create Tools

| Tool | Description |
| --- | --- |
| `arc_create_tab` | Creates a new tab in an explicit Arc Space. Requires `space_id` and `url`, accepts optional `window_id`, and returns the verified new `tab_id`. Set `select` to `false` to create without selecting when supported by the flow. |

### Edit And Navigation Tools

| Tool | Description |
| --- | --- |
| `arc_focus_space` | Focuses an Arc Space by explicit `space_id`. This changes visible Arc state. |
| `arc_select_tab` | Selects an Arc tab by explicit `tab_id`. This changes visible Arc state. |
| `arc_open_url` | Navigates a specific tab when `tab_id` is provided, or the active tab when `tab_id` is intentionally omitted. Prefer passing `tab_id` for predictable behavior. |
| `arc_reload_tabs` | Reloads one or more tabs by explicit `tab_ids`. |
| `arc_execute_javascript` | Executes JavaScript in an explicit tab. Disabled by default and available only when `ARC_MCP_ENABLE_JAVASCRIPT=1` is set. |

### Delete Tools

| Tool | Description |
| --- | --- |
| `arc_close_tabs` | Closes one or more tabs by explicit `tab_ids`. This is marked destructive. Use `dry_run: true` to preview the close response without closing tabs. |

<details>
<summary>Example workflows</summary>

Find duplicate tabs:

```json
{
  "analyses": ["duplicates"],
  "limit": 25,
  "include_evidence": true
}
```

Search tabs in a Space:

```json
{
  "query": "docs",
  "space_id": "space-id",
  "limit": 20
}
```

Create a tab in a known Space:

```json
{
  "space_id": "space-id",
  "url": "https://example.com",
  "select": true
}
```

Preview closing tabs:

```json
{
  "tab_ids": ["tab-id-1", "tab-id-2"],
  "dry_run": true
}
```

Close tabs after review:

```json
{
  "tab_ids": ["tab-id-1", "tab-id-2"],
  "dry_run": false
}
```

</details>

## Quick Start

Requirements:

- macOS
- Arc installed at `/Applications/Arc.app`
- Python 3.12 or newer
- `uv` / `uvx`
- A local stdio MCP client
- macOS Automation permission for the MCP client or terminal app when using
  mutating tools

Run the server directly:

```bash
uvx arc-browser-mcp
```

Run a local prerequisite check:

```bash
uvx arc-browser-mcp doctor
```

## Installation

<details>
<summary>Codex</summary>

```bash
codex mcp add arc-browser -- uvx arc-browser-mcp
```

</details>

<details>
<summary>Claude Code</summary>

```bash
claude mcp add --transport stdio --scope user arc-browser -- uvx arc-browser-mcp
```

</details>

<details>
<summary>opencode</summary>

Add this server entry to `~/.config/opencode/opencode.json` or a project
`opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "arc_browser": {
      "type": "local",
      "command": ["uvx", "arc-browser-mcp"],
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

</details>

<details>
<summary>Claude Desktop</summary>

For local development, add this to the Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "arc-browser": {
      "command": "uvx",
      "args": ["arc-browser-mcp"],
      "env": {}
    }
  }
}
```

For end users, prefer a Claude Desktop Extension / DXT package. This repository
includes MCPB packaging metadata for that workflow:

```bash
npm install -g @anthropic-ai/mcpb
mcpb pack
```

</details>

<details>
<summary>Local development install</summary>

From a checkout of this repository:

```bash
uv sync
uv run arc-browser-mcp doctor
uv run arc-browser-mcp serve
```

For a local MCP client config that runs from source, use:

```bash
uv run arc-browser-mcp
```

or:

```bash
uv run arc-browser-mcp serve
```

</details>

<details>
<summary>Install command helper</summary>

You can also print client-specific install guidance:

```bash
uvx arc-browser-mcp install --client codex
uvx arc-browser-mcp install --client claude-code
uvx arc-browser-mcp install --client opencode
uvx arc-browser-mcp install --client claude-desktop
```

</details>

## Safety And Privacy

- The server is local and communicates with MCP clients over stdio.
- Read tools may return private browser data to the connected MCP client,
  including titles, URLs, domains, Space names, folder names, profile IDs,
  history metadata, and local source paths.
- The server does not send browser data anywhere by itself. Your MCP client and
  its model provider receive whatever data they request through tool calls.
- Mutating tools change visible Arc state, including focused Spaces, selected
  tabs, newly created tabs, opened URLs, reloaded tabs, and closed tabs.
- Destructive actions require explicit tab IDs. `arc_close_tabs` also supports
  `dry_run`.
- `arc_create_tab` requires an explicit Space ID and verifies the created tab
  before returning its ID.
- `arc_execute_javascript` is disabled unless `ARC_MCP_ENABLE_JAVASCRIPT=1` is
  set in the MCP server environment.
- The server does not directly edit Arc sidebar, archive, command ranking, or
  history files. Changes go through Arc automation instead.

<details>
<summary>CLI reference</summary>

```bash
arc-browser-mcp serve
arc-browser-mcp doctor
arc-browser-mcp smoke --read-only
arc-browser-mcp install --client codex
arc-browser-mcp install --client claude-code
arc-browser-mcp install --client opencode
arc-browser-mcp install --client claude-desktop
```

`serve` runs the MCP server over stdio. Running `arc-browser-mcp` without a
subcommand also starts the server.

`doctor` checks macOS, `osascript`, `uvx`, and the expected Arc app location.

`smoke --read-only` runs live read-only checks against local Arc state. It does
not call mutating tools.

`install --client ...` prints MCP configuration guidance for a supported client.

</details>

<details>
<summary>Troubleshooting</summary>

### Arc Is Not Running

Mutating tools and live Arc reads through AppleScript/JXA require Arc to be
running. Open Arc and retry the tool call.

### macOS Automation Permission Is Denied

If Arc actions fail with an automation or permissions error, open macOS System
Settings and check the Automation and Privacy & Security permissions for the
terminal or MCP client that launches this server.

### `uvx` Is Missing

Install `uv` from the official installer or package manager you use, then rerun:

```bash
arc-browser-mcp doctor
```

### JavaScript Execution Is Disabled

`arc_execute_javascript` intentionally fails unless enabled:

```bash
ARC_MCP_ENABLE_JAVASCRIPT=1 uvx arc-browser-mcp
```

Only enable this in a client configuration where you are comfortable allowing
explicit JavaScript execution in browser tabs.

### Multiple Arc Windows

Some tools accept `window_id`. Use `arc_get_overview`, `arc_query_tabs`, or a
client-visible tab record to identify Space and tab IDs first. When creating a
tab and more than one Arc window is open, pass `window_id` when you need the tab
created in a specific window.

</details>

<details>
<summary>Development and packaging</summary>

Set up the local environment:

```bash
uv sync
```

Run tests and linting:

```bash
uv run pytest
uv run ruff check .
```

Run local checks against Arc:

```bash
uv run arc-browser-mcp doctor
uv run arc-browser-mcp smoke --read-only
```

Run the server from source:

```bash
uv run arc-browser-mcp serve
```

Manual live verification steps are documented in
[`docs/manual-verification.md`](docs/manual-verification.md).

The repository includes `manifest.json` and `.mcpbignore` for MCPB packaging:

```bash
npm install -g @anthropic-ai/mcpb
mcpb pack
```

</details>

## License

MIT. See [`LICENSE`](LICENSE).
