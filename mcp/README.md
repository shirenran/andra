# Andra MCP (desktop)

Desktop reverse workflow for AI agents (MCP): DEX search + jadx, deliverable is a phone-loadable **Andra** plugin.

**中文逐步教程（含「某吧去广告」示意）：** [../docs/mcp-usage.zh-CN.md](../docs/mcp-usage.zh-CN.md)

Does **not** depend on any third-party mobile reverse app.

**Preferred phone path** (host-readable under scoped storage):

```text
/sdcard/Android/media/<hostPackage>/Andra/plugins/<Name>/
```

## Deliverable

```text
workspace/plugins/<Name>/
  plugin.json
  hooks.json
  main.bsh
  INSTALL.md
  manifest.json
```

## MCP client config

Example for any MCP host (Grok / Claude / Cursor / …):

```toml
[mcp_servers.andra]
command = "uv"
args = ["run", "--directory", "mcp", "python", "-m", "andra.server"]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 600
```

Or from this package root after `cd mcp && uv sync`:

```bash
uv run python -m andra.server
```

## Pipeline

```text
load_apk → search_strings / find_usage / find_caller
  → find_method(in_class=...) / decompile_*
  → write_plugin (hooks.json is what runs)
  → deploy_plugin   # host media + public + andra private
  → verify_plugin   # start host + read Chinese I/E file logs
  → read_andra_log  # re-check anytime
```

```bash
uv run python -m andra.cli deploy DemoHook --package com.example.host
uv run python -m andra.cli verify DemoHook --package com.example.host
uv run python -m andra.cli read-log --host com.example.host --plugin DemoHook
```

## Wireless ADB

```bash
# Prefer real Wi-Fi IP; never 172.19.*
uv run python -m andra.cli connect 192.168.x.x:<PORT>
```

Env: `ANDRA_ADB`, `ANDRA_WIFI_HOST`, `ANDRA_WORKSPACE`, `ADB_BIN`, `JADX_BIN`.

## Runtime

Phone package: `dev.andra.runtime` (LSPosed module + status UI).  
Log tag: `Andra` (also appears in LSPosed modules log via `XposedBridge.log`).

**LSPosed scope:** enable Andra and check the **host app only**.  
**Do not require 系统框架** for normal app plugins.

**Plugin path:**

```text
/sdcard/Android/media/<hostPackage>/Andra/plugins/<Name>/
```

## Anti-hang

- `find_method` without `in_class` requires a name pattern (len≥2); full dumps refused.
- Prefer **`read_andra_log`** / **`verify_plugin`** over live `capture_logcat`.
- `capture_logcat` defaults to dump + ≤12s; empty → lspd modules log fallback.
- Prefer `search_strings` / `find_usage` before heavy scans on mega APKs.

## Logs

Runtime writes Chinese Info/Error to:

```text
/sdcard/Android/media/<host>/Andra/logs/andra.log
```

UI + MCP mirror into Andra private files when needed (host media is often mode 660).
