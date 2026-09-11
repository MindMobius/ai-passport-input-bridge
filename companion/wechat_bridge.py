#!/usr/bin/env python3
"""AI Passport -> Windows virtual microphone bridge for WeChat IME.

Usage:
    .venv\\Scripts\\python.exe companion\\wechat_bridge.py --dry-run
    .venv\\Scripts\\python.exe companion\\wechat_bridge.py
    .venv\\Scripts\\python.exe companion\\wechat_bridge.py --list-audio-devices
"""
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import re
import sys
import time
from pathlib import Path

# Running this file directly puts companion/ on sys.path.  Keep it explicit so
# the same module also works from `python -m companion.wechat_bridge`.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from bridge_status import BridgeStatus, write_json_atomic
from keyinject_win import KeyInjectError, WindowsKeyInjector
from relay import BleakTransport, Relay, RelayError
from virtual_asr import VirtualMicSession
from win_default_mic import make_switcher
from virtual_mic import NullMicSink, VirtualMicError, make_sink
from wechat_bridge_config import load_config


# 板卡档案:这些是硬件事实(型号/屏幕/音频链路/USB 描述符),设备不上报,
# 但控制台"设备信息"面板需要显示。芯片/Flash/MAC/固件版本一律以设备上报为准
# (device.hello),档案里不重复写 —— 免得两处数据源打架。
DEVICE_PROFILE = {
    "model": "FoloToy AI Passport",
    "display": "ST7789 240x320",
    "audio": "ES8311 16 kHz mono",
    "usb_vid_pid": "303A:1001",
}


def _write_json(path: Path, obj: dict) -> None:
    """原子写(临时文件 + replace):控制台随时在读,不能读到半个 JSON。"""
    write_json_atomic(path, obj)


def build_device_info(ev: dict, cfg: dict) -> dict:
    """device.hello + 板卡档案 → 控制台"设备信息"面板的数据。

    设备上报的字段一律照抄;档案补设备压根不上报的硬件事实。任何字段取不到
    就留空,由前端渲染成 "--" —— 不用占位符冒充真值。
    """
    flash_mb = ev.get("flash_mb")
    return {
        **DEVICE_PROFILE,
        "mcu": ev.get("chip") or "",
        "flash": f"{flash_mb} MB" if isinstance(flash_mb, int) and flash_mb > 0 else "",
        "mac": ev.get("mac") or "",
        "fw": ev.get("fw") or "",
        "idf": ev.get("idf") or "",
        "proto": ev.get("proto"),
        "channel": cfg.get("channel"),
        "source": (f"device.hello(proto={ev.get('proto')}"
                   + (f", fw={ev.get('fw')}" if ev.get("fw") else "") + ")"),
    }


def write_device_info(path: Path, ev: dict, cfg: dict) -> dict:
    """device.hello → build/wechat/device.json(返回落盘内容,便于测试/调用方复用)。"""
    info = build_device_info(ev, cfg)
    _write_json(path, info)
    return info


def build_transport(cfg: dict):
    channel = str(cfg.get("channel", "ble")).lower()
    if channel == "ble":
        return BleakTransport()
    if channel == "usb":
        from serial_transport import SerialTransport
        return SerialTransport(port=cfg.get("usb_port") or None)
    raise RelayError(f"不支持的 channel: {channel!r}")


def print_audio_devices() -> int:
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"无法导入 sounddevice: {exc}", file=sys.stderr)
        return 1
    print("Windows audio output devices:")
    for index, dev in enumerate(sd.query_devices()):
        out_channels = int(dev.get("max_output_channels", 0))
        if out_channels <= 0:
            continue
        print(
            f"  [{index}] {dev.get('name')}  "
            f"inputs={dev.get('max_input_channels')} outputs={out_channels} "
            f"default_sr={dev.get('default_samplerate')}"
        )
    print("\nFor VB-CABLE, set audio_device to 'CABLE Input'.")
    print("WeChat IME should use 'CABLE Output' as its microphone.")
    return 0


def parse_device_status(text: str) -> dict:
    """Parse the firmware's `st` console output for dashboard state."""
    result: dict = {}
    m = re.search(r"soc:\s*(\d+)%\s+mv:\s*(\d+)", text)
    if m:
        result["battery_percent"] = int(m.group(1))
        result["battery_mv"] = int(m.group(2))
    m = re.search(r"link:\s*(.+)", text)
    if m:
        result["link"] = m.group(1).strip()
    m = re.search(r"streaming:\s*(\w+)\s+peak:\s*(\d+)", text)
    if m:
        result["streaming"] = m.group(1)
        result["audio_peak"] = int(m.group(2))
    m = re.search(r"drops:\s*audio\s*(\d+)\s+event\s*(\d+)", text)
    if m:
        result["audio_drops"] = int(m.group(1))
        result["event_drops"] = int(m.group(2))
    return result


