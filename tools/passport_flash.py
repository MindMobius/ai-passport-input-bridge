#!/usr/bin/env python3
"""Safe Windows helper for AI Passport backup and segmented flashing."""
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


def esptool(port: str, baud: int, *args: str) -> None:
    run([PY, "-m", "esptool", "--chip", "esp32c3", "--port", port, "--baud", str(baud), *args])


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="Windows COM port, e.g. COM5")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("action", choices=("info", "backup", "backup-full", "flash"))
    args = ap.parse_args()
    try:
        if args.action == "info":
            esptool(args.port, args.baud, "flash_id")
            esptool(args.port, args.baud, "read_mac")
        elif args.action in ("backup", "backup-full"):
            backup(args.port, args.baud, args.action == "backup-full")
        else:
            flash_segmented(args.port, args.baud)
    except (subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
