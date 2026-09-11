#!/usr/bin/env python3
"""把默认录音设备还原给用户自己的设备(撤销 Passport 会话切换)。

用途:桥接进程被强杀、或用户发现"麦克风没声音"时手动救急。
正常路径不需要它 —— 会话结束与桥接退出都会自动还原。

用法:
    .venv\\Scripts\\python.exe tools\\restore-default-mic.py            # 用状态文件还原
    .venv\\Scripts\\python.exe tools\\restore-default-mic.py --name "Beoplay A1"  # 指定设备名
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "companion"))

from win_default_mic import WindowsDefaultMicSwitcher  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="直接指定要设为默认录音设备的名称片段")
    args = ap.parse_args()

    sw = WindowsDefaultMicSwitcher()
    if args.name:
        target = sw.find_capture_endpoint(args.name)
        if not target:
            print(f"未找到匹配 '{args.name}' 的录音设备", file=sys.stderr)
            return 2
        sw._saved = {role: target for role in sw._roles()}   # 显式指定:全部角色
        sw.restore()
        return 0

    if sw.restore_leftover():
        print("已按 build/wechat/mic-saved.json 还原默认录音设备")
        return 0
    print("没有待还原的切换记录(默认录音设备未被本工具改动)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
