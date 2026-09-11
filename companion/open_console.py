#!/usr/bin/env python3
"""One-click launcher for the local AI Passport console (companion/dashboard).

启动策略:
  1. 端口已在监听 -> 直接打开浏览器;
  2. 未监听 -> 后台拉起 dashboard_server.py(带日志),等端口就绪后打开浏览器。
不启动 Bridge 本体;链路连接请在控制台里点"保存并重连"。
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
HOST = "127.0.0.1"
PORT = 8790
LOG_DIR = ROOT / "build" / "wechat" / "logs"


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((HOST, port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    url = f"http://{HOST}:{args.port}/"
    if not port_open(args.port):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with (LOG_DIR / "dashboard.log").open("a", encoding="utf-8") as out, \
             (LOG_DIR / "dashboard.err.log").open("a", encoding="utf-8") as err:
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            subprocess.Popen(
                [PY, str(ROOT / "companion" / "dashboard_server.py"),
                 "--no-open", "--port", str(args.port)],
                cwd=str(ROOT), env=env, creationflags=creationflags,
                stdout=out, stderr=err,
            )
        for _ in range(60):
            if port_open(args.port):
                break
            time.sleep(0.25)
        else:
            print(f"[console] 启动失败,端口 {args.port} 未就绪", file=sys.stderr)
            return 2
    print(f"[console] {url}")
    if not args.no_browser:
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