def client_status_payload(cfg: dict) -> dict:
    """设备屏幕"连接信息"行要的 PC 侧状态(主机名/虚拟声卡/麦克风切换)。"""
    auto = bool(cfg.get("mic_auto_switch", True))
    return {
        "host": socket.gethostname()[:23],
        "sink": str(cfg.get("audio_device") or "")[:23],
        # 关闭自动切换时不报麦克风目标:设备据此显示 MIC AUTO OFF,
        # 而不是显示一个"看起来切了、其实没切"的名字。
        "mic": (str(cfg.get("mic_switch_target") or "")[:23] if auto else ""),
        "auto": auto,
    }


async def client_status_loop(relay, cfg: dict, interval_s: float = 2.0) -> None:
    """周期下发 bridge.status(设备端 6s 无心跳即视为 PC 离线)。

    未连接时 send_client_status 返回 False 且不抛;这里继续下一轮,
    设备重连后自动恢复,不需要重连逻辑配合。
    """
    payload = client_status_payload(cfg)
    announced = False
    while True:
        if await relay.send_client_status(payload) and not announced:
            announced = True
            print(f"[status] 电脑端心跳已下发(bridge.status):PC={payload['host']} "
                  f"声卡={payload['sink'] or '--'}")
        await asyncio.sleep(interval_s)


async def poll_device_status(transport, status: BridgeStatus) -> None:
    """Poll `st` after the transport is connected; USB exposes the full state."""
    if not hasattr(transport, "send_syscmd"):
        return
    for _ in range(30):
        try:
            text = await transport.send_syscmd("st")
        except Exception:
            await asyncio.sleep(1.0)
            continue
        parsed = parse_device_status(text)
        if parsed:
            status.update(device_status=parsed)
        break
    while True:
        await asyncio.sleep(5.0)
        try:
            text = await transport.send_syscmd("st")
            parsed = parse_device_status(text)
            if parsed:
                status.update(device_status=parsed)
        except Exception:
            pass


async def run_bridge(cfg: dict, device_addr: str | None, dry_run: bool, status_file: str | None = None) -> None:
    keys = WindowsKeyInjector(cfg, dry_run=dry_run)
    sink = make_sink(cfg, dry_run=dry_run)
    status_path = status_file or str(Path(__file__).resolve().parent.parent / "build" / "wechat" / "status.json")
    status = BridgeStatus(status_path, cfg)
    transport = build_transport(cfg)

    def phase(name: str) -> None:
        status.update(phase=name, connected=name == "connected")
        status.event("phase", name)

    def key_action(action: str) -> None:
        status.update(last_key={"action": action, "time": time.time()})
        status.event("key", action)
        keys.key_action(action)

    def session_event(kind: str, **fields) -> None:
        if kind == "voice_end":
            # 双保险:会话对象自己的还原失败/未跑到时,这里再还一次(幂等)。
            try:
                mic_switcher.restore()
            except Exception:
                pass
        status.update(
            voice={
                "active": kind == "voice_start",
                "last_event": kind,
                "time": time.time(),
                **fields,
            },
            audio={
                "device": cfg.get("audio_device"),
                "frames": getattr(sink, "frames", 0),
                "bytes": getattr(sink, "bytes_written", 0),
            },
        )
        status.event("voice", kind)

    def make_session() -> VirtualMicSession:
        return VirtualMicSession(sink, keys, cfg, on_event=session_event)

    # 默认麦克风:启动先补上次崩溃遗留的还原,退出时兜底还原
    mic_switcher = make_switcher(cfg)
    if mic_switcher.restore_leftover():
        print("[bridge] 已还原上次遗留的默认麦克风设置")

    device_path = Path(status_path).parent / "device.json"

    def on_device_info(ev: dict) -> None:
        """device.hello → build/wechat/device.json(控制台"设备信息"面板数据源)。

        设备上报 chip/flash/mac/fw/idf;档案补 model/display/audio/usb_vid_pid。
        写盘失败只记日志:面板是辅助信息,不该影响语音主路径。
        """
        try:
            info = write_device_info(device_path, ev, cfg)
        except Exception as exc:      # noqa: BLE001
            print(f"[bridge] 设备信息写盘失败: {exc}", file=sys.stderr)
            return
        status.update(device={"serial": info["mac"], "fw": info["fw"],
                              "chip": info["mcu"], "channel": info["channel"]})
        status.event("device", f"{info['mcu'] or '--'} fw={info['fw'] or '--'}")

    relay = Relay(
        transport=transport,
        asr_factory=make_session,
        inject_fn=lambda _text: None,
        key_action_fn=key_action,
        on_phase=phase,
        on_device_info=on_device_info,
        timeout=float(cfg.get("session_timeout_s", 3.0)),
        connect_timeout_s=float(cfg.get("connect_timeout_s", 5.0)),
        do_inject=False,
        do_approval=False,
        dry_run=dry_run,
    )

    print("[bridge] AI Passport -> WeChat IME virtual microphone")
    print(f"[bridge] channel={cfg.get('channel')} audio_device={cfg.get('audio_device')!r}")
    print(f"[bridge] voice_hotkey={cfg.get('voice_hotkey')!r} dry_run={dry_run}")
    print("[bridge] 操作: 单击 UP 启动 -> 任意键结束 -> DOWN 粘贴 -> OK 发送")
    if isinstance(sink, NullMicSink):
        print("[bridge] dry-run: 不会写入真实虚拟声卡，也不会注入真实按键")

    status_task = asyncio.create_task(poll_device_status(transport, status))
    status_push_task = asyncio.create_task(client_status_loop(relay, cfg))
    # connect_retries=0(默认)= 无限重试:设备没开机/出门了也不该让桥接退出,
    # 它回来就自动接上;要停就点控制台的"停止 Bridge"。
    attempts = int(cfg.get("connect_retries", 0))
    base_delay = float(cfg.get("connect_retry_delay_s", 2.0))
    max_delay = float(cfg.get("connect_retry_max_s", 30.0))
    try:
        attempt = 0
        while True:
            attempt += 1
            label = f"{attempt}" if attempts <= 0 else f"{attempt}/{attempts}"
            try:
                await relay.run(device_addr, console_stdin=False)
                reason = "链路断开"
            except RelayError as exc:
                if attempts > 0 and attempt >= attempts:
                    raise
                reason = f"连接失败: {exc}"
            if attempts > 0 and attempt >= attempts:
                break
            delay = min(base_delay * (2 ** min(attempt - 1, 4)), max_delay)
            print(f"[bridge] {reason},{delay:.0f}s 后重连(第 {label} 次)",
                  file=sys.stderr)
            status.update(phase="retrying", connected=False)
            status.event("retry", f"{label}: {reason}")
            await asyncio.sleep(delay)
    finally:
        status_task.cancel()
        status_push_task.cancel()
        if mic_switcher.available:
            mic_switcher.restore()          # 收尾兜底:别把用户的麦克风留在虚拟声卡
        status.update(phase="stopped", connected=False)
        status.event("phase", "stopped")
