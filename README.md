# Andra

**English** | [中文](README.zh-CN.md)

**Andra** = hot-reloadable **LSPosed hook runtime** + **desktop reverse MCP**.

Write `hooks.json` on the desktop, deploy over adb, inject into a host app — no
rebuild of an Xposed module for every small change.

```text
load_apk → search / decompile → write_plugin → deploy_plugin → verify_plugin
```

| Layer | Path | What it is |
|-------|------|------------|
| **Runtime** | `runtime/` | Android app `dev.andra.runtime` (LSPosed module + status UI) |
| **MCP / CLI** | `mcp/` | Python MCP server + CLI (DEX search, jadx, deploy, verify) |
| **Docs** | `docs/` | Pipeline and anti-hang rules |

## Requirements

- Rooted Android device with **LSPosed** (or compatible)
- `adb` on the desktop
- Optional: [jadx](https://github.com/skylot/jadx), [uv](https://github.com/astral-sh/uv), JDK 17+

## Quick start

### 1. Build & install runtime

```bash
# From repo root (needs Android SDK; set sdk.dir in local.properties)
./gradlew :runtime:assembleRelease
adb install -r runtime/build/outputs/apk/release/runtime-release.apk
```

In LSPosed:

1. Enable **Andra**
2. Scope = **host app only** (not system framework)
3. Force-stop the host app after scope changes

### 2. Run desktop MCP / CLI

```bash
cd mcp
uv sync
uv run python -m andra.cli --help
uv run python -m andra.server   # MCP stdio
```

### 3. Demo plugin

Example package lives at `mcp/workspace/plugins/DemoHook/` (hooks `Activity.onResume`
in `com.android.settings`).

```bash
cd mcp
uv run python -m andra.cli deploy DemoHook --package com.android.settings
uv run python -m andra.cli verify DemoHook --package com.android.settings --wait 6
```

## Plugin layout

```text
plugin.json     # id, targetPackage, version, …
hooks.json      # what the runtime actually executes
main.bsh        # documentation / future BeanShell (not required today)
INSTALL.md      # human notes
.enabled        # touch this file on device to enable
```

**Phone path (preferred):**

```text
/sdcard/Android/media/<hostPackage>/Andra/plugins/<Name>/
```

Logs:

```text
/sdcard/Android/media/<hostPackage>/Andra/logs/andra.log
```

## hooks.json

```json
[
  {
    "class_name": "com.example.Vip",
    "method_name": "isVip",
    "kind": "replace",
    "return_value": "true",
    "note": "gate"
  }
]
```

| `kind` | Behavior |
|--------|----------|
| `log` | Log args / return |
| `before` | Run before; optional `return_value` short-circuits |
| `after` | Run after; optional override `return_value` |
| `replace` | Set result from `return_value` |

Optional note token: `log_result`.

## MCP client snippet

```toml
[mcp_servers.andra]
command = "uv"
args = ["run", "--directory", "/path/to/andra/mcp", "python", "-m", "andra.server"]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 600
```

## Wireless adb

Prefer the real Wi-Fi IPv4. Do **not** use VPN fake addresses such as `172.19.*`.

```bash
uv run python -m andra.cli connect 192.168.x.x:<PORT>
```

Env: `ANDRA_ADB`, `ANDRA_WIFI_HOST`, `ANDRA_WORKSPACE`, `ADB_BIN`, `JADX_BIN`.

## Project layout

```text
andra/
  runtime/          # LSPosed module (Gradle :runtime)
  mcp/              # Python package andra-mcp
  docs/workflow.md  # Full reverse → deploy pipeline
  LICENSE           # Apache-2.0
  README.md         # English
  README.zh-CN.md   # 中文
```

## Scope of this open-source tree

- **Included:** generic hook engine, status UI, MCP reverse tools, DemoHook
- **Not included:** third-party APKs, decompiled dumps, app-specific automation
  modules from private experiments

Use on apps you own or are authorized to instrument.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
