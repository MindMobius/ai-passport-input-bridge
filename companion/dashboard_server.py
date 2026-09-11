#!/usr/bin/env python3
"""Local black-line control panel for the AI Passport WeChat bridge."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "companion" / "wechat_config.json"
LOGDIR = ROOT / "build" / "wechat" / "logs"
STATUS_PATH = ROOT / "build" / "wechat" / "status.json"
DEVICE_PATH = ROOT / "build" / "wechat" / "device.json"
PID_FILE = LOGDIR / "bridge.pid"
DASH_DIR = ROOT / "companion" / "dashboard"
PY = sys.executable
sys.path.insert(0, str(ROOT / "companion"))
from serial_transport import discover_direct_cdc_path  # noqa: E402

_ble_cache: tuple[float, dict] | None = None


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(int(pid)) and psutil.Process(int(pid)).is_running()
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except Exception:
            return False


def _bridge_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="ascii").strip())
    except Exception:
        return None


def _stop_bridge() -> None:
    pid = _bridge_pid()
    if not _pid_running(pid):
        return
    try:
        import psutil
        proc = psutil.Process(int(pid))
        for child in proc.children(recursive=True):
            try:
                child.terminate()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except Exception:
            proc.kill()
    except Exception:
        try:
            os.kill(int(pid), 15)
        except Exception:
            pass


def _start_bridge(channel: str) -> dict:
    _stop_bridge()
    LOGDIR.mkdir(parents=True, exist_ok=True)
    out = LOGDIR / "bridge.out.log"
    err = LOGDIR / "bridge.err.log"
    out.write_text("", encoding="utf-8")
    err.write_text("", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [PY, "-u", str(ROOT / "companion" / "wechat_bridge.py"), "--channel", channel,
         "--status-file", str(STATUS_PATH)],
        cwd=str(ROOT),
        env=env,
        stdout=open(out, "a", encoding="utf-8"),
        stderr=open(err, "a", encoding="utf-8"),
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(proc.pid), encoding="ascii")
    time.sleep(0.4)
    return {"pid": proc.pid, "running": proc.poll() is None}


def _audio_devices() -> list[dict]:
    try:
        import sounddevice as sd
        result = []
        for index, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_output_channels", 0)) > 0:
                result.append({
                    "index": index,
                    "name": dev.get("name"),
                    "outputs": int(dev.get("max_output_channels", 0)),
                    "inputs": int(dev.get("max_input_channels", 0)),
                    "default_samplerate": dev.get("default_samplerate"),
                })
        return result
    except Exception:
        return []


def _ble_status() -> dict:
    global _ble_cache
    now = time.time()
    if _ble_cache and now - _ble_cache[0] < 10:
        return _ble_cache[1]
    script = (
        "import asyncio\n"
        "from winrt.windows.devices.radios import Radio\n"
        "async def main():\n"
        "    rs=await Radio.get_radios_async()\n"
        "    print('BLUETOOTH=' + str(any(str(r.kind)=='RadioKind.BLUETOOTH' for r in rs)))\n"
        "asyncio.run(main())\n"
    )
    try:
        p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=8)
        available = "BLUETOOTH=True" in (p.stdout or "")
        result = {"available": available, "reason": "" if available else "Windows 未暴露 Bluetooth radio，需要重启电脑"}
    except Exception as exc:
        result = {"available": False, "reason": str(exc)}
    _ble_cache = (now, result)
    return result


def _tail(path: Path, lines: int = 200) -> list[str]:
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return data[-max(1, min(lines, 1000)):]
    except Exception:
        return []


class Handler(BaseHTTPRequestHandler):
    server_version = "PassportDashboard/1.0"

    def log_message(self, fmt, *args):
        return

    def _send(self, code: int, payload, content_type: str = "application/json; charset=utf-8") -> None:
        if not isinstance(payload, (bytes, bytearray)):
            payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html; charset=utf-8")
        if path == "/styles.css":
            return self._static("styles.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self._static("app.js", "application/javascript; charset=utf-8")
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path == "/api/state":
            cfg = _read_json(CONFIG_PATH, {})
            status = _read_json(STATUS_PATH, {})
            pid = _bridge_pid()
            running = _pid_running(pid)
            return self._send(200, {
                "bridge": {"running": running, "pid": pid if running else None},
                "config": cfg,
                "status": status,
                "logs": {
                    "stdout": _tail(LOGDIR / "bridge.out.log"),
                    "stderr": _tail(LOGDIR / "bridge.err.log"),
                },
            })
        if path == "/api/devices":
            usb_path = discover_direct_cdc_path()
            bridge_pid = _bridge_pid()
            return self._send(200, {
                "audio_outputs": _audio_devices(),
                "usb": {
                    "available": bool(usb_path),
                    "path": usb_path,
                    "in_use": _pid_running(bridge_pid),
                    "reason": "" if usb_path else "未发现 ESP32-C3 CDC 接口(设备未连接?)",
                },
                "ble": _ble_status(),
                "wifi": {"available": False, "reason": "固件尚无 WiFi 音频通道"},
                "device": _read_json(DEVICE_PATH, {}),
                "config_path": str(CONFIG_PATH),
            })
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"error": "invalid config"})
            _write_json(CONFIG_PATH, body)
            return self._send(200, {"ok": True, "config": body})
        if parsed.path == "/api/bridge":
            body = self._body()
            action = body.get("action")
            channel = body.get("channel") or _read_json(CONFIG_PATH, {}).get("channel", "usb")
            if action == "stop":
                _stop_bridge()
                return self._send(200, {"ok": True, "running": False})
            if action in ("start", "restart"):
                return self._send(200, {"ok": True, **_start_bridge(channel)})
            return self._send(400, {"error": "unknown action"})
        if parsed.path == "/api/client-log":
            body = self._body()
            try:
                LOGDIR.mkdir(parents=True, exist_ok=True)
                with (LOGDIR / "dashboard-client.log").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"server_time": time.time(), **(body if isinstance(body, dict) else {})},
                                        ensure_ascii=False) + "\n")
            except Exception:
                pass
            return self._send(200, {"ok": True})
        if parsed.path == "/api/test-mic":
            try:
                p = subprocess.run(
                    [PY, str(ROOT / "tools" / "test_virtual_mic_loopback.py")],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=30,
                )
                return self._send(200, {"ok": p.returncode == 0, "output": (p.stdout or "") + (p.stderr or "")})
            except Exception as exc:
                return self._send(500, {"ok": False, "output": str(exc)})
        return self._send(404, {"error": "not found"})

    def _static(self, name: str, content_type: str):
        try:
            data = (DASH_DIR / name).read_bytes()
            self._send(200, data, content_type)
        except Exception:
            self._send(404, {"error": f"{name} not found"})


def main() -> int:
    import argparse
    import webbrowser
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)  # 8765 被百度输入法占用,默认改用 8790
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    DASH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"[dashboard] 端口 {args.port} 无法绑定 ({exc});换 --port 指定其它端口", file=sys.stderr)
        return 3
    url = f"http://127.0.0.1:{args.port}/"
    print(f"[dashboard] {url}")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