async def run_simulated_sequence(cfg: dict) -> None:
    """Exercise the full state machine without a device or system audio."""
    sim_cfg = dict(cfg)
    sim_cfg["target_title_regex"] = ""
    keys = WindowsKeyInjector(sim_cfg, dry_run=True)
    sink = NullMicSink()
    session = VirtualMicSession(sink, keys, sim_cfg)
    print("[simulate] voice start -> 10 audio frames -> voice end -> paste -> enter")
    await session.connect()
    for _ in range(10):
        await session.send_frame(b"\x00\x00" * 1600)
        await asyncio.sleep(0.01)
    await session.send_end()
    async for _ in session.results():
        pass
    await session.close()
    keys.key_action("paste")
    keys.key_action("enter")
    print(f"[simulate] OK: frames={sink.frames} bytes={sink.bytes_written}")


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Passport WeChat IME virtual microphone bridge")
    ap.add_argument("--config", help="配置文件路径，默认 companion/wechat_config.json")
    ap.add_argument("--device", help="BLE 地址；省略则扫描 AI Passport")
    ap.add_argument("--dry-run", action="store_true", help="不写声卡，只打印按键与音频统计")
    ap.add_argument("--list-audio-devices", action="store_true", help="列出 Windows 输出设备后退出")
    ap.add_argument("--channel", choices=("ble", "usb"), help="临时覆盖配置中的通道")
    ap.add_argument("--simulate", action="store_true", help="不连接设备，模拟完整按键/音频流程")
    ap.add_argument("--status-file", help="供本地配置页读取的状态 JSON 路径")
    args = ap.parse_args()

    if args.list_audio_devices:
        return print_audio_devices()

    try:
        cfg = load_config(args.config)
        if args.channel:
            cfg["channel"] = args.channel
        if args.dry_run:
            print("[bridge] dry-run 模式", file=sys.stderr)
        if args.simulate:
            asyncio.run(run_simulated_sequence(cfg))
        else:
            asyncio.run(run_bridge(cfg, args.device, args.dry_run, args.status_file))
    except KeyboardInterrupt:
        print("\n[bridge] 已退出")
        return 0
    except (RelayError, VirtualMicError, KeyInjectError, ValueError) as exc:
        print(f"[bridge] 错误: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
