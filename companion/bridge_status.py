#!/usr/bin/env python3
"""Small JSON status file shared by the bridge and the local dashboard."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


def write_json_atomic(path: str | os.PathLike[str], obj: Any) -> None:
    """原子写 JSON(临时文件 + 替换),对 Windows 的"读着的人"做重试。

    Windows 的 MoveFileEx 在目标文件被别的进程打开(哪怕只是读)时会直接
    报 WinError 5 拒绝访问 —— 而这个文件天生就有读者:控制台每 2s 轮询
    /api/state。没有重试的话,控制台页面一开着,桥接就会在写状态时崩掉
    (2026-09-11 实际踩到:open-console 打开页面后启动 Bridge 立即退出)。
    读者每次只开几微秒,退避重试几次即可;真失败也不抛出 —— 状态文件是
    辅助信息,不该拖垮语音主路径。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))       # 累计 ~1.1s,足够跨过读者的打开窗口
    print(f"[status] 写 {path} 失败(文件被占用),本次状态未落盘", file=sys.stderr)


class BridgeStatus:
    def __init__(self, path: str | os.PathLike[str], config: dict[str, Any]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {
            "updated_at": time.time(),
            "pid": os.getpid(),
            "channel": config.get("channel"),
            "phase": "starting",
            "connected": False,
            "config": {
                "audio_device": config.get("audio_device"),
                "voice_hotkey": config.get("voice_hotkey"),
                "voice_stop_key": config.get("voice_stop_key"),
                "target_title_regex": config.get("target_title_regex"),
            },
            "device": {},
            "voice": {"active": False},
            "last_key": None,
            "device_status": {},
            "events": [],
        }
        self._write()

    def _write(self) -> None:
        write_json_atomic(self.path, self._data)

    def update(self, **fields: Any) -> None:
        with self._lock:
            self._data.update(fields)
            self._data["updated_at"] = time.time()
            self._write()

    def event(self, kind: str, message: str, **fields: Any) -> None:
        with self._lock:
            item = {"time": time.time(), "kind": kind, "message": message, **fields}
            events = self._data.setdefault("events", [])
            events.append(item)
            del events[:-80]
            self._data["updated_at"] = time.time()
            self._write()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data, ensure_ascii=False))
