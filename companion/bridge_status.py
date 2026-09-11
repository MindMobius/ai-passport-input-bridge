#!/usr/bin/env python3
"""Small JSON status file shared by the bridge and the local dashboard."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


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
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

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
