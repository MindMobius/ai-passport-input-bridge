#!/usr/bin/env python3
"""麦克风电平自检:用 8 秒实时电平条判断"麦克风到底有没有拾音"。

用法(对着麦克风说话/拍手):
    mic-level-test.cmd            # 双击也行
    .venv\\Scripts\\python.exe tools\\mic-level-test.py --seconds 8 --device "Beoplay A1"

输出:每 0.5 秒一行 + 峰值柱;结束时给结论(有信号 / 基本静音)。
"""
from __future__ import annotations

import argparse
import array
import sys

import sounddevice as sd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--device", help="名称片段,默认用系统默认录音设备")
    args = ap.parse_args()

    if args.device:
        hits = [i for i, d in enumerate(sd.query_devices())
                if d["max_input_channels"] > 0 and args.device.lower() in d["name"].lower()]
        if not hits:
            print(f"找不到输入设备: {args.device}\n", file=sys.stderr)
            print("可用的输入设备(用 --device 里的片段匹配其中一个):", file=sys.stderr)
            seen = set()
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and d["name"] not in seen:
                    seen.add(d["name"])
                    print(f"  [{i:3d}] {d['name']}", file=sys.stderr)
            print("\n提示:名字要写全/写对,例如 --device \"Beoplay A1\"", file=sys.stderr)
            return 2
        if len(hits) > 1:
            print(f"匹配到 {len(hits)} 个输入端点:")
            for i in hits:
                print(f"  [{i:3d}] {sd.query_devices(i)['name']}")
            print(f"→ 使用第一个 [{hits[0]}];要测另一条请写更精确的名字"
                  f"(例如 --device \"2- Beoplay A1\" 指蓝牙那条)\n")
        dev = hits[0]
    else:
        dev = sd.default.device[0]

    info = sd.query_devices(dev)
    rate = int(info["default_samplerate"])
    print(f"设备: {info['name']}  ({rate} Hz)")
    print("对着麦克风说话/拍手,看电平条是否动 …\n")

    block = int(rate * 0.5)
    peak_all = 0
    peaks: list[int] = []
    bars_low = 0
    with sd.RawInputStream(device=dev, samplerate=rate, channels=1, dtype="int16",
                           blocksize=block) as st:
        for n in range(int(args.seconds / 0.5)):
            data, overflowed = st.read(block)
            a = array.array("h", bytes(data))
            peak = max(abs(x) for x in a) if a else 0
            peak_all = max(peak_all, peak)
            peaks.append(peak)
            level = min(40, peak * 40 // 3000)
            if peak < 300:
                bars_low += 1
            print(f"  {n * 0.5 + 0.5:4.1f}s  peak={peak:5d}  {'#' * level}{'.' * (40 - level)}")

    print()
    print(f"峰值 = {peak_all} ({peak_all / 32768:.4f} 满刻度)")
    if peak_all > 2000:
        print("结论: 麦克风工作正常,拾音清晰")
    elif peak_all > 300:
        print("结论: 有信号但很弱(贴近说话再试一次;或设备音量偏小)")
    else:
        span = (max(peaks) - min(peaks)) if peaks else 0
        if peak_all > 0 and span <= max(20, peak_all // 4):
            print(f"结论: 这条通路一直在送**恒定值**(peak≈{peak_all},波动 {span})—— "
                  "不是拾音,而是这条采集通路没有麦克风数据")
            print("      常见于设备把采集端点做成空壳;换设备上的另一条通路(如蓝牙)再测对比")
        else:
            print(f"结论: 基本静音 —— 麦克风没有拾音(峰值波动 {span};"
                  "设备侧静音/卡住,或系统默认设备不对)")
    return 0 if peak_all > 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
