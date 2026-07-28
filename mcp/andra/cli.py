#!/usr/bin/env python3
"""CLI wrapper for Andra desktop tools (no MCP required)."""

from __future__ import annotations

import argparse
import json
import sys

from .workspace import get_workspace


def _print(data) -> None:
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="andra", description="Desktop Andra reverse tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s = sub.add_parser("load")
    s.add_argument("path")
    s.add_argument("--decompile", action="store_true")
    s.add_argument("-j", type=int, default=4)

    s = sub.add_parser("decompile-all")
    s.add_argument("-j", type=int, default=4)
    s.add_argument("--force", action="store_true")

    s = sub.add_parser("search-classes")
    s.add_argument("keyword")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("search-strings")
    s.add_argument("keyword")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("find-method")
    s.add_argument("--name")
    s.add_argument("--class")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("find-field")
    s.add_argument("--name")
    s.add_argument("--class")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("decompile-class")
    s.add_argument("class_name")

    s = sub.add_parser("decompile-method")
    s.add_argument("class_name")
    s.add_argument("method_name")

    s = sub.add_parser("manifest")
    s = sub.add_parser("hierarchy")
    s.add_argument("class_name")

    s = sub.add_parser("write-plugin", help="Write Andra plugin (plugin.json + main.bsh)")
    s.add_argument("name")
    s.add_argument("--package", default="", help="Target host package name")
    s.add_argument("--desc", default="")
    s.add_argument("--author", default="andra-mcp")
    s.add_argument("--hooks", default="[]", help="JSON array of hook specs")
    s.add_argument("--notes", default="", help="Analysis notes (// comments)")
    s.add_argument("--main-java", default="", help="Path to full main.bsh to embed")
    s.add_argument("--no-zip", action="store_true")

    s = sub.add_parser("list-plugins")
    s = sub.add_parser("read-plugin")
    s.add_argument("name")

    s = sub.add_parser("find-caller")
    s.add_argument("class_name")
    s.add_argument("method_name")
    s.add_argument("--limit", type=int, default=30)

    s = sub.add_parser("find-usage")
    s.add_argument("keyword")
    s.add_argument("--in", dest="search_in", default="both")
    s.add_argument("--limit", type=int, default=30)

    s = sub.add_parser("find-class-usage")
    s.add_argument("class_name")
    s.add_argument("--limit", type=int, default=40)

    s = sub.add_parser("devices", help="List USB/wireless adb + remembered endpoint")
    s.add_argument("--serial", default="")

    s = sub.add_parser("connect", help="Wireless adb connect HOST:PORT")
    s.add_argument("address", help="e.g. 192.168.x.x:37123 (not 172.19.0.1)")
    s.add_argument("--prefer-host", default="", help="Rewrite bad VPN IP to this Wi-Fi host")

    s = sub.add_parser("pair", help="Wireless adb pair HOST:PAIR_PORT CODE")
    s.add_argument("address")
    s.add_argument("code")
    s.add_argument("--prefer-host", default="")

    s = sub.add_parser("reconnect", help="Reconnect last wireless or given HOST:PORT")
    s.add_argument("address", nargs="?", default="")
    s.add_argument("--prefer-host", default="")

    s = sub.add_parser("disconnect", help="Disconnect wireless endpoint(s)")
    s.add_argument("address", nargs="?", default="")

    s = sub.add_parser("deploy")
    s.add_argument("name", help="Plugin folder name")
    s.add_argument("--package", default="", help="Host package (or from manifest)")
    s.add_argument("--serial", default="", help="HOST:PORT or USB serial")
    s.add_argument("--prefer-host", default="")
    s.add_argument("--no-stop", action="store_true")
    s.add_argument("--start", default="", help="am start component, e.g. pkg/.MainActivity")

    s = sub.add_parser("logcat")
    s.add_argument("--tag", default="Andra")
    s.add_argument("--package", default="")
    s.add_argument("--grep", default="")
    s.add_argument("--timeout", type=float, default=8)
    s.add_argument("--serial", default="", help="HOST:PORT or USB serial")
    s.add_argument("--prefer-host", default="")

    s = sub.add_parser("read-log", help="Read Andra file logs (Chinese I/E)")
    s.add_argument("--host", required=True, help="Host package, e.g. com.example.host")
    s.add_argument("--plugin", default="", help="Plugin name filter")
    s.add_argument("--level", default="IE", help="I | E | IE | all")
    s.add_argument("--lines", type=int, default=80)
    s.add_argument("--serial", default="")
    s.add_argument("--prefer-host", default="")
    s.add_argument("--no-mirror", action="store_true")

    s = sub.add_parser("verify", help="Force-stop host, start, read I/E logs")
    s.add_argument("name", help="Plugin folder name")
    s.add_argument("--package", default="", help="Host package (or from plugin.json)")
    s.add_argument("--serial", default="")
    s.add_argument("--prefer-host", default="")
    s.add_argument("--start", default="", help="am start component")
    s.add_argument("--wait", type=float, default=6)
    s.add_argument("--expect", default="", help="keywords a|b|c")

    s = sub.add_parser("write-frida")
    s.add_argument("name")
    s.add_argument("--hooks", default="[]")
    s.add_argument("--from-plugin", default="")

    s = sub.add_parser("frida-run")
    s.add_argument("package")
    s.add_argument("script_name")
    s.add_argument("--serial", default="")
    s.add_argument("--attach", action="store_true", help="Attach instead of spawn")
    s.add_argument("--timeout", type=float, default=12)

    args = p.parse_args(argv)
    ws = get_workspace()

    try:
        if args.cmd == "status":
            _print(ws.status())
        elif args.cmd == "load":
            _print(ws.load_apk(args.path, decompile=args.decompile, threads=args.j))
        elif args.cmd == "decompile-all":
            _print(ws.decompile_all(threads=args.j, force=args.force))
        elif args.cmd == "search-classes":
            _print(ws.ensure_index().search_classes(args.keyword, limit=args.limit))
        elif args.cmd == "search-strings":
            _print(ws.ensure_index().search_strings(args.keyword, limit=args.limit))
        elif args.cmd == "find-method":
            _print(
                ws.ensure_index().find_method(
                    method_name_pattern=args.name,
                    in_class=getattr(args, "class"),
                    limit=args.limit,
                )
            )
        elif args.cmd == "find-field":
            _print(
                ws.ensure_index().find_field(
                    field_name_pattern=args.name,
                    in_class=getattr(args, "class"),
                    limit=args.limit,
                )
            )
        elif args.cmd == "decompile-class":
            _print(ws.decompile_class(args.class_name))
        elif args.cmd == "decompile-method":
            _print(ws.decompile_method(args.class_name, args.method_name))
        elif args.cmd == "manifest":
            _print(ws.read_manifest_summary())
        elif args.cmd == "hierarchy":
            _print(ws.ensure_index().class_hierarchy(args.class_name))
        elif args.cmd == "write-plugin":
            main_java = None
            if args.main_java:
                from pathlib import Path

                main_java = Path(args.main_java).read_text(encoding="utf-8")
            _print(
                ws.write_plugin(
                    name=args.name,
                    hooks=args.hooks,
                    target_package=args.package,
                    desc=args.desc,
                    author=args.author,
                    analysis_notes=args.notes,
                    main_java=main_java,
                    make_zip=not args.no_zip,
                )
            )
        elif args.cmd == "list-plugins":
            _print({"plugins": ws.list_written_plugins(), "dir": str(ws.plugins_dir)})
        elif args.cmd == "read-plugin":
            _print(ws.read_plugin(args.name))
        elif args.cmd == "find-caller":
            _print(
                ws.ensure_index().find_caller(
                    args.class_name, args.method_name, limit=args.limit
                )
            )
        elif args.cmd == "find-usage":
            _print(
                ws.ensure_index().find_usage(
                    args.keyword, search_in=args.search_in, limit=args.limit
                )
            )
        elif args.cmd == "find-class-usage":
            _print(ws.ensure_index().find_class_usage(args.class_name, limit=args.limit))
        elif args.cmd == "devices":
            _print(ws.runtime_status(serial=args.serial or None))
        elif args.cmd == "connect":
            _print(ws.adb_connect(args.address, prefer_host=args.prefer_host or None))
        elif args.cmd == "pair":
            _print(
                ws.adb_pair(
                    args.address, args.code, prefer_host=args.prefer_host or None
                )
            )
        elif args.cmd == "reconnect":
            _print(
                ws.adb_reconnect(
                    args.address or None, prefer_host=args.prefer_host or None
                )
            )
        elif args.cmd == "disconnect":
            _print(ws.adb_disconnect(args.address or None))
        elif args.cmd == "deploy":
            _print(
                ws.deploy_plugin_to_device(
                    args.name,
                    target_package=args.package or None,
                    serial=args.serial or None,
                    force_stop=not args.no_stop,
                    start_activity=args.start or None,
                    prefer_host=args.prefer_host or None,
                )
            )
        elif args.cmd == "logcat":
            from .device import logcat as _logcat

            _print(
                _logcat(
                    serial=args.serial or None,
                    tag=args.tag or None,
                    package=args.package or None,
                    grep=args.grep or None,
                    timeout_sec=args.timeout,
                    prefer_host=args.prefer_host or None,
                )
            )
        elif args.cmd == "read-log":
            _print(
                ws.read_andra_log_on_device(
                    args.host,
                    plugin=args.plugin or "",
                    level=args.level or "IE",
                    max_lines=args.lines,
                    serial=args.serial or None,
                    prefer_host=args.prefer_host or None,
                    mirror=not args.no_mirror,
                )
            )
        elif args.cmd == "verify":
            _print(
                ws.verify_plugin_on_device(
                    args.name,
                    host_package=args.package or None,
                    serial=args.serial or None,
                    prefer_host=args.prefer_host or None,
                    start_activity=args.start or None,
                    wait_sec=args.wait,
                    expect_keywords=args.expect or None,
                )
            )
        elif args.cmd == "write-frida":
            _print(
                ws.write_frida(
                    args.name,
                    hooks=args.hooks if args.hooks != "[]" else None,
                    from_plugin=args.from_plugin or None,
                )
            )
        elif args.cmd == "frida-run":
            from .frida_tools import frida_attach

            script = ws.root / "frida" / f"{args.script_name}.js"
            _print(
                frida_attach(
                    args.package,
                    script,
                    serial=args.serial or None,
                    spawn=not args.attach,
                    timeout_sec=args.timeout,
                )
            )
        else:
            p.error(f"unknown command {args.cmd}")
            return 2
        return 0
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
