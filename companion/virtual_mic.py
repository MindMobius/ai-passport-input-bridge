#!/usr/bin/env python3
"""Virtual microphone sink for the AI Passport WeChat bridge.

The Passport sends 16 kHz mono signed 16-bit PCM frames.  This module writes
those frames to a normal Windows output endpoint (normally VB-CABLE's
``CABLE Input``).  WeChat IME then reads the matching recording endpoint
(``CABLE Output``) as its microphone.
"""
from __future__ import annotations

from array import array
import contextlib
import math
import sys
import threading
import time
from typing import Any


class VirtualMicError(RuntimeError):
    """Raised when the configured virtual audio endpoint cannot be used."""


def _clamp_i16(value: float) -> int:
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return int(value)


def resample_pcm16_mono(
    pcm: bytes,
    in_rate: int,
    out_rate: int,
    out_channels: int = 1,
) -> bytes:
    """Convert little-endian mono PCM16 to the target rate/channel count.

    The implementation is intentionally dependency-free.  It is good enough
    for speech at 16 kHz and for virtual-cable output at 48 kHz.
    """
    if not pcm:
        return b""
    if out_channels < 1:
        raise ValueError("out_channels must be >= 1")
    if in_rate <= 0 or out_rate <= 0:
        raise ValueError("sample rates must be > 0")

    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return b""

    if in_rate == out_rate:
        converted = samples
    else:
        out_len = max(1, int(round(len(samples) * out_rate / in_rate)))
        converted = array("h")
        last_index = len(samples) - 1
        for i in range(out_len):
            pos = i * in_rate / out_rate
            idx = int(pos)
            if idx >= last_index:
                value = samples[last_index]
            else:
                frac = pos - idx
                value = _clamp_i16(
                    samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
                )
            converted.append(value)

    if out_channels == 1:
        out = converted
    else:
        out = array("h")
        for sample in converted:
            for _ in range(out_channels):
                out.append(sample)

    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


class NullMicSink:
    """No-op sink used by ``--dry-run`` and unit tests."""

    def __init__(self) -> None:
        self.started = False
        self.bytes_written = 0
        self.frames = 0
        self.finished = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def write(self, pcm: bytes) -> None:
        if not self.started:
            raise VirtualMicError("write() called before start()")
        self.bytes_written += len(pcm)
        self.frames += 1

    def finish(self) -> None:
        self.finished = True

    def close(self) -> None:
        self.closed = True


class VirtualMicSink:
    """Write Passport PCM to a configured output endpoint."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.device_name = str(config.get("audio_device") or "").strip()
        self.device_index = config.get("audio_device_index")
        self.input_sample_rate = int(config.get("input_sample_rate", 16000))
        self.requested_output_rate = config.get("output_sample_rate")
        self.requested_channels = config.get("output_channels")
        self._stream: Any = None
        self._device: dict[str, Any] | None = None
        self._samplerate = 0
        self._channels = 0
        self.frames = 0
        self.bytes_written = 0
        self._lock = threading.Lock()

    @property
    def samplerate(self) -> int:
        return self._samplerate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    @staticmethod
    def list_output_devices() -> list[dict[str, Any]]:
        import sounddevice as sd  # lazy: config/test paths should not need audio

        result: list[dict[str, Any]] = []
        for idx, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_output_channels", 0)) > 0:
                result.append({"index": idx, **dict(dev)})
        return result

    def _resolve_device(self) -> dict[str, Any]:
        import sounddevice as sd

        devices = self.list_output_devices()
        if self.device_index is not None:
            wanted = int(self.device_index)
            for dev in devices:
                if int(dev["index"]) == wanted:
                    return dev
            raise VirtualMicError(f"找不到音频输出设备 index={wanted}")

        if not self.device_name:
            # Explicit opt-in to the system default output.  This is useful for
            # a loopback test, but normally the user wants CABLE Input.
            default_index = sd.default.device[1]
            for dev in devices:
                if int(dev["index"]) == int(default_index):
                    return dev
            raise VirtualMicError("找不到系统默认音频输出设备")

        needle = self.device_name.casefold()
        matches = [d for d in devices if needle in str(d.get("name", "")).casefold()]
        if not matches:
            names = "\n".join(f"  [{d['index']}] {d.get('name')}" for d in devices)
            raise VirtualMicError(
                f"找不到输出设备 {self.device_name!r}。可用输出设备:\n{names}\n"
                "请先安装/配置 VB-CABLE，或修改 wechat_config.json 的 audio_device。"
            )

        wanted_sr = int(self.requested_output_rate) if self.requested_output_rate else None
        wanted_ch = int(self.requested_channels) if self.requested_channels else None

        def score(dev: dict[str, Any]) -> tuple[int, int, int]:
            name = str(dev.get("name", "")).casefold()
            exact = 1 if name == needle else 0
            channels = int(dev.get("max_output_channels", 0))
            sr_delta = (
                abs(int(float(dev.get("default_samplerate") or 0)) - wanted_sr)
                if wanted_sr else 0
            )
            channel_delta = abs(channels - wanted_ch) if wanted_ch else 0
            return (exact, -sr_delta, -channel_delta)

        return max(matches, key=score)

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            if self._stream is not None:
                return
            dev = self._resolve_device()
            self._device = dev
            sr = int(self.requested_output_rate or dev.get("default_samplerate") or 48000)
            max_channels = int(dev.get("max_output_channels", 1))
            channels = int(self.requested_channels or min(2, max_channels))
            channels = max(1, min(channels, max_channels))
            try:
                stream = sd.RawOutputStream(
                    device=int(dev["index"]),
                    samplerate=sr,
                    channels=channels,
                    dtype="int16",
                    latency="low",
                )
                stream.start()
            except Exception as exc:  # PortAudio errors have varied classes
                raise VirtualMicError(
                    f"无法打开输出设备 {dev.get('name')!r} "
                    f"({sr} Hz, {channels} ch): {exc}"
                ) from exc
            self._stream = stream
            self._samplerate = sr
            self._channels = channels
            print(
                f"[mic] 已打开虚拟麦克风输出: {dev.get('name')} "
                f"index={dev['index']} {sr}Hz {channels}ch"
            )

    def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        with self._lock:
            stream = self._stream
            if stream is None:
                raise VirtualMicError("write() called before start()")
            converted = resample_pcm16_mono(
                pcm, self.input_sample_rate, self._samplerate, self._channels
            )
            if converted:
                stream.write(converted)
                self.frames += 1
                self.bytes_written += len(converted)

    def finish(self) -> None:
        # Let the audio engine consume the final block before stopping.
        if self._stream is not None:
            time.sleep(0.12)
            with contextlib.suppress(Exception):
                self._stream.stop()

    def close(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
            if stream is not None:
                with contextlib.suppress(Exception):
                    stream.stop()
                with contextlib.suppress(Exception):
                    stream.close()


def make_sink(config: dict[str, Any], *, dry_run: bool = False) -> NullMicSink | VirtualMicSink:
    return NullMicSink() if dry_run else VirtualMicSink(config)
