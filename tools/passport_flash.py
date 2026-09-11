#!/usr/bin/env python3
"""Safe Windows helper for AI Passport backup / flashing.

用法(设备用 USB 线连好):
  python tools/passport_flash.py info          # 读芯片/MAC(自动发现端口)
  python tools/passport_flash.py backup        # 备份分区表/NVS/cardid/recovery
  python tools/passport_flash.py app           # ★只更新应用分区 0x10000
  python tools/passport_flash.py flash         # 分段烧 bootloader+分区表+应用
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_firmware import parse_partition_table  # noqa: E402

SEGMENTS = ROOT / "build" / "wechat" / "segments"
BACKUPS = ROOT / "build" / "wechat" / "backup"
PY = sys.executable


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _needs_usb_reset(port: str) -> bool:
    """ESP32-C3 原生 USB-Serial-JTAG(设备接口路径)必须显式 usb-reset。

    否则 esptool 会报 "Wrong boot mode detected (0xa)":这条路径不是普通 UART,
    默认的 DTR/RTS 复位序列对 USB-Serial-JTAG 无效(2026-09-11 真机实测)。
    """
    p = (port or "").lower()
    return "vid_303a" in p and "pid_1001" in p


def esptool(port: str, baud: int, *args: str) -> None:
    cmd = [PY, "-m", "esptool", "--chip", "esp32c3", "--port", port, "--baud", str(baud)]
    if _needs_usb_reset(port):
        cmd += ["--before", "usb-reset"]
    run(cmd + list(args))


def read_flash(port: str, baud: int, offset: int, size: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    esptool(port, baud, "read_flash", hex(offset), hex(size), str(output))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    print(f"backup {output.name}: {output.stat().st_size} bytes sha256={digest}")


def check_partition_table(path: Path) -> None:
    raw = path.read_bytes()
    partitions, found_md5 = parse_partition_table(raw)
    labels = {p.label: p for p in partitions}
    print("current partitions:")
    for p in partitions:
        print(f"  {p.label:8s} 0x{p.offset:06x} 0x{p.size:06x}")
    if not found_md5:
        raise RuntimeError("current partition table has no MD5 marker")
    expected = {"factory": 0x10000, "cardid": 0x356000, "recovery": 0x700000}
    for label, offset in expected.items():
        if label not in labels:
            raise RuntimeError(f"current partition table is missing {label}")
        if labels[label].offset != offset:
            raise RuntimeError(f"{label} offset mismatch: 0x{labels[label].offset:x} != 0x{offset:x}")
    print("partition table protection check: PASS")


def backup(port: str, baud: int, full: bool) -> None:
    read_flash(port, baud, 0x8000, 0x1000, BACKUPS / "partition-table.bin")
    check_partition_table(BACKUPS / "partition-table.bin")
    read_flash(port, baud, 0x9000, 0x6000, BACKUPS / "nvs.bin")
    read_flash(port, baud, 0x10000, 0x300000, BACKUPS / "factory-app.bin")
    read_flash(port, baud, 0x356000, 0x4000, BACKUPS / "cardid.bin")
    read_flash(port, baud, 0x700000, 0x100000, BACKUPS / "recovery.bin")
    if full:
        read_flash(port, baud, 0, 0x800000, BACKUPS / "flash-8mb.bin")


def flash_segmented(port: str, baud: int) -> None:
    bootloader = SEGMENTS / "bootloader.bin"
    table = SEGMENTS / "partition-table.bin"
    app = SEGMENTS / "FoloToy-AI-Passport.bin"
    for path in (bootloader, table, app):
        if not path.is_file():
            raise FileNotFoundError(path)
    esptool(
        port, baud, "write_flash", "--flash_mode", "dio", "--flash_freq", "80m",
        "--flash_size", "8MB", "0x0", str(bootloader), "0x8000", str(table),
        "0x10000", str(app),
    )
    print("Segmented flash complete. NVS/cardid/recovery were not written.")


def flash_app_only(port: str, baud: int) -> None:
    """只写 0x10000 应用分区:不动 bootloader / 分区表 / NVS / cardid / recovery。

    日常固件迭代用这个(设备已配网、cardid 已写入时尤其重要)。
    """
    app = SEGMENTS / "FoloToy-AI-Passport.bin"
    if not app.is_file():
        raise FileNotFoundError(f"{app} 不存在,先跑 build-firmware.cmd")
    if app.stat().st_size > 0x300000:
        raise ValueError(f"应用镜像 {app.stat().st_size} 超过 factory 分区 0x300000")
    esptool(
        port, baud, "write_flash", "--flash_mode", "dio", "--flash_freq", "80m",
        "--flash_size", "8MB", "0x10000", str(app),
    )
    print("App-only flash complete (0x10000). "
          "bootloader/partition-table/NVS/cardid/recovery untouched.")


def resolve_port(explicit: str | None) -> str:
    """--port 省略时自动发现:优先 USB-Serial-JTAG 设备接口路径(绕开坏 COM 口)。"""
    if explicit:
        return explicit
    sys.path.insert(0, str(ROOT / "companion"))
    try:
        from serial_transport import discover_direct_cdc_path

        direct = discover_direct_cdc_path()
        if direct:
            print(f"[flash] 自动发现设备接口路径: {direct}")
            return direct
    except Exception as exc:
        print(f"[flash] 设备接口路径探测失败({exc}),改用 COM 扫描", file=sys.stderr)
    try:
        from serial.tools import list_ports

        for port in list_ports.comports():
            hay = f"{port.description} {port.hwid}".upper()
            if "303A" in hay or "JTAG" in hay:
                print(f"[flash] 自动发现串口: {port.device}")
                return port.device
    except Exception:
        pass
    raise RuntimeError("未找到 Passport:插好 USB 线,或用 --port 指定设备接口路径/COM 口")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="省略=自动发现(设备接口路径优先,其次 COM 口)")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("action", choices=("info", "backup", "backup-full", "flash", "app"))
    args = ap.parse_args()
    try:
        port = resolve_port(args.port)
        if args.action == "info":
            esptool(port, args.baud, "flash_id")
            esptool(port, args.baud, "read_mac")
        elif args.action in ("backup", "backup-full"):
            backup(port, args.baud, args.action == "backup-full")
        elif args.action == "app":
            flash_app_only(port, args.baud)
        else:
            flash_segmented(port, args.baud)
    except (subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
