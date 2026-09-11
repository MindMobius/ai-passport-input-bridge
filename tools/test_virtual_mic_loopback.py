#!/usr/bin/env python3
"""Verify VB-CABLE loopback using the same sink path as the bridge."""
from __future__ import annotations

import argparse
import math
import sys
import threading
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "companion"))

import sounddevice as sd  # noqa: E402
from virtual_mic import VirtualMicSink  # noqa: E402
from wechat_bridge_config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--seconds", type=float, default=0.5)
    args = ap.parse_args()
    cfg = load_config(args.config)
    devices = sd.query_devices()
    input_idx = None
    for i, dev in enumerate(devices):
        name = str(dev.get("name", "")).upper()
        if "CABLE OUTPUT" in name and int(dev.get("max_input_channels", 0)) >= 2:
            input_idx = i
            break
    if input_idx is None:
        print("ERROR: no CABLE Output recording endpoint found", file=sys.stderr)
        return 2

    sink = VirtualMicSink(cfg)
    cap = sd.RawInputStream(
        device=input_idx, samplerate=48000, channels=2, dtype="int16", latency="low"
    )
    result: dict[str, object] = {}

    def reader() -> None:
        data, overflowed = cap.read(48000)
        result["data"] = bytes(data)
        result["overflowed"] = overflowed

    cap.start()
    thread = threading.Thread(target=reader)
    thread.start()
    sink.start()
    pcm = array("h")
    for n in range(int(16000 * args.seconds)):
        pcm.append(int(15000 * math.sin(2 * math.pi * 440 * n / 16000)))
    sink.write(pcm.tobytes())
    thread.join(timeout=2.0)
    cap.stop()
    cap.close()
    sink.close()

    data = result.get("data", b"")
    peak = 0
    for i in range(0, len(data) - 1, 2):
        peak = max(peak, abs(int.from_bytes(data[i:i + 2], "little", signed=True)))
    print(f"VB-CABLE loopback peak={peak} bytes={len(data)} overflow={result.get('overflowed')}")
    if peak < 100:
        print("FAIL: CABLE Input did not reach CABLE Output", file=sys.stderr)
        return 1
    print("PASS: CABLE Input -> CABLE Output works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
