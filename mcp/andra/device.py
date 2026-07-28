"""ADB helpers with first-class wireless debugging support."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .plugin import RUNTIME_PKG


class DeviceError(RuntimeError):
    pass


# VPN / CLASH virtual NIC ranges that look like wireless-debug endpoints but are unusable.
_BAD_WIRELESS_PREFIXES = (
    "172.19.",  # common FLClash/tun virtual
    "172.18.",
    "127.0.0.1",
    "0.0.0.0",
)

_HOSTPORT_RE = re.compile(
    r"^(?P<host>(?:\d{1,3}\.){3}\d{1,3}|[a-zA-Z0-9._-]+):(?P<port>\d{1,5})$"
)


def default_state_path() -> Path:
    env = os.environ.get("ANDRA_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve() / "adb_state.json"
    return Path(__file__).resolve().parents[1] / "workspace" / "adb_state.json"


def which_adb() -> str:
    env = os.environ.get("ADB_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("adb")
    if found:
        return found
    # Common Windows winget path (from project AGENT.md) — only if present
    win = Path(
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        )
    )
    if win.exists():
        for p in win.rglob("adb.exe"):
            return str(p)
    raise DeviceError("adb not found on PATH. Install platform-tools or set ADB_BIN.")


def adb_cmd(
    serial: str | None = None,
    *args: str,
    timeout: float = 60,
) -> subprocess.CompletedProcess:
    cmd = [which_adb()]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------- state (remember last wireless endpoint) ----------


def load_adb_state(path: Path | None = None) -> dict[str, Any]:
    p = path or default_state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_adb_state(data: dict[str, Any], path: Path | None = None) -> Path:
    p = path or default_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = load_adb_state(p)
    cur.update(data)
    cur["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def remember_serial(serial: str, *, path: Path | None = None) -> None:
    serial = serial.strip()
    meta: dict[str, Any] = {"last_serial": serial}
    if is_wireless_serial(serial):
        meta["last_wireless"] = serial
        host, port = serial.rsplit(":", 1)
        meta["last_host"] = host
        meta["last_port"] = port
    save_adb_state(meta, path)


# ---------- wireless helpers ----------


def is_wireless_serial(serial: str) -> bool:
    return bool(_HOSTPORT_RE.match(serial.strip()))


def is_bad_wireless_host(host: str) -> bool:
    h = host.strip()
    return any(h.startswith(p) for p in _BAD_WIRELESS_PREFIXES)


def normalize_endpoint(address: str, *, prefer_host: str | None = None) -> str:
    """
    Normalize host:port. If address is a bad VPN IP but port is real,
    rewrite host with prefer_host / last known Wi-Fi IP / ANDRA_WIFI_HOST.
    """
    address = address.strip().replace(" ", "")
    # allow adb-connect style without scheme
    if "://" in address:
        address = address.split("://", 1)[1]
    m = _HOSTPORT_RE.match(address)
    if not m:
        raise DeviceError(
            f"Invalid wireless endpoint '{address}'. Expected HOST:PORT "
            f"(e.g. 192.168.x.x:37123). Do not use 172.19.0.1."
        )
    host, port = m.group("host"), m.group("port")
    port_i = int(port)
    if not (1 <= port_i <= 65535):
        raise DeviceError(f"Invalid port: {port}")

    if is_bad_wireless_host(host):
        replacement = (
            prefer_host
            or os.environ.get("ANDRA_WIFI_HOST")
            or os.environ.get("ADB_WIFI_HOST")
            or load_adb_state().get("last_host")
        )
        if not replacement or is_bad_wireless_host(str(replacement)):
            raise DeviceError(
                f"Endpoint {host}:{port} looks like a VPN/tun address and cannot be used. "
                f"Replace host with real Wi-Fi IP (e.g. 192.168.x.x:{port}). "
                f"Set ANDRA_WIFI_HOST or pass prefer_host=."
            )
        host = str(replacement).strip()
    return f"{host}:{port}"


def list_devices() -> list[dict[str, str]]:
    proc = adb_cmd(None, "devices", "-l")
    if proc.returncode != 0:
        raise DeviceError(proc.stderr or proc.stdout or "adb devices failed")
    out: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        info: dict[str, str] = {
            "serial": serial,
            "state": state,
            "transport": "wireless" if is_wireless_serial(serial) else "usb",
        }
        if is_wireless_serial(serial):
            host = serial.rsplit(":", 1)[0]
            info["wireless_host_ok"] = "no" if is_bad_wireless_host(host) else "yes"
        for p in parts[2:]:
            if ":" in p:
                k, v = p.split(":", 1)
                info[k] = v
        out.append(info)
    return out


def wireless_devices(devices: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    devices = devices if devices is not None else list_devices()
    return [
        d
        for d in devices
        if d.get("transport") == "wireless"
        and d.get("state") == "device"
        and d.get("wireless_host_ok") != "no"
    ]


def adb_connect(
    address: str,
    *,
    prefer_host: str | None = None,
    remember: bool = True,
    timeout: float = 8,
) -> dict[str, Any]:
    """
    adb connect HOST:PORT for wireless debugging.
    Auto-rewrites 172.19.* to real Wi-Fi host when possible.
    """
    endpoint = normalize_endpoint(address, prefer_host=prefer_host)
    # disconnect stale same-host different-port? optional soft cleanup of offline
    try:
        proc = adb_cmd(None, "connect", endpoint, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "endpoint": endpoint,
            "message": f"adb connect timed out after {timeout}s",
            "returncode": -1,
            "hint": "Port may have changed after reboot; get a fresh HOST:PORT.",
        }
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    ok = proc.returncode == 0 and (
        "connected to" in text.lower()
        or "already connected" in text.lower()
    )
    # Some adb versions return 0 with "failed to connect"
    if "failed" in text.lower() or "cannot connect" in text.lower():
        ok = False

    result = {
        "ok": ok,
        "endpoint": endpoint,
        "message": text,
        "returncode": proc.returncode,
    }
    if ok and remember:
        remember_serial(endpoint)
        result["remembered"] = endpoint
    if not ok:
        result["hint"] = (
            "Wireless debug port changes after reboot. "
            "Get new port from phone Developer options / wireless-adb module clipboard. "
            "Never use 172.19.0.1 (VPN). Use real Wi-Fi IP + port."
        )
    return result


def adb_disconnect(address: str | None = None) -> dict[str, Any]:
    if address:
        endpoint = normalize_endpoint(address) if ":" in address else address
        proc = adb_cmd(None, "disconnect", endpoint, timeout=15)
    else:
        proc = adb_cmd(None, "disconnect", timeout=15)
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return {"ok": proc.returncode == 0, "message": text}


def adb_pair(
    address: str,
    pairing_code: str,
    *,
    prefer_host: str | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """
    adb pair HOST:PAIR_PORT CODE  (Android 11+ wireless debugging pairing).
    After pair, still need adb_connect to the *connection* port (different from pair port).
    """
    endpoint = normalize_endpoint(address, prefer_host=prefer_host)
    code = pairing_code.strip()
    if not code:
        raise DeviceError("pairing_code is required")
    proc = adb_cmd(None, "pair", endpoint, code, timeout=timeout)
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    ok = proc.returncode == 0 and "successfully" in text.lower()
    return {
        "ok": ok,
        "pair_endpoint": endpoint,
        "message": text,
        "next": "After pairing, adb_connect to the *wireless debugging connection port* (not pair port).",
    }


def reconnect_wireless(
    address: str | None = None,
    *,
    prefer_host: str | None = None,
    timeout: float = 8,
) -> dict[str, Any]:
    """
    Reconnect using explicit address, else last_wireless / last_serial from state,
    else env ANDRA_ADB / ANDROID_SERIAL if host:port.
    """
    state = load_adb_state()
    candidate = (
        address
        or os.environ.get("ANDRA_ADB")
        or os.environ.get("ADB_WIRELESS")
        or state.get("last_wireless")
        or (
            state.get("last_serial")
            if state.get("last_serial") and is_wireless_serial(str(state["last_serial"]))
            else None
        )
        or (
            os.environ.get("ANDROID_SERIAL")
            if os.environ.get("ANDROID_SERIAL")
            and is_wireless_serial(os.environ.get("ANDROID_SERIAL", ""))
            else None
        )
    )
    if not candidate:
        raise DeviceError(
            "No wireless endpoint to reconnect. "
            "Pass address=HOST:PORT or set ANDRA_ADB / connect once to remember."
        )
    # If only host remembered + new port not known, still need full endpoint
    if ":" not in str(candidate):
        raise DeviceError(
            f"Remembered host '{candidate}' has no port. "
            "Wireless port changes after reboot — pass full HOST:PORT."
        )
    # drop existing offline entries for same host
    host = str(candidate).rsplit(":", 1)[0]
    try:
        for d in list_devices():
            s = d.get("serial", "")
            if is_wireless_serial(s) and s.startswith(host + ":") and d.get("state") != "device":
                try:
                    adb_disconnect(s)
                except Exception:
                    pass
    except DeviceError:
        pass
    return adb_connect(str(candidate), prefer_host=prefer_host, remember=True, timeout=timeout)


def ensure_device(
    serial: str | None = None,
    *,
    auto_reconnect: bool = True,
    prefer_host: str | None = None,
) -> str:
    """
    Resolve a usable serial. For wireless:
      - accept HOST:PORT and connect if needed
      - prefer online wireless over USB when both exist and no serial given
      - auto-reconnect last wireless if nothing online
    """
    # Explicit serial
    if serial:
        serial = serial.strip()
        if is_wireless_serial(serial):
            endpoint = normalize_endpoint(serial, prefer_host=prefer_host)
            online = {
                d["serial"]
                for d in list_devices()
                if d.get("state") == "device"
            }
            if endpoint not in online:
                conn = adb_connect(endpoint, prefer_host=prefer_host, remember=True)
                if not conn["ok"]:
                    raise DeviceError(
                        f"Wireless connect failed: {conn.get('message')}. {conn.get('hint', '')}"
                    )
            else:
                remember_serial(endpoint)
            return endpoint
        # USB or other serial — just verify
        online = [d for d in list_devices() if d.get("serial") == serial]
        if not online or online[0].get("state") != "device":
            raise DeviceError(f"Device not online: {serial}")
        remember_serial(serial)
        return serial

    # Env overrides
    for key in ("ANDRA_ADB", "ANDROID_SERIAL", "ADB_SERIAL"):
        val = os.environ.get(key)
        if val:
            return ensure_device(val, auto_reconnect=False, prefer_host=prefer_host)

    devices = list_devices()
    ready = [d for d in devices if d.get("state") == "device"]
    # Prefer healthy wireless
    wifi = [
        d
        for d in ready
        if d.get("transport") == "wireless" and d.get("wireless_host_ok") != "no"
    ]
    if len(wifi) == 1:
        remember_serial(wifi[0]["serial"])
        return wifi[0]["serial"]
    if len(wifi) > 1:
        # prefer last_wireless if among them
        last = load_adb_state().get("last_wireless")
        for d in wifi:
            if d["serial"] == last:
                remember_serial(d["serial"])
                return d["serial"]
        serials = ", ".join(d["serial"] for d in wifi)
        raise DeviceError(
            f"Multiple wireless devices online ({serials}). Pass serial=HOST:PORT."
        )

    if len(ready) == 1:
        remember_serial(ready[0]["serial"])
        return ready[0]["serial"]
    if len(ready) > 1:
        serials = ", ".join(d["serial"] for d in ready)
        raise DeviceError(f"Multiple devices online ({serials}). Pass serial=.")

    # Nothing online — try reconnect last wireless (short timeout)
    if auto_reconnect:
        try:
            conn = reconnect_wireless(prefer_host=prefer_host, timeout=5)
            if conn.get("ok"):
                return conn["endpoint"]
            msg = conn.get("message") or "reconnect failed"
            raise DeviceError(msg)
        except DeviceError as e:
            raise DeviceError(
                f"No adb device online, wireless reconnect failed: {e}. "
                f"Run: adb_connect / andra.cli connect HOST:PORT "
                f"(skip 172.19.*; use real Wi-Fi IP)."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise DeviceError(
                f"Wireless reconnect timed out ({e.timeout}s). "
                f"Port likely stale — connect a fresh HOST:PORT."
            ) from e

    raise DeviceError("No adb device online. connect HOST:PORT first.")


def pick_serial(serial: str | None = None) -> str:
    """Backward-compatible alias used by deploy/logcat."""
    return ensure_device(serial, auto_reconnect=True)


def shell(serial: str | None, command: str, timeout: float = 60) -> str:
    serial = ensure_device(serial) if serial is None or serial == "" else ensure_device(serial)
    proc = adb_cmd(serial, "shell", command, timeout=timeout)
    if proc.returncode != 0:
        # wireless drop — one reconnect retry
        if is_wireless_serial(serial):
            try:
                reconnect_wireless(serial)
                proc = adb_cmd(serial, "shell", command, timeout=timeout)
            except Exception:
                pass
        if proc.returncode != 0:
            raise DeviceError(f"adb shell failed: {proc.stderr or proc.stdout}")
    return (proc.stdout or "").strip()


def push(serial: str | None, local: Path, remote: str, timeout: float = 120) -> None:
    serial = ensure_device(serial)
    local = local.expanduser().resolve()
    if not local.exists():
        raise DeviceError(f"Local path missing: {local}")
    proc = adb_cmd(serial, "push", str(local), remote, timeout=timeout)
    if proc.returncode != 0:
        if is_wireless_serial(serial):
            try:
                reconnect_wireless(serial)
                proc = adb_cmd(serial, "push", str(local), remote, timeout=timeout)
            except Exception:
                pass
        if proc.returncode != 0:
            raise DeviceError(f"adb push failed: {proc.stderr or proc.stdout}")


def device_status(serial: str | None = None, *, auto_reconnect: bool = False) -> dict[str, Any]:
    """
    Status snapshot. By default does NOT auto-reconnect (avoids long hang on dead ports).
    Pass serial= or auto_reconnect=True to try ensure_device.
    """
    state = load_adb_state()
    try:
        devices = list_devices()
    except DeviceError as e:
        devices = []
        list_err = str(e)
    else:
        list_err = None

    selected = None
    select_err = None
    # Prefer already-online device without reconnect
    ready = [d for d in devices if d.get("state") == "device"]
    wifi = wireless_devices(devices)
    if serial:
        try:
            selected = ensure_device(serial, auto_reconnect=True)
        except DeviceError as e:
            select_err = str(e)
    elif wifi:
        selected = wifi[0]["serial"]
    elif len(ready) == 1:
        selected = ready[0]["serial"]
    elif auto_reconnect:
        try:
            selected = ensure_device(None, auto_reconnect=True)
        except DeviceError as e:
            select_err = str(e)
    elif not ready:
        select_err = (
            "No device online. "
            "Use adb_connect HOST:PORT (or cli: connect). "
            f"Last wireless: {state.get('last_wireless') or 'none'}."
        )

    return {
        "adb_bin": which_adb(),
        "devices": devices,
        "wireless_online": wifi,
        "selected_serial": selected,
        "list_error": list_err,
        "select_error": select_err,
        "remembered": {
            "last_serial": state.get("last_serial"),
            "last_wireless": state.get("last_wireless"),
            "last_host": state.get("last_host"),
            "last_port": state.get("last_port"),
            "state_file": str(default_state_path()),
        },
        "env": {
            "ANDRA_ADB": os.environ.get("ANDRA_ADB"),
            "ANDRA_WIFI_HOST": os.environ.get("ANDRA_WIFI_HOST")
            or os.environ.get("ADB_WIFI_HOST"),
            "ANDROID_SERIAL": os.environ.get("ANDROID_SERIAL"),
        },
        "notes": [
            "Wireless debugging port changes after phone reboot.",
            "Never connect to 172.19.0.1 (FLClash/VPN virtual); use LAN Wi-Fi IP.",
            "Pairing port != connection port on Android 11+ wireless debugging.",
            "Set ANDRA_ADB=192.168.x.x:PORT or connect once to remember.",
        ],
    }


def deploy_plugin(
    plugin_dir: Path,
    target_package: str,
    *,
    serial: str | None = None,
    enable_plugin: bool = True,
    force_stop: bool = True,
    start_activity: str | None = None,
    prefer_host: str | None = None,
) -> dict[str, Any]:
    """
    Push Andra plugin folder to host-owned media path:
      /sdcard/Android/media/<targetPackage>/Andra/plugins/<folder>/
    (readable by the host process under scoped storage).
    Also mirrors to /sdcard/Andra/plugins and writes bridge/last_deploy.json.
    """
    from .plugin import PHONE_PLUGINS_ROOT, RUNTIME_PKG, phone_plugin_path

    plugin_dir = plugin_dir.expanduser().resolve()
    need = ("plugin.json", "main.bsh")
    if not all((plugin_dir / f).exists() for f in need):
        # allow hooks-only
        if not (plugin_dir / "plugin.json").exists() or not (
            (plugin_dir / "hooks.json").exists() or (plugin_dir / "main.bsh").exists()
        ):
            raise DeviceError(
                f"Not an Andra plugin dir (need plugin.json + main.bsh or hooks.json): {plugin_dir}"
            )
    if not target_package:
        # try plugin.json
        try:
            meta = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
            target_package = meta.get("targetPackage") or target_package
        except Exception:
            pass
    if not target_package:
        raise DeviceError("target_package is required for deploy")

    serial = ensure_device(serial, prefer_host=prefer_host)
    folder = plugin_dir.name
    remote_plugin = phone_plugin_path(folder, target_package).rstrip("/")
    public_plugin = phone_plugin_path(folder).rstrip("/")
    bridge_dir = f"/sdcard/Android/media/{target_package}/Andra/bridge"

    steps: list[dict[str, Any]] = []

    def step(name: str, fn):
        try:
            result = fn()
            steps.append({"step": name, "ok": True, "detail": result})
        except Exception as e:
            steps.append({"step": name, "ok": False, "error": str(e)})
            raise

    step("mkdir", lambda: shell(serial, f"mkdir -p '{remote_plugin}' '{public_plugin}' '{bridge_dir}'") or remote_plugin)

    for fname in ("plugin.json", "hooks.json", "main.bsh", "INSTALL.md", "manifest.json"):
        local = plugin_dir / fname
        if local.exists():
            step(
                f"push {fname}",
                lambda p=local, r=f"{remote_plugin}/{fname}": (push(serial, p, r), r)[1],
            )
            # mirror to public fallback path
            step(
                f"mirror {fname}",
                lambda p=local, r=f"{public_plugin}/{fname}": (push(serial, p, r), r)[1],
            )

    if enable_plugin:
        step(
            "enable + triple-mirror",
            lambda: (
                shell(
                    serial,
                    f"touch '{remote_plugin}/.enabled' '{public_plugin}/.enabled'",
                ),
                triple_mirror_plugin_files(
                    serial, folder, target_package, remote_plugin
                ),
            )[1],
        )

    # last_deploy for companion
    import tempfile
    from datetime import datetime, timezone

    last = {
        "plugin": folder,
        "hostPackage": target_package,
        "path": remote_plugin + "/",
        "deployedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cliVersion": "0.1.0",
        "runtimePackage": RUNTIME_PKG,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(last, tf, ensure_ascii=False, indent=2)
        tf.write("\n")
        tmp_path = Path(tf.name)
    try:
        step("mkdir bridge", lambda: shell(serial, f"mkdir -p '{bridge_dir}'") or bridge_dir)
        step(
            "push last_deploy.json",
            lambda: (
                push(serial, tmp_path, f"{bridge_dir}/last_deploy.json"),
                f"{bridge_dir}/last_deploy.json",
            )[1],
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    listing = shell(serial, f"ls -la '{remote_plugin}'")
    steps.append({"step": "verify", "ok": True, "detail": listing})

    if force_stop:
        step(
            "force-stop host",
            lambda: (shell(serial, f"am force-stop {target_package}"), "stopped")[1],
        )
        time.sleep(0.3)

    if start_activity:
        step(
            "start",
            lambda: (shell(serial, f"am start -n {start_activity}"), start_activity)[1],
        )

    return {
        "ok": all(s.get("ok") for s in steps),
        "serial": serial,
        "transport": "wireless" if is_wireless_serial(serial) else "usb",
        "target_package": target_package,
        "remote_plugin": remote_plugin + "/",
        "runtime_package": RUNTIME_PKG,
        "last_deploy": last,
        "steps": steps,
        "paths": {
            "host_media": remote_plugin + "/",
            "public": public_plugin + "/",
            "andra_private": f"/sdcard/Android/data/{RUNTIME_PKG}/files/plugins/{folder}/",
            "host_log": f"/sdcard/Android/media/{target_package}/Andra/logs/andra.log",
        },
        "hint": (
            "LSPosed: enable Andra, scope = HOST only "
            f"({target_package}), NOT 系统框架. "
            "Next: verify_plugin 或 read_andra_log；不要空等 capture_logcat。"
        ),
        "lsp_scope": {
            "module": RUNTIME_PKG,
            "must_check": [target_package],
            "must_not_require": ["system", "系统框架"],
            "reason": (
                "Andra injects into the host app process and reads host-owned "
                "media plugins; system_server scope is unnecessary for app hooks."
            ),
        },
        "next": [
            f'verify_plugin(name="{folder}", host_package="{target_package}")',
            f'read_andra_log(host_package="{target_package}", plugin="{folder}")',
        ],
    }



def logcat(
    *,
    serial: str | None = None,
    tag: str | None = "Andra",
    package: str | None = None,
    grep: str | None = None,
    clear: bool = True,
    timeout_sec: float = 5,
    max_lines: int = 200,
    prefer_host: str | None = None,
    dump_only: bool = True,
) -> dict[str, Any]:
    """Capture Andra / host logs without hanging.

    Default is **dump_only** (``logcat -d``): returns immediately from the ring
    buffer. Live follow mode is opt-in and hard-capped (never wait >12s).

    Empty result checklist is returned so callers do not re-wait forever.
    """
    serial = ensure_device(serial, prefer_host=prefer_host)
    # Hard cap: never let MCP sessions hang on empty live follow.
    timeout_sec = float(max(0.5, min(timeout_sec, 12.0)))
    max_lines = int(max(1, min(max_lines, 500)))

    if clear and not dump_only:
        adb_cmd(serial, "logcat", "-c", timeout=15)

    pid = None
    if package:
        try:
            pid = shell(serial, f"pidof -s {package}") or None
        except DeviceError:
            pid = None

    # Prefer dump mode: adb logcat -d exits when buffer is drained.
    cmd = [which_adb(), "-s", serial, "logcat", "-v", "time"]
    if dump_only:
        cmd += ["-d", "-t", str(max(50, min(max_lines * 3, 800)))]
    if pid:
        cmd += [f"--pid={pid}"]
    if tag:
        # Also include LSPosed bridge which often carries "Andra: ..." lines.
        if tag == "Andra":
            cmd += ["Andra:V", "LSPosed-Bridge:V", "LSPosedFramework:V", "*:S"]
        else:
            cmd += [f"{tag}:V", "*:S"]

    lines: list[str] = []
    note_parts: list[str] = []

    if dump_only:
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_sec + 5
            )
            raw = (proc.stdout or "").splitlines()
            for line in raw:
                if grep and grep not in line:
                    # allow multi-token OR via | in grep
                    if "|" in (grep or ""):
                        parts = [p for p in grep.split("|") if p]
                        if parts and not any(p in line for p in parts):
                            continue
                    else:
                        continue
                # Always keep Andra-tagged content even if tag filter missed
                if tag == "Andra" and "Andra" not in line:
                    if grep:
                        pass
                    elif "LSPosed" not in line:
                        continue
                lines.append(line)
                if len(lines) >= max_lines:
                    break
        except subprocess.TimeoutExpired:
            note_parts.append(f"dump timed out after {timeout_sec + 5}s")
    else:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        deadline = time.time() + timeout_sec
        try:
            assert proc.stdout is not None
            while time.time() < deadline and len(lines) < max_lines:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.05)
                    continue
                line = line.rstrip("\n")
                if grep and grep not in line:
                    continue
                lines.append(line)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()

    # Fallback: LSPosed modules log on rooted devices (Andra uses XposedBridge.log)
    lspd_lines: list[str] = []
    if len(lines) == 0:
        try:
            # Two-step: resolve newest modules log, then grep (avoids quote hell).
            newest = shell(
                serial,
                "su -c 'ls -t /data/adb/lspd/log/modules_*.log 2>/dev/null | head -1'",
                timeout=5,
            ).strip()
            if newest:
                out = shell(
                    serial,
                    f"su -c 'grep Andra: {newest} 2>/dev/null | tail -n 80'",
                    timeout=8,
                )
                for line in (out or "").splitlines():
                    if grep:
                        if "|" in grep:
                            parts = [p for p in grep.split("|") if p]
                            if parts and not any(p in line for p in parts):
                                continue
                        elif grep not in line:
                            continue
                    lspd_lines.append(line)
                    if len(lspd_lines) >= max_lines:
                        break
                if lspd_lines:
                    note_parts.append(f"filled from {newest}")
                    lines = lspd_lines
                else:
                    note_parts.append(f"lspd log empty for Andra: ({newest})")
            else:
                note_parts.append("no lspd modules_*.log found")
        except Exception as e:
            note_parts.append(f"lspd fallback skipped: {e}")

    empty_hints = []
    if not lines:
        empty_hints = [
            "1) LSPosed: enable dev.andra.runtime, scope = HOST APP only (not 系统框架)",
            "2) Plugin path must be /sdcard/Android/media/<host>/Andra/plugins/<Name>/ with .enabled",
            "3) Force-stop host and reopen so handleLoadPackage reloads plugins",
            "4) Prefer: adb shell su -c \"grep Andra: $(ls -t /data/adb/lspd/log/modules_*.log|head -1)|tail -30\"",
            "5) Do not live-follow empty logcat — use dump_only (default) or lspd modules log",
        ]

    return {
        "ok": True,
        "serial": serial,
        "transport": "wireless" if is_wireless_serial(serial) else "usb",
        "package": package,
        "pid": pid,
        "tag": tag,
        "grep": grep,
        "timeout_sec": timeout_sec,
        "dump_only": dump_only,
        "line_count": len(lines),
        "lines": lines,
        "empty_hints": empty_hints,
        "note": (
            "; ".join(note_parts)
            if note_parts
            else (
                "Empty log often means plugin not loaded — open host after deploy; "
                "scope host app (NOT system); path under Android/media/<host>/Andra/."
                if not lines
                else "ok"
            )
        ),
    }


# ---------------------------------------------------------------------------
# File logs + deploy verify (Andra runtime writes Chinese I/E to andra.log)
# ---------------------------------------------------------------------------


def andra_log_paths(host_package: str, plugin: str = "") -> list[str]:
    """Candidate andra.log paths on device (host media first)."""
    host = (host_package or "").strip()
    paths = []
    if host:
        paths.append(f"/sdcard/Android/media/{host}/Andra/logs/andra.log")
    paths.append("/sdcard/Andra/logs/andra.log")
    paths.append(f"/sdcard/Android/data/{RUNTIME_PKG}/files/logs/andra.log")
    if plugin:
        # per-plugin optional future path
        paths.append(f"/sdcard/Android/data/{RUNTIME_PKG}/files/logs/{plugin}.log")
    # dedupe
    out: list[str] = []
    for p in paths:
        if p not in out:
            out.append(p)
    return out


def _su(serial: str, cmd: str, timeout: float = 20) -> str:
    """Run su -c with proper quoting for KernelSU."""
    # json.dumps gives a safe single-argument string for -c
    quoted = json.dumps(cmd, ensure_ascii=False)
    return shell(serial, f"su -c {quoted}", timeout=timeout)


def _level_char(line: str) -> str:
    """Parse 'MM-dd HH:mm:ss.SSS  X  [plugin]  msg' → X, or ''."""
    s = line.strip()
    sp = s.find("  ")
    if sp < 8:
        return ""
    rest = s[sp:].strip()
    if not rest:
        return ""
    c = rest[0]
    if c in "IDEWVidewv" and len(rest) > 1 and rest[1] == " ":
        return c.upper()
    return ""


def _keep_ie_line(line: str, plugin: str = "", keyword: str = "") -> bool:
    s = line.strip()
    if not s:
        return False
    lv = _level_char(s)
    if lv == "D" or lv == "V":
        return False
    if lv and lv not in ("I", "E", "W"):
        return False
    # no level: only keep outcome-ish Chinese/English keywords
    if not lv:
        low = s.lower()
        if not any(
            k in low
            for k in (
                "今日已签",
                "失败",
                "成功",
                "跳过",
                "error",
                "fail",
                "done",
                "hook",
            )
        ):
            return False
    if plugin:
        if plugin not in s and f"[{plugin}]" not in s:
            # still allow host-wide I/E without plugin tag if no keyword
            if not keyword:
                return lv in ("I", "E", "W")
            return False
    if keyword and keyword not in s:
        return False
    return True


def mirror_andra_logs(
    host_package: str,
    *,
    serial: str | None = None,
    prefer_host: str | None = None,
) -> dict[str, Any]:
    """su-copy host media log → public + Andra private (UI-readable)."""
    serial = ensure_device(serial, prefer_host=prefer_host)
    host = (host_package or "").strip()
    if not host:
        raise DeviceError("host_package required")
    src = f"/sdcard/Android/media/{host}/Andra/logs/andra.log"
    priv = f"/sdcard/Android/data/{RUNTIME_PKG}/files/logs/andra.log"
    pub = "/sdcard/Andra/logs/andra.log"
    cmd = (
        f"mkdir -p '/sdcard/Android/data/{RUNTIME_PKG}/files/logs' '/sdcard/Andra/logs' "
        f"&& if [ -f '{src}' ]; then "
        f"cp -f '{src}' '{priv}' && cp -f '{src}' '{pub}' "
        f"&& chmod 666 '{priv}' '{pub}' 2>/dev/null; "
        f"echo OK size=$(wc -c < '{priv}'); "
        f"else echo NOFILE; fi"
    )
    try:
        out = _su(serial, cmd, timeout=15)
    except Exception as e:
        return {"ok": False, "serial": serial, "src": src, "error": str(e)}
    return {
        "ok": "OK" in out,
        "serial": serial,
        "src": src,
        "private": priv,
        "public": pub,
        "detail": out.strip(),
    }


def read_andra_log(
    host_package: str,
    *,
    plugin: str = "",
    level: str = "IE",
    max_lines: int = 80,
    serial: str | None = None,
    prefer_host: str | None = None,
    mirror: bool = True,
    newest_first: bool = True,
) -> dict[str, Any]:
    """
    Read Andra file logs (Chinese I/E) via su — does not hang on empty logcat.

    level: 'I' | 'E' | 'IE' | 'all'
    """
    serial = ensure_device(serial, prefer_host=prefer_host)
    host = (host_package or "").strip()
    if not host:
        raise DeviceError("host_package required for read_andra_log")
    max_lines = max(1, min(int(max_lines or 80), 500))
    level = (level or "IE").upper()

    mirror_info = None
    if mirror:
        mirror_info = mirror_andra_logs(host, serial=serial, prefer_host=prefer_host)

    paths = andra_log_paths(host, plugin)
    raw_chunks: list[tuple[str, str]] = []
    for path in paths:
        try:
            # su cat — works even when mode is 660
            body = _su(
                serial,
                f"if [ -f '{path}' ]; then wc -c < '{path}'; echo '---'; tail -n 400 '{path}'; else echo MISSING; fi",
                timeout=12,
            )
            if "MISSING" in body and "---" not in body:
                continue
            if "---" in body:
                _size, _, rest = body.partition("---")
                text = rest.lstrip("\n")
            else:
                text = body
            if text.strip():
                raw_chunks.append((path, text))
        except Exception:
            continue

    lines: list[str] = []
    sources_used: list[str] = []
    for path, text in raw_chunks:
        sources_used.append(path)
        for line in text.splitlines():
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if level != "ALL":
                lv = _level_char(line)
                if level == "I" and lv and lv != "I":
                    continue
                if level == "E" and lv and lv != "E":
                    continue
                if level == "IE" and not _keep_ie_line(line, plugin=plugin):
                    continue
            elif plugin and plugin not in line:
                continue
            lines.append(line)

    # de-dupe across mirrored sources (same line may appear 3x)
    seen: set[str] = set()
    dedup: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        dedup.append(line)

    # keep chronological tail then optionally reverse for newest-first
    if len(dedup) > max_lines:
        dedup = dedup[-max_lines:]
    if newest_first:
        dedup = list(reversed(dedup))

    empty_hints: list[str] = []
    if not dedup:
        empty_hints = [
            "1) 打开宿主 App 触发 hook（写日志在宿主进程）",
            f"2) LSPosed 启用 Andra，作用域勾选 {host}（不要勾系统框架）",
            f"3) 检查文件: adb shell su -c \"ls -la /sdcard/Android/media/{host}/Andra/logs/\"",
            "4) 确认插件 .enabled 且 deploy 到 media/<host>/Andra/plugins/",
            "5) 强制停止宿主后再开，重新 load 插件",
        ]

    return {
        "ok": True,
        "serial": serial,
        "host_package": host,
        "plugin": plugin or None,
        "level": level,
        "newest_first": newest_first,
        "line_count": len(dedup),
        "lines": dedup,
        "sources": sources_used,
        "paths_checked": paths,
        "mirror": mirror_info,
        "empty_hints": empty_hints,
        "note": (
            "ok"
            if dedup
            else "无 I/E 日志 — 先打开宿主再 read_andra_log；勿空等 logcat"
        ),
    }


def resolve_launcher_activity(serial: str, package: str) -> str | None:
    """Best-effort main launcher component for package."""
    try:
        out = shell(
            serial,
            f"cmd package resolve-activity --brief {package} 2>/dev/null | tail -n 1",
            timeout=10,
        )
        line = (out or "").strip().splitlines()[-1] if out else ""
        if line and "/" in line and not line.startswith("No "):
            return line.strip()
    except Exception:
        pass
    try:
        out = shell(
            serial,
            f"dumpsys package {package} 2>/dev/null | grep -A2 'android.intent.action.MAIN' | head -5",
            timeout=15,
        )
        for line in (out or "").splitlines():
            line = line.strip()
            if package in line and "/" in line:
                # e.g. 67f987c com.example.host/.MainActivity
                parts = line.split()
                for p in parts:
                    if p.startswith(package + "/"):
                        return p
    except Exception:
        pass
    return None


def verify_plugin(
    plugin_name: str,
    host_package: str,
    *,
    serial: str | None = None,
    prefer_host: str | None = None,
    start_activity: str | None = None,
    wait_sec: float = 6.0,
    expect_keywords: list[str] | None = None,
    max_lines: int = 40,
) -> dict[str, Any]:
    """
    Deploy-time verification:
      force-stop host → start → wait → read_andra_log (I/E) → report.
    """
    serial = ensure_device(serial, prefer_host=prefer_host)
    host = (host_package or "").strip()
    if not host:
        raise DeviceError("host_package required")
    wait_sec = float(max(1.0, min(wait_sec, 30.0)))
    steps: list[dict[str, Any]] = []

    def step(name: str, fn):
        try:
            detail = fn()
            steps.append({"step": name, "ok": True, "detail": detail})
            return detail
        except Exception as e:
            steps.append({"step": name, "ok": False, "error": str(e)})
            raise

    step("force-stop", lambda: (shell(serial, f"am force-stop {host}"), "stopped")[1])
    time.sleep(0.4)

    comp = (start_activity or "").strip() or resolve_launcher_activity(serial, host)
    if not comp:
        # monkey launcher fallback
        step(
            "start-monkey",
            lambda: (
                shell(
                    serial,
                    f"monkey -p {host} -c android.intent.category.LAUNCHER 1",
                    timeout=20,
                ),
                "monkey",
            )[1],
        )
    else:
        c = comp

        def _start():
            return (shell(serial, f"am start -n {c}", timeout=15), c)[1]

        step("start", _start)

    time.sleep(wait_sec)
    step("mirror-logs", lambda: mirror_andra_logs(host, serial=serial))

    log_result = read_andra_log(
        host,
        plugin=plugin_name or "",
        level="IE",
        max_lines=max_lines,
        serial=serial,
        mirror=False,
        newest_first=True,
    )
    steps.append(
        {
            "step": "read-log",
            "ok": True,
            "detail": {
                "line_count": log_result.get("line_count"),
                "sources": log_result.get("sources"),
            },
        }
    )

    lines: list[str] = list(log_result.get("lines") or [])
    defaults = [
        "今日已签",
        "签到完成",
        "开始静默签到",
        "待签",
        "无需签到",
        "签到失败",
        "未登录",
        "ready",
        "插件应用失败",
        "Hook 安装失败",
    ]
    keys = list(expect_keywords) if expect_keywords else defaults
    matched = [k for k in keys if any(k in ln for ln in lines)]
    success = bool(lines) and bool(matched)

    return {
        "ok": success,
        "serial": serial,
        "plugin": plugin_name,
        "host_package": host,
        "start_component": comp,
        "wait_sec": wait_sec,
        "matched_keywords": matched,
        "expect_keywords": keys,
        "line_count": len(lines),
        "lines": lines,
        "log": log_result,
        "steps": steps,
        "hint": (
            "验证通过：宿主已启动且出现 Andra I/E 日志"
            if success
            else (
                "验证未通过。检查：LSPosed 作用域=宿主；插件 .enabled；"
                "hooks.json 非空；强停后重开宿主。用 read_andra_log 再查。"
            )
        ),
    }


def triple_mirror_plugin_files(
    serial: str,
    folder: str,
    target_package: str,
    remote_plugin: str,
) -> str:
    """
    Ensure plugin files exist on:
      1) host media (already pushed)
      2) /sdcard/Andra/plugins
      3) Andra app private files (UI)
    and chmod best-effort.
    """
    public = f"/sdcard/Andra/plugins/{folder}"
    private = f"/sdcard/Android/data/{RUNTIME_PKG}/files/plugins/{folder}"
    cmd = (
        f"mkdir -p '{public}' '{private}' "
        f"/sdcard/Android/media/{target_package}/Andra/logs "
        f"/sdcard/Andra/logs "
        f"/sdcard/Android/data/{RUNTIME_PKG}/files/logs "
        f"&& for f in plugin.json hooks.json main.bsh INSTALL.md manifest.json .enabled; do "
        f"  if [ -e '{remote_plugin}/'$f ]; then "
        f"    cp -f '{remote_plugin}/'$f '{public}/'$f 2>/dev/null; "
        f"    cp -f '{remote_plugin}/'$f '{private}/'$f 2>/dev/null; "
        f"  fi; "
        f"done "
        f"&& touch '{remote_plugin}/.enabled' '{public}/.enabled' '{private}/.enabled' "
        f"&& chmod -R a+rX '{private}' 2>/dev/null || true "
        f"&& chmod -R a+rX '/sdcard/Andra' 2>/dev/null || true "
        f"&& echo MIRROR_OK "
        f"&& ls -la '{remote_plugin}' | head -20"
    )
    return _su(serial, cmd, timeout=30)
