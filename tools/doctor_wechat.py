#!/usr/bin/env python3
"""AI Passport 新电脑体检:一条命令回答"这台机器还缺什么"。

设计约束:
  * 只依赖标准库自身可跑(缺依赖时它才是最需要跑起来的那一个);
  * 每项都给出"缺了要做什么",不打印一堆无结论的技术细节;
  * 退出码 0 = 可以开始用;1 = 有关键项未满足。

用法:
  doctor.cmd                 # 完整体检(含 4s BLE 扫描)
  doctor.cmd --no-scan       # 跳过 BLE 扫描(快)
  .venv\\Scripts\\python.exe tools\\doctor_wechat.py --json   # 机器可读输出
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "companion"))

CONFIG_PATH = ROOT / "companion" / "wechat_config.json"
EXAMPLE_PATH = ROOT / "companion" / "wechat_config.example.json"
STATUS_PATH = ROOT / "build" / "wechat" / "status.json"
CONSOLE_PORT = 8790

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, level: str, detail: str, fix: str = "") -> None:
        self.items.append({"check": name, "level": level, "detail": detail, "fix": fix})

    def worst(self) -> str:
        levels = {i["level"] for i in self.items}
        return FAIL if FAIL in levels else (WARN if WARN in levels else OK)


def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def check_python(rep: Report) -> None:
    ver = ".".join(str(x) for x in sys.version_info[:3])
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if sys.version_info < (3, 10):
        rep.add("Python", FAIL, f"{ver}(需要 3.10+)",
                "安装 Python 3.10/3.11/3.12 后重新运行 install.cmd")
    elif not in_venv:
        rep.add("Python", WARN, f"{ver}(当前不是项目 .venv)",
                "双击 install.cmd 建虚拟环境;或直接用 open-console.cmd(它会用 .venv)")
    else:
        rep.add("Python", OK, f"{ver} (.venv)")


DEPS = [
    ("bleak", "BLE 通道"),
    ("serial", "USB 通道(pyserial)"),
    ("sounddevice", "写虚拟声卡"),
    ("win32api", "按键/剪贴板注入(pywin32)"),
    ("comtypes", "会话内切换默认麦克风"),
    ("pycaw", "音频端点枚举"),
    ("psutil", "控制台启停 Bridge"),
]


def check_deps(rep: Report) -> None:
    missing = [f"{mod}({why})" for mod, why in DEPS if not _module(mod)]
    if missing:
        rep.add("依赖", FAIL, "缺少 " + ", ".join(missing),
                "双击 install.cmd(或 .venv\\Scripts\\python.exe -m pip install -r companion\\requirements-wechat.txt)")
    else:
        rep.add("依赖", OK, f"{len(DEPS)} 个运行依赖齐全")


def _cable_endpoints() -> tuple[bool, bool, str]:
    """返回 (有 CABLE Input 播放端点, 有 CABLE Output 录音端点, 说明)"""
    try:
        import sounddevice as sd
    except Exception as exc:
        return False, False, f"sounddevice 不可用: {exc}"
    try:
        devices = list(sd.query_devices())
    except Exception as exc:
        return False, False, f"枚举音频设备失败: {exc}"
    has_in = any("cable input" in str(d["name"]).lower() and d["max_output_channels"] > 0
                 for d in devices)
    has_out = any("cable output" in str(d["name"]).lower() and d["max_input_channels"] > 0
                  for d in devices)
    names = [str(d["name"]) for d in devices if "cable" in str(d["name"]).lower()]
    return has_in, has_out, "; ".join(sorted(set(names))[:3]) or "未发现任何 CABLE 端点"


def check_virtual_cable(rep: Report) -> None:
    if not _module("sounddevice"):
        rep.add("虚拟声卡", WARN, "跳过(还没装 sounddevice)", "先跑 install.cmd")
        return
    has_in, has_out, detail = _cable_endpoints()
    if has_in and has_out:
        rep.add("虚拟声卡", OK, "VB-CABLE 已安装(CABLE Input → CABLE Output)")
    else:
        rep.add("虚拟声卡", FAIL, f"未检测到完整 VB-CABLE({detail})",
                "安装 VB-Audio Virtual Cable(管理员安装,装完重启),再跑一次体检")


def check_config(rep: Report) -> dict:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
    if not path.exists():
        rep.add("配置", FAIL, "companion/wechat_config.json 不存在且没有示例文件",
                "运行 install.cmd 生成配置")
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        rep.add("配置", FAIL, f"解析失败: {exc}", "删掉该文件后重跑 install.cmd")
        return {}
    if path is EXAMPLE_PATH:
        rep.add("配置", WARN, "只有示例配置(尚未生成 wechat_config.json)",
                "运行 install.cmd 会自动复制一份,或直接在控制台保存参数")
        return cfg
    channel = str(cfg.get("channel", "?"))
    audio_dev = str(cfg.get("audio_device", "?"))
    rep.add("配置", OK, f"channel={channel} audio_device={audio_dev!r} "
                        f"mic_auto_switch={bool(cfg.get('mic_auto_switch', True))}")
    return cfg


def check_usb(rep: Report) -> bool:
    if not _module("serial"):
        rep.add("设备/USB", WARN, "跳过(缺 pyserial)", "先跑 install.cmd")
        return False
    try:
        with contextlib.redirect_stderr(open(os.devnull, "w")):
            from serial_transport import discover_direct_cdc_path
            path = discover_direct_cdc_path()
    except Exception as exc:
        rep.add("设备/USB", WARN, f"探测异常: {exc}", "")
        return False
    if path:
        rep.add("设备/USB", OK, "已插好(ESP32-C3 USB-Serial-JTAG)")
        return True
    rep.add("设备/USB", WARN, "未发现 Passport(没插 USB 或设备没开机)", "")
    return False


def _ble_probe(scan: bool) -> dict:
    """在子进程里查 radio + 扫设备:同进程里 pywin32 的 STA 会破坏 WinRT。"""
    code = (
        "import asyncio, json, sys\n"
        "out = {'radio': None, 'devices': [], 'error': ''}\n"
        "try:\n"
        "    from winrt.windows.devices.radios import Radio\n"
        "    async def r():\n"
        "        return await Radio.get_radios_async()\n"
        "    out['radio'] = any(str(x.kind) == 'RadioKind.BLUETOOTH' for x in asyncio.run(r()))\n"
        "except Exception as e:\n"
        "    out['error'] = f'radio: {e}'\n"
        f"if {scan!r} and out['radio']:\n"
        "    try:\n"
        "        from bleak import BleakScanner\n"
        "        async def s():\n"
        "            return await BleakScanner.discover(timeout=4.0, return_adv=True)\n"
        "        for addr, (dev, adv) in asyncio.run(s()).items():\n"
        "            out['devices'].append({'addr': addr,\n"
        "                                   'name': dev.name or adv.local_name or '',\n"
        "                                   'rssi': adv.rssi})\n"
        "    except Exception as e:\n"
        "        out['error'] = (out['error'] + ' | scan: ' + str(e)).strip(' |')\n"
        "print(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, timeout=40)
        for line in reversed((proc.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        return {"radio": None, "devices": [], "error": (proc.stderr or "").strip()[:200]}
    except Exception as exc:
        return {"radio": None, "devices": [], "error": str(exc)}


def check_ble(rep: Report, scan: bool) -> tuple[bool, bool]:
    """返回 (radio 可用, 扫到设备)。"""
    if not _module("bleak"):
        rep.add("设备/BLE", WARN, "跳过(缺 bleak)", "先跑 install.cmd")
        return False, False
    info = _ble_probe(scan)
    radio = info.get("radio")
    if radio is False:
        rep.add("设备/BLE", WARN, "Windows 未暴露蓝牙 radio",
                "设备管理器里启用蓝牙;若提示需重启,重启电脑后重试")
        return False, False
    if radio is None:
        rep.add("设备/BLE", WARN, f"蓝牙状态未知({info.get('error') or '探测失败'})", "")
        return False, False
    if not scan:
        rep.add("设备/BLE", OK, "蓝牙 radio 可用(未扫描设备)")
        return True, False
    hit = [x for x in info.get("devices", [])
           if "ai passport" in str(x.get("name", "")).lower()]
    if hit:
        rep.add("设备/BLE", OK, f"发现 AI Passport {hit[0]['addr']} ({hit[0].get('rssi')} dBm)")
        return True, True
    rep.add("设备/BLE", WARN, "蓝牙可用但没扫到 AI Passport(设备没开机/太远)", "")
    return True, False


def _capture_endpoint_names() -> dict[str, str]:
    """endpoint id -> 友好名(用于把默认设备 ID 翻成人看得懂的名字)。"""
    try:
        import warnings

        warnings.filterwarnings("ignore")
        from pycaw.pycaw import AudioUtilities

        out = {}
        for dev in AudioUtilities.GetAllDevices():
            did = str(getattr(dev, "id", "") or "")
            if ".1." in did:                      # 采集端点
                try:
                    out[did.lower()] = dev.FriendlyName or "?"
                except Exception:
                    out[did.lower()] = "?"
        return out
    except Exception:
        return {}


def check_default_mic(rep: Report) -> None:
    """★ 关键检查:默认录音设备有没有被上次会话留在虚拟声卡上。

    本项目的麦克风切换是"会话内临时切 CABLE Output,结束还原"。如果进程被强杀
    或断电,残留可能留在系统默认设备上,导致用户自己的麦克风"听起来没声音"。
    这里主动发现,并给出还原命令。
    """
    try:
        import sys as _sys

        _sys.path.insert(0, str(ROOT / "companion"))
        from win_default_mic import make_switcher
    except Exception as exc:
        rep.add("默认麦克风", WARN, f"跳过(无法加载切换模块: {exc})", "")
        return
    sw = make_switcher({"mic_auto_switch": True, "mic_switch_target": "CABLE Output"})
    if not getattr(sw, "available", False):
        rep.add("默认麦克风", WARN, "跳过(非 Windows 或缺少 pycaw/comtypes)", "")
        return
    try:
        cur = sw.current_defaults()
        cable = (sw.find_capture_endpoint("CABLE Output") or "").lower()
    except Exception as exc:
        rep.add("默认麦克风", WARN, f"读取失败: {exc}", "")
        return
    names = _capture_endpoint_names()
    stuck = [rid for rid in cur.values() if cable and str(rid).lower() == cable]
    if stuck:
        rep.add("默认麦克风", FAIL,
                f"默认录音设备仍指向 CABLE Output({len(stuck)}/3 个角色)—— 你自己的麦克风会听起来没声音",
                "还原:.venv\\Scripts\\python.exe tools\\restore-default-mic.py"
                "(或跑控制台的\"恢复默认麦克风\")")
        return
    shown = []
    for rid in sorted(set(cur.values())):
        shown.append(names.get(str(rid).lower(), str(rid)[:38]))
    rep.add("默认麦克风", OK, "当前 = " + "; ".join(shown))


def check_mic_users(rep: Report) -> None:
    """谁在用麦克风:读 Windows 自己的使用记录(LastUsedTimeStop=0 表示此刻在用)。"""
    import winreg

    hits = []
    roots = (
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone\\NonPackaged"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone"),
    )
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                sub = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, sub)
                    except OSError:
                        break
                    sub += 1
                    try:
                        with winreg.OpenKey(key, name) as sk:
                            stop = winreg.QueryValueEx(sk, "LastUsedTimeStop")[0]
                    except OSError:
                        continue
                    if stop == 0:
                        hits.append(name.replace("#", "\\"))
        except OSError:
            continue
    if hits:
        rep.add("麦克风占用", WARN, "此刻正在使用: " + "; ".join(hits[:4]),
                "若是设置页面/远程工具占用,关掉它们再测;独占模式能打开即说明没被独占")
    else:
        rep.add("麦克风占用", OK, "此刻没有 App 在使用麦克风")


def check_console(rep: Report) -> None:
    listening = False
    try:
        with socket.socket() as sock:
            sock.settimeout(0.4)
            listening = sock.connect_ex(("127.0.0.1", CONSOLE_PORT)) == 0
    except Exception:
        pass
    bridge_running = None
    if STATUS_PATH.exists():
        try:
            st = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            age = time.time() - float(st.get("updated_at", 0))
            bridge_running = age < 60 and st.get("phase") not in (None, "stopped")
        except Exception:
            bridge_running = None
    detail = []
    detail.append(f"控制台{'已运行' if listening else '未运行'}(:{CONSOLE_PORT})")
    if bridge_running is not None:
        detail.append(f"Bridge{'在线' if bridge_running else '停止'}")
    level = OK if listening or bridge_running else WARN
    rep.add("运行状态", level, " / ".join(detail),
            "" if level == OK else "双击 open-console.cmd → 连接配置 → 保存并重连")


def check_wechat_ime(rep: Report) -> None:
    names = ("WeType", "WeChatAppEx", "Weixin", "WeChat")
    hit = []
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, timeout=15).stdout.lower()
        hit = [n for n in names if n.lower() in out]
    except Exception:
        pass
    if hit:
        rep.add("微信输入法", OK, "进程在运行: " + ", ".join(hit))
    else:
        rep.add("微信输入法", WARN, "未检测到微信输入法进程",
                "正常:用到时再切换;请确认它把麦克风设为 CABLE Output")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scan", action="store_true", help="跳过 BLE 扫描")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rep = Report()
    check_python(rep)
    check_deps(rep)
    check_virtual_cable(rep)
    cfg = check_config(rep)
    usb = check_usb(rep)
    ble_radio, ble_found = check_ble(rep, scan=not args.no_scan)
    check_console(rep)
    check_default_mic(rep)
    check_mic_users(rep)
    check_wechat_ime(rep)

    if args.json:
        print(json.dumps({"worst": rep.worst(), "items": rep.items, "config": cfg},
                         ensure_ascii=False, indent=2))
        return 0 if rep.worst() != FAIL else 1

    icons = {OK: "[OK]  ", WARN: "[!!]  ", FAIL: "[XX]  "}
    print("AI Passport 体检 (Windows)")
    print("-" * 62)
    for item in rep.items:
        print(f"{icons[item['level']]}{item['check']:<10} {item['detail']}")
        if item["fix"] and item["level"] != OK:
            print(f"        → {item['fix']}")
    print("-" * 62)
    worst = rep.worst()
    if worst == OK:
        print("结论: 可以开始使用。双击 open-console.cmd → 选通道 → 保存并重连")
    elif worst == WARN:
        print("结论: 基本可用,上面的 [!!] 项按提示处理即可(设备没插/没开机属于正常)")
    else:
        print("结论: 还缺关键项,先按 [XX] 的提示处理,然后重跑 doctor.cmd")
    if ble_found:
        ble_text = "已发现设备"
    elif not ble_radio:
        ble_text = "不可用"
    elif args.no_scan:
        ble_text = "radio 可用(未扫描)"
    else:
        ble_text = "radio 可用,未扫到设备"
    print(f"(USB: {'已连接' if usb else '未连接'} · BLE: {ble_text})")
    return 0 if worst != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
