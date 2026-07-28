"""Workspace state: loaded APK, jadx output cache, session helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .dex import ApkIndex, DexError
from .device import (
    DeviceError,
    adb_connect,
    adb_disconnect,
    adb_pair,
    deploy_plugin,
    device_status as adb_device_status,
    ensure_device,
    list_devices,
    logcat,
    pick_serial,
    reconnect_wireless,
)
from .frida_tools import (
    FridaError,
    frida_attach,
    frida_available,
    write_frida_script,
)
from .plugin import (
    HookSpec,
    PluginMeta,
    list_plugins,
    parse_hooks_json,
    write_plugin_package,
    zip_plugin,
)


DEFAULT_WORKSPACE = Path(
    os.environ.get(
        "ANDRA_WORKSPACE",
        str(Path(__file__).resolve().parents[1] / "workspace"),
    )
)


class Workspace:
    def __init__(self, root: Path | None = None):
        self.root = (root or DEFAULT_WORKSPACE).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.plugins_dir = self.root / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self._index: ApkIndex | None = None
        self._state: dict[str, Any] = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    @property
    def apk_path(self) -> str | None:
        return self._state.get("apk_path")

    @property
    def jadx_dir(self) -> Path | None:
        p = self._state.get("jadx_dir")
        return Path(p) if p else None

    def ensure_index(self) -> ApkIndex:
        if self._index is not None:
            return self._index
        apk = self.apk_path
        if not apk:
            raise DexError("No APK loaded. Call load_apk(path) first.")
        self._index = ApkIndex.load(apk)
        return self._index

    def load_apk(self, path: str, decompile: bool = False, threads: int = 4) -> dict:
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            raise DexError(f"APK not found: {path_obj}")

        digest = hashlib.sha1(path_obj.read_bytes()[: min(1024 * 1024, path_obj.stat().st_size)]).hexdigest()[:12]
        cache_key = f"{path_obj.stem}-{path_obj.stat().st_size}-{digest}"
        work = self.root / cache_key
        work.mkdir(parents=True, exist_ok=True)

        self._state = {
            "apk_path": str(path_obj),
            "cache_key": cache_key,
            "work_dir": str(work),
            "jadx_dir": self._state.get("jadx_dir") if self._state.get("cache_key") == cache_key else None,
        }
        self._index = ApkIndex.load(path_obj)
        stats = self._index.stats()

        result: dict[str, Any] = {"ok": True, "stats": stats, "work_dir": str(work)}
        if decompile:
            result["decompile"] = self.decompile_all(threads=threads)
        self._save_state()
        return result

    def which_jadx(self) -> str:
        env = os.environ.get("JADX_BIN")
        if env and Path(env).exists():
            return env
        found = shutil.which("jadx")
        if found:
            return found
        raise DexError("jadx not found on PATH. Install jadx or set JADX_BIN.")

    def decompile_all(self, threads: int = 4, force: bool = False) -> dict:
        idx = self.ensure_index()
        work = Path(self._state["work_dir"])
        out = work / "jadx"
        marker = out / ".done"
        if out.exists() and marker.exists() and not force:
            self._state["jadx_dir"] = str(out)
            self._save_state()
            return {"ok": True, "jadx_dir": str(out), "cached": True}

        if out.exists() and force:
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)

        jadx = self.which_jadx()
        cmd = [
            jadx,
            "-d",
            str(out),
            "-j",
            str(max(1, threads)),
            "--show-bad-code",
            "--no-res",
            idx.source,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        marker.write_text("ok\n", encoding="utf-8")
        self._state["jadx_dir"] = str(out)
        self._save_state()
        return {
            "ok": proc.returncode == 0,
            "jadx_dir": str(out),
            "cached": False,
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-2000:],
            "stdout_tail": (proc.stdout or "")[-1000:],
        }

    def _class_to_java_path(self, class_name: str) -> Path | None:
        jadx_dir = self.jadx_dir
        if not jadx_dir or not jadx_dir.exists():
            return None
        # sources may be under sources/ or directly
        rel = class_name.replace(".", "/") + ".java"
        candidates = [
            jadx_dir / "sources" / rel,
            jadx_dir / rel,
        ]
        # inner classes: Foo$Bar -> Foo.java
        if "$" in class_name:
            outer = class_name.split("$", 1)[0].replace(".", "/") + ".java"
            candidates.extend([jadx_dir / "sources" / outer, jadx_dir / outer])
        for c in candidates:
            if c.exists():
                return c
        return None

    def decompile_class(self, class_name: str, from_line: int | None = None, to_line: int | None = None) -> str:
        path = self._class_to_java_path(class_name)
        if path is None:
            # try single-class jadx
            text = self._jadx_single_class(class_name)
            if text is None:
                return (
                    f"// Class not decompiled yet: {class_name}\n"
                    f"// Tip: call decompile_all() first, or check class name spelling."
                )
        else:
            text = path.read_text(encoding="utf-8", errors="replace")

        lines = text.splitlines()
        if from_line is not None or to_line is not None:
            start = max(0, (from_line or 1) - 1)
            end = to_line if to_line is not None else len(lines)
            lines = lines[start:end]
            numbered = [f"{start + i + 1}|{line}" for i, line in enumerate(lines)]
        else:
            numbered = [f"{i + 1}|{line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)

    def decompile_method(self, class_name: str, method_name: str) -> str:
        full = self.decompile_class(class_name)
        if full.startswith("// Class not decompiled"):
            return full
        lines = full.splitlines()
        # crude method extraction by name
        start = None
        for i, line in enumerate(lines):
            # strip "N|"
            body = line.split("|", 1)[-1]
            if method_name + "(" in body or method_name + " (" in body:
                # skip fields that happen to contain name
                if any(k in body for k in ("(", "void ", "int ", "boolean ", "public ", "private ", "protected ", "static ")):
                    start = i
                    break
        if start is None:
            return f"// Method not found in decompiled output: {class_name}.{method_name}"

        # find opening brace then match braces
        depth = 0
        started = False
        chunk: list[str] = []
        for line in lines[start:]:
            body = line.split("|", 1)[-1]
            chunk.append(line)
            for ch in body:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
            if started and depth <= 0:
                break
        return "\n".join(chunk)

    def _jadx_single_class(self, class_name: str) -> str | None:
        idx = self.ensure_index()
        jadx = self.which_jadx()
        work = Path(self._state.get("work_dir") or self.root / "tmp")
        work.mkdir(parents=True, exist_ok=True)
        out_file = work / "single" / f"{class_name.replace('.', '_')}.java"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            jadx,
            "--single-class",
            class_name,
            "--single-class-output",
            str(out_file),
            "--show-bad-code",
            "-j",
            "1",
            idx.source,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if out_file.exists():
            return out_file.read_text(encoding="utf-8", errors="replace")
        # jadx sometimes writes a dir
        if out_file.is_dir():
            java_files = list(out_file.rglob("*.java"))
            if java_files:
                return java_files[0].read_text(encoding="utf-8", errors="replace")
        # fallback: search any java produced nearby
        produced = list((work / "single").rglob("*.java"))
        for p in produced:
            if class_name.rsplit(".", 1)[-1] in p.name:
                return p.read_text(encoding="utf-8", errors="replace")
        _ = proc
        return None

    def list_decompiled_classes(self, keyword: str = "", limit: int = 50) -> list[str]:
        jadx_dir = self.jadx_dir
        if not jadx_dir:
            return []
        root = jadx_dir / "sources" if (jadx_dir / "sources").exists() else jadx_dir
        hits: list[str] = []
        for p in root.rglob("*.java"):
            rel = p.relative_to(root).with_suffix("")
            name = str(rel).replace("/", ".")
            if keyword.lower() in name.lower():
                hits.append(name)
            if len(hits) >= limit:
                break
        return hits

    def read_manifest_summary(self) -> dict:
        """Best-effort manifest via jadx resources or aapt-less zip strings."""
        apk = self.apk_path
        if not apk:
            raise DexError("No APK loaded")
        # Prefer already-decompiled resources
        for base in filter(None, [self.jadx_dir, Path(self._state.get("work_dir", "")) / "jadx"]):
            if not base:
                continue
            for cand in [
                base / "resources" / "AndroidManifest.xml",
                base / "AndroidManifest.xml",
            ]:
                if cand.exists():
                    text = cand.read_text(encoding="utf-8", errors="replace")
                    return {"path": str(cand), "text": text[:50000]}

        # Decompile resources only
        jadx = self.which_jadx()
        work = Path(self._state["work_dir"])
        out = work / "manifest_only"
        if not (out / "resources" / "AndroidManifest.xml").exists():
            out.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [jadx, "-d", str(out), "-s", "-j", "2", apk],
                capture_output=True,
                text=True,
            )
        manifest = out / "resources" / "AndroidManifest.xml"
        if manifest.exists():
            return {"path": str(manifest), "text": manifest.read_text(encoding="utf-8", errors="replace")[:50000]}
        return {"path": None, "text": "// Failed to decode AndroidManifest.xml"}

    def status(self) -> dict:
        return {
            "workspace": str(self.root),
            "plugins_dir": str(self.plugins_dir),
            "apk_path": self.apk_path,
            "jadx_dir": str(self.jadx_dir) if self.jadx_dir else None,
            "loaded": self._index is not None or bool(self.apk_path),
            "stats": self.ensure_index().stats() if self.apk_path else None,
            "plugins": list_plugins(self.plugins_dir),
        }

    def write_plugin(
        self,
        name: str,
        hooks: str | list | dict | None = None,
        *,
        author: str = "andra-mcp",
        version: str = "1.0.0",
        desc: str = "",
        target_package: str = "",
        extra_bsh: str = "",
        analysis_notes: str = "",
        main_bsh: str | None = None,
        make_zip: bool = True,
        overwrite: bool = True,
    ) -> dict:
        """
        Primary deliverable: an Andra plugin directory.

        Layout:
          workspace/plugins/<name>/
            plugin.json / hooks.json / main.bsh / INSTALL.md / manifest.json
          workspace/plugins/<name>.zip   (optional)
        """
        meta = PluginMeta(
            name=name,
            author=author,
            version=version,
            desc=desc or name,
            target_package=target_package,
        )
        hook_specs: list[HookSpec] = parse_hooks_json(hooks)
        manifest = write_plugin_package(
            self.plugins_dir,
            meta,
            hooks=hook_specs,
            extra_bsh=extra_bsh,
            analysis_notes=analysis_notes,
            main_bsh=main_bsh,
            overwrite=overwrite,
        )
        if make_zip:
            zpath = zip_plugin(Path(manifest["path"]))
            manifest["zip"] = str(zpath)
        return {"ok": True, **manifest}

    def read_plugin(self, name: str) -> dict:
        d = self.plugins_dir / name
        if not d.is_dir():
            # try match by info name
            for item in list_plugins(self.plugins_dir):
                if item["name"] == name or item["folder"] == name:
                    d = Path(item["path"])
                    break
        if not d.is_dir():
            raise DexError(f"Plugin not found: {name} (under {self.plugins_dir})")
        main = d / "main.bsh"
        info = d / "plugin.json"
        hooks = d / "hooks.json"
        return {
            "path": str(d),
            "plugin_json": info.read_text(encoding="utf-8", errors="replace") if info.exists() else "",
            "hooks_json": hooks.read_text(encoding="utf-8", errors="replace") if hooks.exists() else "",
            "main_bsh": main.read_text(encoding="utf-8", errors="replace") if main.exists() else "",
            "files": [p.name for p in d.iterdir() if p.is_file()],
        }

    def list_written_plugins(self) -> list[dict]:
        return list_plugins(self.plugins_dir)

    def resolve_plugin_dir(self, name: str) -> Path:
        d = self.plugins_dir / name
        if d.is_dir() and ((d / "main.bsh").exists() or (d / "plugin.json").exists()):
            return d
        for item in list_plugins(self.plugins_dir):
            if item["name"] == name or item["folder"] == name:
                return Path(item["path"])
        raise DexError(f"Plugin not found: {name}")

    def deploy_plugin_to_device(
        self,
        name: str,
        target_package: str | None = None,
        *,
        serial: str | None = None,
        force_stop: bool = True,
        start_activity: str | None = None,
        prefer_host: str | None = None,
    ) -> dict:
        plugin_dir = self.resolve_plugin_dir(name)
        pkg = target_package
        if not pkg:
            # try manifest.json
            man = plugin_dir / "manifest.json"
            if man.exists():
                try:
                    pkg = json.loads(man.read_text(encoding="utf-8")).get("meta", {}).get(
                        "target_package"
                    )
                except Exception:
                    pkg = None
        if not pkg:
            # plugin.json
            try:
                meta = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
                pkg = meta.get("targetPackage") or pkg
            except Exception:
                pass
        if not pkg:
            raise DeviceError(
                "target_package required (pass it or set when write_plugin)"
            )
        return deploy_plugin(
            plugin_dir,
            pkg,
            serial=serial,
            force_stop=force_stop,
            start_activity=start_activity,
            prefer_host=prefer_host,
        )

    def read_andra_log_on_device(
        self,
        host_package: str,
        *,
        plugin: str = "",
        level: str = "IE",
        max_lines: int = 80,
        serial: str | None = None,
        prefer_host: str | None = None,
        mirror: bool = True,
    ) -> dict:
        from .device import read_andra_log as _read

        return _read(
            host_package,
            plugin=plugin,
            level=level,
            max_lines=max_lines,
            serial=serial,
            prefer_host=prefer_host,
            mirror=mirror,
            newest_first=True,
        )

    def verify_plugin_on_device(
        self,
        name: str,
        host_package: str | None = None,
        *,
        serial: str | None = None,
        prefer_host: str | None = None,
        start_activity: str | None = None,
        wait_sec: float = 6.0,
        expect_keywords: str | list[str] | None = None,
    ) -> dict:
        from .device import verify_plugin as _verify

        plugin_dir = self.resolve_plugin_dir(name)
        pkg = host_package
        if not pkg:
            try:
                meta = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
                pkg = meta.get("targetPackage") or pkg
            except Exception:
                pass
        if not pkg:
            raise DeviceError("host_package / targetPackage required")

        keys: list[str] | None
        if isinstance(expect_keywords, str) and expect_keywords.strip():
            raw = expect_keywords.strip()
            if raw.startswith("["):
                try:
                    keys = list(json.loads(raw))
                except Exception:
                    keys = [k.strip() for k in raw.split("|") if k.strip()]
            else:
                keys = [k.strip() for k in raw.split("|") if k.strip()]
        elif isinstance(expect_keywords, list):
            keys = [str(k) for k in expect_keywords]
        else:
            keys = None

        return _verify(
            plugin_dir.name,
            pkg,
            serial=serial,
            prefer_host=prefer_host,
            start_activity=start_activity,
            wait_sec=wait_sec,
            expect_keywords=keys,
        )

    def adb_connect(self, address: str, prefer_host: str | None = None) -> dict:
        return adb_connect(address, prefer_host=prefer_host, remember=True)

    def adb_disconnect(self, address: str | None = None) -> dict:
        return adb_disconnect(address)

    def adb_pair(self, address: str, pairing_code: str, prefer_host: str | None = None) -> dict:
        return adb_pair(address, pairing_code, prefer_host=prefer_host)

    def adb_reconnect(self, address: str | None = None, prefer_host: str | None = None) -> dict:
        return reconnect_wireless(address, prefer_host=prefer_host)

    def write_frida(
        self,
        name: str,
        hooks: str | list | dict | None = None,
        *,
        from_plugin: str | None = None,
    ) -> dict:
        """Write Frida JS next to plugins or from an existing plugin's hooks."""
        if from_plugin and not hooks:
            man = self.resolve_plugin_dir(from_plugin) / "manifest.json"
            if man.exists():
                hooks = json.loads(man.read_text(encoding="utf-8")).get("hooks") or []
            else:
                raise DexError(f"No manifest hooks in plugin {from_plugin}")
        if not hooks:
            raise DexError("hooks required (JSON) or from_plugin=")
        out = self.root / "frida" / f"{name}.js"
        return write_frida_script(out, hooks, title=name)

    def runtime_status(self, serial: str | None = None) -> dict:
        status = adb_device_status(serial)
        status["frida"] = frida_available()
        return status


# process-wide singleton
_WS: Workspace | None = None


def get_workspace() -> Workspace:
    global _WS
    if _WS is None:
        _WS = Workspace()
    return _WS
