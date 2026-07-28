# DemoHook — Andra plugin

Smoke-test plugin that logs `Activity.onResume` in the host app.

## Phone path

```text
/sdcard/Android/media/<targetPackage>/Andra/plugins/DemoHook/
```

Default target in `plugin.json`: `com.android.settings`.

## Deploy

```bash
# MCP
deploy_plugin(name="DemoHook", target_package="com.android.settings")

# CLI
uv run python -m andra.cli deploy DemoHook --package com.android.settings
```

## LSPosed

1. Enable **Andra** (`dev.andra.runtime`)
2. Scope: **host app only** (e.g. Settings) — not system framework
3. Force-stop and reopen the host app

## Verify

```bash
uv run python -m andra.cli verify DemoHook --package com.android.settings --wait 6
uv run python -m andra.cli read-log --host com.android.settings --plugin DemoHook --level IE
```
