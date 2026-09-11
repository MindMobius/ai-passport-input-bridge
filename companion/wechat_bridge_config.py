#!/usr/bin/env python3
"""Configuration for the WeChat IME + AI Passport virtual-microphone bridge."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    # Transport
    "channel": "ble",              # ble | usb
    "usb_port": "",
    "device_name": "AI Passport",
    # Virtual microphone
    "audio_device": "CABLE Input",
    "audio_device_index": None,
    "input_sample_rate": 16000,
    "output_sample_rate": None,    # None = use device default, normally 48000
    "output_channels": None,       # None = use up to 2 channels
    # Keyboard actions
    "voice_hotkey": "ctrl+win+shift",  # WeChat IME voice start
    "voice_stop_key": "shift",       # any-key stop for WeChat voice input
    "paste_hotkey": "ctrl+v",
    "enter_hotkey": "enter",
    "clear_hotkey": "ctrl+a,delete",
    "cancel_hotkey": "escape",
    # Safety / focus guard
    "target_title_regex": r"(Codex|ChatGPT)",
    "require_target_for_paste": True,
    "require_target_for_enter": True,
    # Session
    "connect_timeout_s": 5.0,
    "session_timeout_s": 3.0,
    "log_audio_frames": True,
}


def config_path() -> Path:
    override = os.environ.get("WECHAT_BRIDGE_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).with_name("wechat_config.json")


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    cfg_path = Path(path).expanduser().resolve() if path else config_path()
    cfg = dict(DEFAULTS)
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as fh:
            user_cfg = json.load(fh)
        if not isinstance(user_cfg, dict):
            raise ValueError(f"{cfg_path}: 顶层必须是 JSON object")
        cfg.update(user_cfg)
    cfg["_config_path"] = str(cfg_path)
    _validate(cfg)
    return cfg


def _validate(cfg: dict[str, Any]) -> None:
    if cfg["channel"] not in ("ble", "usb"):
        raise ValueError("channel 必须是 'ble' 或 'usb'")
    if int(cfg["input_sample_rate"]) <= 0:
        raise ValueError("input_sample_rate 必须大于 0")
    if cfg.get("output_sample_rate") is not None and int(cfg["output_sample_rate"]) <= 0:
        raise ValueError("output_sample_rate 必须大于 0")
    if cfg.get("output_channels") is not None and int(cfg["output_channels"]) <= 0:
        raise ValueError("output_channels 必须大于 0")


def write_example_config(path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(path).expanduser().resolve() if path else Path(__file__).with_name("wechat_config.json")
    target.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    p = write_example_config(sys.argv[1] if len(sys.argv) > 1 else None)
    print(p)
