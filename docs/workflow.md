# Andra workflow — Reverse → Plugin → Deploy → Verify

## Required deliverable

```text
mcp/workspace/plugins/<Name>/{plugin.json, hooks.json, main.bsh, INSTALL.md}
```

Phone path (**host-owned media**, readable by host process under scoped storage):

```text
/sdcard/Android/media/<targetPackage>/Andra/plugins/<Name>/
```

Fallback mirror (optional):

```text
/sdcard/Andra/plugins/<Name>/
```

**Do not** deploy only to `/sdcard/Android/data/dev.andra.runtime/...` — host apps
cannot read another package's `Android/data` on modern Android.

Analysis without `write_plugin` = **incomplete**.  
Runtime currently executes **`hooks.json` only** (`main.bsh` is documentation /
future BSH). Always put real hooks in `hooks.json`.

## Full pipeline

```text
load_apk
  → search_strings / find_usage / search_classes   # cheap first
  → find_caller / find_method(in_class=...) / decompile_method
  → write_plugin   # hooks.json is what runs
  → deploy_plugin  # host media + public + andra private triple mirror
  → verify_plugin  # force-stop → start host → read Chinese I/E file logs
  → read_andra_log # anytime re-check (prefer over capture_logcat)
```

## Anti-hang rules (hard)

These bit us on large multi-dex APKs / empty logcat. Follow strictly:

1. **Never** call `find_method` without `in_class` **or** a meaningful
   `method_name_pattern` (len ≥ 2). Prefer `search_strings` → `find_usage` →
   `find_caller`. Tool now refuses unconstrained dumps.
2. **Never** live-follow `capture_logcat` waiting for lines that may never come.
   Default is dump (`logcat -d`) + hard timeout ≤ 12s. If empty, read
   `/data/adb/lspd/log/modules_*.log` via `su` (Andra uses `XposedBridge.log`).
3. Prefer **local jadx** on a known class over MCP `find_method` when the class
   name is already known from prior decompile cache.
4. After deploy: if no Andra lines, check path + LSPosed scope **before**
   waiting again.
5. Wireless adb: never use `172.19.*` (VPN fake).

## LSPosed scope (Andra)

| 勾选 | 需要？ |
|------|--------|
| 宿主 App（如 `com.example.host`） | **必须** |
| 系统框架 `system` | **不需要**（app hook 场景） |
| Andra 自身 `dev.andra.runtime` | 一般不需要 |

Andra 在**宿主进程**里 `handleLoadPackage` → 读 host media 下 plugins → hook。
不注入 `system_server` 也能工作。界面上若曾勾过系统框架可去掉，不影响 app 插件。

## Tool map

### Static

| Tool | Use |
|------|-----|
| `load_apk` | Index APK |
| `search_classes` / `search_strings` | Cheap locate |
| `find_method` | **Only** with `in_class` or short name pattern |
| `find_field` / `find_class` | Constrained |
| **`find_usage`** | String → which methods load it |
| **`find_caller`** | Who invokes `Class.method` |
| **`find_class_usage`** | Invokes / fields / subclasses |
| `decompile_class` / `decompile_method` | jadx (after ≤2 candidates) |
| `read_manifest` | Structure |

### Deliverable

| Tool | Use |
|------|-----|
| **`write_plugin`** | plugin.json + hooks.json + main.bsh |
| `list_plugins` / `read_plugin` | Inspect generated packages |

### Device

| Tool | Use |
|------|-----|
| **`adb_connect`** | `HOST:PORT`; rewrite `172.19.*` |
| `adb_pair` / `adb_reconnect` / `adb_disconnect` | Wireless lifecycle |
| `device_status` | USB/wireless + remembered endpoint |
| **`deploy_plugin`** | Triple mirror: host media + `/sdcard/Andra` + andra private |
| **`verify_plugin`** | force-stop → start host → `read_andra_log` I/E |
| **`read_andra_log`** | Chinese I/E file logs (su cat), newest first |
| `capture_logcat` | Dump-first ring buffer; prefer `read_andra_log` |
| `write_frida_script` / `frida_run` | Optional |

## hooks JSON (`write_plugin`)

```json
[
  {
    "class_name": "com.example.Vip",
    "method_name": "isVip",
    "kind": "replace",
    "return_value": "true",
    "note": "VIP gate"
  }
]
```

`kind`: `log` | `before` | `after` | `replace`

Optional `note` tokens understood by runtime `HookApplicator`:

| Token | Effect |
|-------|--------|
| `log_result` | Extra result logging |

App-specific automation should live in your own plugins, not in the core runtime.

## Verify (MCP, preferred)

```text
deploy_plugin(name=..., target_package=com.xxx)
verify_plugin(name=..., host_package=com.xxx, wait_sec=6)
read_andra_log(host_package=com.xxx, plugin=Name, level=IE)
```

CLI:

```bash
cd mcp
uv run python -m andra.cli deploy DemoHook --package com.android.settings
uv run python -m andra.cli verify DemoHook --package com.android.settings --wait 6
uv run python -m andra.cli read-log --host com.android.settings --plugin DemoHook --level IE
```

## Rules

1. Strings / usage first; callers before bulk decompile  
2. Always end with `write_plugin` path + deploy path  
3. If device online, offer `deploy_plugin`  
4. After deploy: call **`verify_plugin`** (or `read_andra_log`) — not infinite logcat follow  
5. Frida is optional — Andra plugin remains primary  
6. Never use VPN fake IP `172.19.*` for adb  
7. LSPosed scope = **host app only** for Andra app plugins  
8. User-facing log text is **Chinese I/E**; file path under host media `Andra/logs/`  

## Definition of done

- [ ] Plugin dir with `plugin.json` + `hooks.json` (+ main.bsh)
- [ ] Hooks match verified class/method; runtime path is host media
- [ ] Deployed (triple mirror) and user got paths
- [ ] `verify_plugin` or `read_andra_log` shows Chinese I/E (or clear empty_hints)
