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

## What is it for?

Classic Xposed workflow: edit Java → build APK → install → reload scope, for every tiny hook trial.  
**Andra workflow: edit JSON → push to phone → force-stop host → done.**

| Goal | You write | Result |
|------|-----------|--------|
| See if a method runs / what args it gets | `kind: log` | Chinese I/E lines under host media logs |
| Temporarily force a gate (your own app) | `kind: replace` + `return_value` | Method returns the value you set |
| Observe return value only | `kind: after` + `log_result` | No behavior change, just visibility |
| AI-assisted reverse | MCP: `load_apk` → strings → `write_plugin` → `deploy` | APK → deployable plugin in one loop |

Built for debugging **apps you own or are authorized to instrument**.  
This repo does **not** ship crack plugins for third-party commercial apps.

## Usage examples

### Example 1: Demo in five minutes (Settings)

Goal: open **Settings** and see `Activity.onResume` in Andra logs.

Shipped plugin: [`mcp/workspace/plugins/DemoHook/`](mcp/workspace/plugins/DemoHook/)

```json
// hooks.json (already in the repo)
[
  {
    "class_name": "android.app.Activity",
    "method_name": "onResume",
    "kind": "log",
    "note": "smoke"
  }
]
```

```bash
# 0. Phone: install Andra, enable in LSPosed, scope = Settings (com.android.settings)
# 1. Deploy from desktop
cd mcp && uv sync
uv run python -m andra.cli deploy DemoHook --package com.android.settings

# 2. Force-stop / open Settings, then read logs
uv run python -m andra.cli verify DemoHook --package com.android.settings --wait 6
# or
uv run python -m andra.cli read-log --host com.android.settings --plugin DemoHook --level IE
```

You should see something like:

```text
07-29 12:00:01.234  I  [DemoHook]  Hook 就绪 1/1
07-29 12:00:02.100  D  [DemoHook]  调用 android.app.Activity.onResume 参数=...
```

(UI / `read-log` prefer I/E; full detail stays in the `andra.log` file.)

### Example 2: Force a method to return true (your app)

Suppose your package is `com.mycompany.demo` and you have:

```java
// com.mycompany.demo.feature.FeatureFlags
public boolean isPremiumUnlocked() { return false; }
```

For local debugging you want it always unlocked, without rebuilding the app:

**1. Create** `mcp/workspace/plugins/UnlockPremium/`

`plugin.json`:

```json
{
  "id": "UnlockPremium",
  "name": "UnlockPremium",
  "version": "1.0.0",
  "desc": "local debug: force premium flag",
  "targetPackage": "com.mycompany.demo",
  "hooksFile": "hooks.json"
}
```

`hooks.json`:

```json
[
  {
    "class_name": "com.mycompany.demo.feature.FeatureFlags",
    "method_name": "isPremiumUnlocked",
    "kind": "replace",
    "return_value": "true",
    "note": "local debug only"
  }
]
```

**2. LSPosed scope:** check `com.mycompany.demo` only (not system framework).

**3. Deploy:**

```bash
cd mcp
uv run python -m andra.cli deploy UnlockPremium --package com.mycompany.demo
adb shell am force-stop com.mycompany.demo
# open the app UI that calls isPremiumUnlocked
uv run python -m andra.cli read-log --host com.mycompany.demo --plugin UnlockPremium --level IE
```

Change the return value? Edit `hooks.json` and `deploy` again — **no rebuild of Andra or the host APK**.

### Example 3: APK → find method → plugin (MCP / AI)

When you only have an APK and do not know the class name yet:

```text
load_apk(path=./app-debug.apk)
  → search_strings("isPremium")
  → find_usage / find_caller
  → decompile_method(class=..., method=...)
  → write_plugin(name=UnlockPremium, hooks=[...])
  → deploy_plugin + verify_plugin
```

Same end state as Example 2: a `hooks.json` on device. Full tool map: [docs/workflow.md](docs/workflow.md).

### vs writing a full Xposed module

| | Hand-written Xposed module | Andra plugin |
|--|----------------------------|--------------|
| Tweak one hook | Java → build → install module | Edit `hooks.json` → deploy |
| Multiple hosts | Often hard-coded in source | One `targetPackage` per plugin |
| AI agents | Must emit a whole module project | Emit a JSON hook list |
| Feedback | Mostly logcat | Host-media Chinese I/E file + `verify` |

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
