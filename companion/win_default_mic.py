#!/usr/bin/env python3
"""把 Windows 默认录音设备临时切到虚拟声卡(仅在一次 Passport 语音会话内)。

背景:微信输入法(以及多数 App)默认听着"系统默认麦克风"。如果为了 Passport
把默认设备永久改成 CABLE Output,用户自己的耳机/耳麦就"哑"了(2026-09-11 用户
反馈的真实事故)。所以这里只在会话期间切换,用完立刻还原:

    UP 按下 → 打开虚拟声卡 → [默认麦克风 → CABLE Output] → 发 Ctrl+Win+Shift
    任意键结束 → 停虚拟声卡 → [默认麦克风 → 用户的设备] → 发 Shift

跨平台安全:非 Windows 或缺 API 时返回空实现,调用方无需分支。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_TARGET = "CABLE Output"
# 记住"切换前用户自己的设备":进程被杀也能在下次启动时还原
STATE_PATH = Path(__file__).resolve().parents[1] / "build" / "wechat" / "mic-saved.json"


class _NullSwitcher:
    """非 Windows / 关闭开关时的空实现(接口与真实实现一致)。"""

    available = False

    def use_virtual(self) -> bool:
        return False

    def restore(self) -> bool:
        return False

    def describe(self) -> str:
        return "disabled"

    def restore_leftover(self) -> bool:
        return False


class WindowsDefaultMicSwitcher:
    """基于 IPolicyConfigVista 的默认录音设备切换(Console/Multimedia/Comm)。"""

    available = True

    def __init__(self, target_name: str = DEFAULT_TARGET) -> None:
        self.target_name = target_name
        self._saved: dict[int, str] = {}
        self._virtual_id: str | None = None
        self._policy = None

    # ---- Core Audio 底层 ----
    @staticmethod
    def _ensure_com() -> None:
        """每个线程首次碰 COM 前都要初始化 —— 切换发生在 asyncio.to_thread
        的工作线程里,不初始化会报 '尚未调用 CoInitialize'(实测踩过)。"""
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass                      # 已初始化 / 其他线程模式,继续即可

    def _build_policy(self):
        self._ensure_com()
        if self._policy is not None:
            return self._policy
        from comtypes import GUID, CoCreateInstance, CLSCTX_ALL
        from win_default_mic_policy import IPolicyConfigVista  # 同目录,延迟导入
        self._policy = CoCreateInstance(
            GUID("{294935CE-F637-4E7C-A41B-AB255460B862}"),
            interface=IPolicyConfigVista, clsctx=CLSCTX_ALL)
        return self._policy

    @staticmethod
    def _enumerator():
        from comtypes import CoCreateInstance, CLSCTX_ALL
        from pycaw.pycaw import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator
        return CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, CLSCTX_ALL)

    @staticmethod
    def _roles():
        from pycaw.pycaw import ERole
        return (ERole.eConsole.value, ERole.eMultimedia.value, ERole.eCommunications.value)

    def current_defaults(self) -> dict[int, str]:
        from pycaw.pycaw import EDataFlow
        self._ensure_com()
        enum = self._enumerator()
        return {role: enum.GetDefaultAudioEndpoint(EDataFlow.eCapture.value, role).GetId()
                for role in self._roles()}

    def find_capture_endpoint(self, name_substring: str) -> str | None:
        """按名字子串找 capture 端点(如 'CABLE Output')。"""
        import warnings

        from pycaw.pycaw import AudioUtilities
        self._ensure_com()

        want = name_substring.lower()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")          # pycaw 属性读取会刷 COM 警告
            try:
                devices = AudioUtilities.GetAllDevices()
            except Exception as exc:                 # noqa: BLE001
                print(f"[mic] 枚举音频端点失败: {exc}", file=sys.stderr)
                return None
            for dev in devices:
                try:
                    dev_id = str(dev.id)
                    friendly = str(dev.FriendlyName)
                except Exception:
                    continue
                # 0.0.1 = capture(录音)端点;0.0.0 是播放端点
                if dev_id.lower().startswith("{0.0.1") and want in friendly.lower():
                    return dev_id
        return None

    # ---- 对外接口 ----
    def _save_state(self, saved: dict[int, str]) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps({str(k): v for k, v in saved.items()}),
                                  encoding="utf-8")
        except Exception:
            pass

    def _clear_state(self) -> None:
        try:
            STATE_PATH.unlink()
        except Exception:
            pass

    def restore_leftover(self) -> bool:
        """上次进程没来得及还原(崩溃/被杀)时,启动阶段补一次还原。"""
        try:
            if not STATE_PATH.exists():
                return False
            saved = {int(k): v for k, v in json.loads(STATE_PATH.read_text(encoding="utf-8")).items()}
        except Exception:
            self._clear_state()
            return False
        self._saved = saved
        restored = self.restore()
        if not restored:
            self._clear_state()
        return restored

    def use_virtual(self) -> bool:
        try:
            virtual = self._virtual_id or self.find_capture_endpoint(self.target_name)
            if not virtual:
                print(f"[mic] 未找到 '{self.target_name}' 录音端点,跳过切换", file=sys.stderr)
                return False
            current = self.current_defaults()
            if all(v == virtual for v in current.values()):
                return True                       # 已经是虚拟设备,无需记住
            if not self._saved:
                self._saved = dict(current)       # 只记一次:真实用户的默认设备
                self._save_state(self._saved)
            self._virtual_id = virtual
            policy = self._build_policy()
            for role in self._roles():
                policy.SetDefaultEndpoint(virtual, role)
            print("[mic] 默认麦克风 -> %s(会话期间)" % self.target_name)
            return True
        except Exception as exc:  # noqa: BLE001 - 切换失败绝不能打断语音
            print(f"[mic] 切换默认麦克风失败(忽略): {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return False

    def restore(self) -> bool:
        if not self._saved:
            return False
        try:
            policy = self._build_policy()
            for role, endpoint in self._saved.items():
                policy.SetDefaultEndpoint(endpoint, role)
            print("[mic] 默认麦克风已还原给用户设备")
            self._saved = {}
            self._clear_state()
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[mic] 还原默认麦克风失败: {type(exc).__name__}: {exc}", file=sys.stderr)
            return False

    def describe(self) -> str:
        return f"auto-switch -> {self.target_name}"


_SHARED: WindowsDefaultMicSwitcher | None = None


def make_switcher(config: dict[str, Any] | None = None):
    """按配置构造切换器:mic_auto_switch=false 或非 Windows → 空实现。

    同一进程内共享一个实例:语音会话(切换/还原)与桥接收尾(兜底还原)
    必须看到同一份"用户原本的设备"记录。
    """
    global _SHARED
    cfg = config or {}
    if sys.platform != "win32" or not cfg.get("mic_auto_switch", True):
        return _NullSwitcher()
    target = str(cfg.get("mic_switch_target") or DEFAULT_TARGET)
    if _SHARED is None or _SHARED.target_name != target:
        _SHARED = WindowsDefaultMicSwitcher(target)
    return _SHARED
