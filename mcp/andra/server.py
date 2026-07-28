#!/usr/bin/env python3
"""Andra desktop MCP server — reverse-engineering tools on the host machine."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .workspace import get_workspace


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _err(e: Exception) -> str:
    return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)


def build_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise SystemExit(
            "mcp package not installed. Run:\n"
            "  cd tools/andra-mcp && uv sync\n"
            f"Original error: {e}"
        ) from e

    mcp = FastMCP("andra")
    ws = get_workspace()

    @mcp.tool()
    def status() -> str:
        """Show current workspace status: loaded APK, jadx cache, stats."""
        try:
            return _ok(ws.status())
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def load_apk(path: str, decompile: bool = False, threads: int = 4) -> str:
        """Load an APK/DEX for analysis. Optionally run full jadx decompile (slow, cached).

        Args:
            path: Absolute or relative path to .apk / .dex / dir of dex files.
            decompile: If true, run jadx on the whole package now.
            threads: jadx thread count.
        """
        try:
            return _ok(ws.load_apk(path, decompile=decompile, threads=threads))
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def decompile_all(threads: int = 4, force: bool = False) -> str:
        """Decompile the loaded APK with jadx into the workspace cache.

        Args:
            threads: jadx -j value.
            force: Re-decompile even if cache exists.
        """
        try:
            return _ok(ws.decompile_all(threads=threads, force=force))
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def search_classes(keyword: str, limit: int = 20, offset: int = 0) -> str:
        """Fuzzy search class names (contains). Best first entry for unknown names."""
        try:
            idx = ws.ensure_index()
            hits = idx.search_classes(keyword, limit=limit, offset=offset)
            return _ok({"count": len(hits), "offset": offset, "classes": hits})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def find_class(
        class_name_pattern: str | None = None,
        pkg: list[str] | None = None,
        super_class: str | None = None,
        interfaces: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Find classes by name/package/superclass/interfaces filters."""
        try:
            idx = ws.ensure_index()
            hits = idx.find_class(
                class_name_pattern=class_name_pattern,
                pkg=pkg,
                super_class=super_class,
                interfaces=interfaces,
                limit=limit,
                offset=offset,
            )
            return _ok({"count": len(hits), "classes": hits})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def find_method(
        method_name_pattern: str | None = None,
        in_class: str | None = None,
        param_count: int | None = None,
        return_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Find methods (fast-path guarded).

        Prefer ``in_class`` (exact method name when set). Without ``in_class``,
        ``method_name_pattern`` is required (len>=2). Full-APK dumps are refused
        so mega apps (multi-dex) cannot hang the MCP session.
        Prefer ``search_strings`` / ``find_usage`` / ``find_caller`` first.
        """
        try:
            if not in_class and (
                not method_name_pattern or len(str(method_name_pattern).strip()) < 2
            ):
                return _err(
                    ValueError(
                        "find_method without in_class needs method_name_pattern "
                        "(len>=2). Prefer search_strings → find_usage → "
                        "find_caller, or pass in_class."
                    )
                )
            lim = max(1, min(int(limit or 20), 100))
            idx = ws.ensure_index()
            hits = idx.find_method(
                method_name_pattern=method_name_pattern,
                in_class=in_class,
                param_count=param_count,
                return_type=return_type,
                limit=lim,
                offset=offset,
            )
            return _ok(
                {
                    "count": len(hits),
                    "methods": hits,
                    "hint": (
                        "Prefer in_class when known. Empty? try search_strings / "
                        "find_usage first."
                    ),
                }
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def find_field(
        field_name_pattern: str | None = None,
        in_class: str | None = None,
        field_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Find fields by name / declaring class / type."""
        try:
            idx = ws.ensure_index()
            hits = idx.find_field(
                field_name_pattern=field_name_pattern,
                in_class=in_class,
                field_type=field_type,
                limit=limit,
                offset=offset,
            )
            return _ok({"count": len(hits), "fields": hits})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def search_strings(keyword: str, limit: int = 20, offset: int = 0) -> str:
        """Search DEX string pool for constants containing keyword."""
        try:
            idx = ws.ensure_index()
            hits = idx.search_strings(keyword, limit=limit, offset=offset)
            return _ok({"count": len(hits), "strings": hits})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def class_hierarchy(class_name: str, depth: int = 3) -> str:
        """Show superclass chain and subclass sample for a class."""
        try:
            idx = ws.ensure_index()
            return _ok(idx.class_hierarchy(class_name, depth=depth))
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def decompile_class(
        class_name: str,
        from_line: int | None = None,
        to_line: int | None = None,
    ) -> str:
        """Decompile a class to Java via jadx cache (line-numbered). Heavy — narrow candidates first."""
        try:
            return ws.decompile_class(class_name, from_line=from_line, to_line=to_line)
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def decompile_method(class_name: str, method_name: str) -> str:
        """Decompile a single method from jadx output (line-numbered excerpt)."""
        try:
            return ws.decompile_method(class_name, method_name)
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def list_decompiled(keyword: str = "", limit: int = 50) -> str:
        """List classes already present in the jadx output cache."""
        try:
            return _ok({"classes": ws.list_decompiled_classes(keyword, limit=limit)})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def read_manifest() -> str:
        """Decode and return AndroidManifest.xml (via jadx resources)."""
        try:
            return _ok(ws.read_manifest_summary())
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def apk_stats() -> str:
        """Return class/string/method counts for the loaded APK."""
        try:
            return _ok(ws.ensure_index().stats())
        except Exception as e:
            return _err(e)

    # ----- Andra plugin deliverable (primary output) -----

    @mcp.tool()
    def write_plugin(
        name: str,
        hooks: str = "[]",
        target_package: str = "",
        desc: str = "",
        author: str = "andra-mcp",
        version: str = "1.0.0",
        extra_bsh: str = "",
        analysis_notes: str = "",
        main_bsh: str = "",
        make_zip: bool = True,
    ) -> str:
        """Write an Andra plugin package (THE expected deliverable).

        Creates workspace/plugins/<name>/{plugin.json, hooks.json, main.bsh, INSTALL.md}.
        Deploy path:
          /sdcard/Android/data/dev.andra.runtime/files/plugins/<name>/

        Args:
            name: Plugin display/folder name.
            hooks: JSON array of hook specs, each:
              {"class_name":"a.b.C","method_name":"foo","kind":"log|before|after|replace",
               "return_value":"true","note":"..."}
              kind=log → log args+result; replace/before may use return_value as BSH expr.
            target_package: Host app package name (for INSTALL path).
            desc: Plugin description for plugin.json.
            author: Author field.
            version: Version string.
            extra_bsh: Extra BeanShell appended after generated hooks.
            analysis_notes: Free text put as // comments at top of main.bsh.
            main_java: If non-empty, use this as full main.bsh body (ignores hooks codegen).
            make_zip: Also write <name>.zip next to the folder.
        """
        try:
            return _ok(
                ws.write_plugin(
                    name=name,
                    hooks=hooks,
                    target_package=target_package,
                    desc=desc,
                    author=author,
                    version=version,
                    extra_bsh=extra_bsh,
                    analysis_notes=analysis_notes,
                    main_bsh=main_bsh or None,
                    make_zip=make_zip,
                )
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def list_plugins() -> str:
        """List plugin packages already written under workspace/plugins/."""
        try:
            return _ok({"plugins_dir": str(ws.plugins_dir), "plugins": ws.list_written_plugins()})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def read_plugin(name: str) -> str:
        """Read plugin.json + main.bsh of a generated plugin by folder or display name."""
        try:
            return _ok(ws.read_plugin(name))
        except Exception as e:
            return _err(e)

    # ----- Xref / call graph -----

    @mcp.tool()
    def find_caller(
        class_name: str,
        method_name: str,
        limit: int = 30,
        offset: int = 0,
    ) -> str:
        """Find callers of class_name.method_name by scanning DEX invoke opcodes (first scan caches)."""
        try:
            hits = ws.ensure_index().find_caller(
                class_name, method_name, limit=limit, offset=offset
            )
            return _ok({"count": len(hits), "callers": hits})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def find_usage(
        keyword: str,
        search_in: str = "both",
        limit: int = 30,
        offset: int = 0,
    ) -> str:
        """Find string constant users and/or method-name matches.

        search_in: string | method | class | both
        """
        try:
            hits = ws.ensure_index().find_usage(
                keyword, search_in=search_in, limit=limit, offset=offset
            )
            return _ok({"count": len(hits), "hits": hits})
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def find_class_usage(
        class_name: str,
        limit: int = 40,
        offset: int = 0,
    ) -> str:
        """Approximate class usage: invokes to its methods, fields of this type, subclasses."""
        try:
            hits = ws.ensure_index().find_class_usage(
                class_name, limit=limit, offset=offset
            )
            return _ok({"count": len(hits), "hits": hits})
        except Exception as e:
            return _err(e)

    # ----- Device deploy / verify -----

    @mcp.tool()
    def device_status(serial: str = "") -> str:
        """List adb devices (USB + wireless), remembered HOST:PORT, frida host status."""
        try:
            return _ok(ws.runtime_status(serial=serial or None))
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def adb_connect(address: str, prefer_host: str = "") -> str:
        """Connect wireless adb: address=HOST:PORT (e.g. 192.168.x.x:37123).

        Rejects/rewrites VPN hosts like 172.19.0.1 using prefer_host or ANDRA_WIFI_HOST.
        Remembers endpoint for later deploy/logcat/reconnect.
        """
        try:
            return _ok(ws.adb_connect(address, prefer_host=prefer_host or None))
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def adb_pair(address: str, pairing_code: str, prefer_host: str = "") -> str:
        """Android 11+ wireless debugging pair: HOST:PAIR_PORT + 6-digit code.

        After success, call adb_connect with the *connection* port (different from pair port).
        """
        try:
            return _ok(
                ws.adb_pair(address, pairing_code, prefer_host=prefer_host or None)
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def adb_reconnect(address: str = "", prefer_host: str = "") -> str:
        """Reconnect last remembered wireless endpoint, or address=HOST:PORT if given."""
        try:
            return _ok(
                ws.adb_reconnect(address or None, prefer_host=prefer_host or None)
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def adb_disconnect(address: str = "") -> str:
        """Disconnect wireless endpoint (or all if address empty)."""
        try:
            return _ok(ws.adb_disconnect(address or None))
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def deploy_plugin(
        name: str,
        target_package: str = "",
        serial: str = "",
        force_stop: bool = True,
        start_activity: str = "",
        prefer_host: str = "",
    ) -> str:
        """adb push plugin over USB or wireless. serial may be HOST:PORT.

        Primary path (host-readable under scoped storage):
          /sdcard/Android/media/<targetPackage>/Andra/plugins/<name>/
        Also mirrors to /sdcard/Andra/plugins/<name>/.
        Do NOT rely on Android/data/dev.andra.runtime (host cannot read it).
        LSPosed scope: enable Andra and check the *host app* only — NOT 系统框架.
        Auto-reconnects remembered wireless if nothing online.
        """
        try:
            return _ok(
                ws.deploy_plugin_to_device(
                    name,
                    target_package=target_package or None,
                    serial=serial or None,
                    force_stop=force_stop,
                    start_activity=start_activity or None,
                    prefer_host=prefer_host or None,
                )
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def capture_logcat(
        tag: str = "Andra",
        package: str = "",
        grep: str = "",
        timeout_sec: float = 5,
        clear: bool = False,
        serial: str = "",
        max_lines: int = 200,
        prefer_host: str = "",
        dump_only: bool = True,
    ) -> str:
        """Capture Andra logs without hanging (logcat ring buffer).

        Prefer ``read_andra_log`` for Chinese I/E file logs written by the runtime.
        Default dump_only=True uses ``logcat -d`` (instant). timeout hard-capped
        at 12s. If empty, falls back to LSPosed modules log on root.
        """
        try:
            from .device import logcat as _logcat

            return _ok(
                _logcat(
                    serial=serial or None,
                    tag=tag or None,
                    package=package or None,
                    grep=grep or None,
                    clear=clear,
                    timeout_sec=timeout_sec,
                    max_lines=max_lines,
                    prefer_host=prefer_host or None,
                    dump_only=dump_only,
                )
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def read_andra_log(
        host_package: str,
        plugin: str = "",
        level: str = "IE",
        max_lines: int = 80,
        serial: str = "",
        prefer_host: str = "",
        mirror: bool = True,
    ) -> str:
        """Read Andra **file** logs (Chinese Info/Error), newest first.

        Runtime writes to:
          /sdcard/Android/media/<host>/Andra/logs/andra.log
        Uses su cat (works with mode 660). Mirrors to Andra private dir for UI.
        level: I | E | IE | all. Prefer this over capture_logcat for verify.
        """
        try:
            return _ok(
                ws.read_andra_log_on_device(
                    host_package,
                    plugin=plugin or "",
                    level=level or "IE",
                    max_lines=max_lines,
                    serial=serial or None,
                    prefer_host=prefer_host or None,
                    mirror=mirror,
                )
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def verify_plugin(
        name: str,
        host_package: str = "",
        serial: str = "",
        prefer_host: str = "",
        start_activity: str = "",
        wait_sec: float = 6,
        expect_keywords: str = "",
    ) -> str:
        """After deploy: force-stop host → start → wait → read_andra_log I/E.

        expect_keywords: optional ``a|b|c`` or JSON list; default matches Chinese
        sign/hook outcomes (今日已签, 签到完成, …).
        Returns ok=true when log lines match at least one keyword.
        """
        try:
            return _ok(
                ws.verify_plugin_on_device(
                    name,
                    host_package=host_package or None,
                    serial=serial or None,
                    prefer_host=prefer_host or None,
                    start_activity=start_activity or None,
                    wait_sec=wait_sec,
                    expect_keywords=expect_keywords or None,
                )
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def write_frida_script(
        name: str,
        hooks: str = "[]",
        from_plugin: str = "",
    ) -> str:
        """Generate a Frida JS hook script from hooks JSON or an existing plugin manifest."""
        try:
            return _ok(
                ws.write_frida(
                    name,
                    hooks=hooks if hooks and hooks != "[]" else None,
                    from_plugin=from_plugin or None,
                )
            )
        except Exception as e:
            return _err(e)

    @mcp.tool()
    def frida_run(
        package: str,
        script_name: str,
        serial: str = "",
        spawn: bool = True,
        timeout_sec: float = 12,
    ) -> str:
        """Optionally attach Frida for a short window (needs frida-tools + device frida-server).

        script_name: name used in write_frida_script (file workspace/frida/<name>.js)
        """
        try:
            from .frida_tools import frida_attach as _attach

            script = ws.root / "frida" / f"{script_name}.js"
            if not script.exists():
                script = Path(script_name)
            return _ok(
                _attach(
                    package,
                    script,
                    serial=serial or None,
                    spawn=spawn,
                    timeout_sec=timeout_sec,
                )
            )
        except Exception as e:
            return _err(e)

    return mcp


def main() -> None:
    mcp = build_mcp()
    # stdio transport for MCP clients
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
