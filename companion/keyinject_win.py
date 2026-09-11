#!/usr/bin/env python3
"""Windows keyboard injection for the AI Passport WeChat bridge.

The bridge deliberately does not try to pretend to be a standard microphone.
Instead it combines a virtual audio cable with normal Windows keyboard input:

* voice_hotkey  -> toggle WeChat IME voice input
* paste_hotkey  -> paste the text copied by the IME
* enter_hotkey  -> submit the Codex prompt
* clear_hotkey  -> clear the active editor
* cancel_hotkey -> cancel the current interaction
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable


class KeyInjectError(RuntimeError):
    """Raised when a key sequence cannot be injected safely."""


# Virtual-key fallbacks make the module importable/testable even without pywin32.
_VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
}
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    _VK[_c] = ord(_c.upper())
for _i in range(1, 25):
    _VK[f"f{_i}"] = 0x6F + _i


def parse_combo(combo: str) -> list[int]:
    parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
    if not parts:
        raise KeyInjectError(f"空快捷键: {combo!r}")
    result: list[int] = []
    for part in parts:
        if part not in _VK:
            raise KeyInjectError(f"不支持的按键: {part!r}")
        result.append(_VK[part])
    return result


def parse_sequence(sequence: str | Iterable[str]) -> list[list[int]]:
    if isinstance(sequence, str):
        raw = [p for p in sequence.split(",") if p.strip()]
    else:
        raw = list(sequence)
    if not raw:
        raise KeyInjectError("空按键序列")
    return [parse_combo(item) for item in raw]


@dataclass
class _Win32Backend:
    def key_down(self, vk: int) -> None:
        import win32api
        win32api.keybd_event(vk, 0, 0, 0)

    def key_up(self, vk: int) -> None:
        import win32api
        import win32con
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    def foreground_title(self) -> str:
        import win32gui
        return win32gui.GetWindowText(win32gui.GetForegroundWindow())


class WindowsKeyInjector:
    """Send global key combinations and maintain a small focus guard."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        dry_run: bool = False,
        backend: Any | None = None,
    ) -> None:
        self.config = config
        self.dry_run = bool(dry_run)
        self.backend = backend
        target = str(config.get("target_title_regex") or "").strip()
        self.target_re = re.compile(target, re.IGNORECASE) if target else None
        self.require_target_for_paste = bool(config.get("require_target_for_paste", True))
        self.require_target_for_enter = bool(config.get("require_target_for_enter", True))

    def _backend(self) -> Any:
        if self.backend is not None:
            return self.backend
        if sys.platform != "win32":
            raise KeyInjectError("键盘注入仅支持 Windows")
        self.backend = _Win32Backend()
        return self.backend

    def foreground_title(self) -> str:
        try:
            return self._backend().foreground_title()
        except Exception as exc:
            raise KeyInjectError(f"读取前台窗口失败: {exc}") from exc

    def _assert_target(self, purpose: str, require: bool) -> None:
        if not require or self.target_re is None:
            return
        title = self.foreground_title()
        if not self.target_re.search(title):
            raise KeyInjectError(
                f"{purpose} 前的前台窗口标题为 {title!r}，不匹配 "
                f"{self.target_re.pattern!r}; 请先聚焦 Codex/ChatGPT"
            )

    def _send_combo(self, keys: list[int], purpose: str) -> None:
        if self.dry_run:
            print(f"[key:dry-run] {purpose}: " + " + ".join(hex(k) for k in keys))
            return
        backend = self._backend()
        pressed: list[int] = []
        try:
            for key in keys:
                backend.key_down(key)
                pressed.append(key)
            time.sleep(0.015)
        finally:
            for key in reversed(pressed):
                try:
                    backend.key_up(key)
                except Exception:
                    pass
        time.sleep(0.020)

    def _send_sequence(self, sequence: str, purpose: str) -> None:
        for combo in parse_sequence(sequence):
            self._send_combo(combo, purpose)

    # -- public actions -------------------------------------------------
    def voice_start(self) -> None:
        # No foreground guard: WeChat IME owns this global hotkey and the user
        # normally keeps Codex focused while speaking.
        self._send_combo(
            parse_combo(self.config.get("voice_hotkey", "ctrl+win+shift")),
            "voice start",
        )

    def voice_stop(self) -> None:
        # WeChat IME documents that any key ends voice input. A bare modifier is
        # the least intrusive choice: it ends listening without typing text.
        self._send_combo(
            parse_combo(self.config.get("voice_stop_key", "shift")),
            "voice stop",
        )

    def voice_toggle(self) -> None:
        # Backward-compatible alias for older bridge code.
        self.voice_start()

    def paste(self) -> None:
        self._assert_target("粘贴", self.require_target_for_paste)
        self._send_combo(parse_combo(self.config.get("paste_hotkey", "ctrl+v")), "paste")

    def enter(self) -> None:
        self._assert_target("发送", self.require_target_for_enter)
        self._send_combo(parse_combo(self.config.get("enter_hotkey", "enter")), "enter")

    def clear(self) -> None:
        self._assert_target("清空", self.require_target_for_paste)
        self._send_sequence(self.config.get("clear_hotkey", "ctrl+a,delete"), "clear")

    def cancel(self) -> None:
        self._send_combo(parse_combo(self.config.get("cancel_hotkey", "escape")), "cancel")

    def key_action(self, action: str) -> None:
        action = str(action)
        if action == "paste":
            self.paste()
        elif action == "enter":
            self.enter()
        elif action == "clear":
            self.clear()
        elif action == "escape":
            self.cancel()
        else:
            raise KeyInjectError(f"未知按键动作 {action!r}")


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="AI Passport Windows key injector")
    ap.add_argument("--config")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("action", choices=("voice", "paste", "enter", "clear", "cancel"))
    args = ap.parse_args()
    from wechat_bridge_config import load_config
    cfg = load_config(args.config)
    injector = WindowsKeyInjector(cfg, dry_run=args.dry_run)
    print("foreground:", injector.foreground_title())
    if args.action == "voice":
        injector.voice_toggle()
    else:
        injector.key_action(args.action)
