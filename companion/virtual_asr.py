#!/usr/bin/env python3
"""ASR-shaped adapter used by relay.py.

The original relay expects an object with connect/send_frame/send_end/results/
close.  This adapter replaces the cloud ASR with a virtual microphone: each
PCM frame is written to the configured virtual-cable output, while the voice
hotkey brackets the WeChat IME listening session.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from win_default_mic import make_switcher


class VirtualMicSession:
    def __init__(self, sink: Any, keys: Any, config: dict[str, Any], on_event=None) -> None:
        self.sink = sink
        self.keys = keys
        self.config = config
        self.on_event = on_event
        # 只管 Passport 会话期间的默认录音设备:用完立刻还给用户原本的麦克风
        self.mic_switcher = make_switcher(config)
        self._final = asyncio.Event()
        self._closed = False
        self._started = False
        self._ended = False
        self._lock = asyncio.Lock()

    def _event(self, kind: str, **fields) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, **fields)
            except Exception:
                pass

    async def connect(self) -> None:
        async with self._lock:
            if self._closed:
                raise RuntimeError("virtual microphone session is closed")
            if self._started:
                return
            self._started = True
        # Open the virtual cable first; then trigger the IME.  The Passport
        # sends its first PCM frame after its start tone, so ordering matters.
        await asyncio.to_thread(self.sink.start)
        # 先切默认麦克风再按热键:微信输入法在收到热键那一刻就开始采集,
        # 顺序反了会录到用户自己的麦克风(或录到静音)。
        if self.mic_switcher.available:
            await asyncio.to_thread(self.mic_switcher.use_virtual)
        start_key = getattr(self.keys, "voice_start", self.keys.voice_toggle)
        await asyncio.to_thread(start_key)
        print("[session] voice start: virtual mic opened, WeChat hotkey sent")
        self._event("voice_start")

    async def send_frame(self, pcm: bytes) -> None:
        if self._ended or self._closed:
            return
        await asyncio.to_thread(self.sink.write, pcm)

    async def send_end(self) -> None:
        if self._ended:
            return
        self._ended = True
        await asyncio.to_thread(self.sink.finish)
        stop_key = getattr(self.keys, "voice_stop", None)
        if stop_key is not None:
            await asyncio.to_thread(stop_key)
        # IME 停采后再还原,避免尾巴录进用户麦克风
        if self.mic_switcher.available:
            await asyncio.to_thread(self.mic_switcher.restore)
        print("[session] voice end: virtual microphone stopped, stop key sent")
        self._event("voice_end")
        self._final.set()

    async def results(self) -> AsyncIterator[tuple[str, bool]]:
        await self._final.wait()
        # Empty final text tells relay.py there is no transcript to inject;
        # WeChat IME owns the recognition and clipboard step.
        yield "", True

    async def close(self) -> None:
        self._closed = True
        # 会话异常结束(ASR 失败/断链)也必须还原默认麦克风 —— 否则用户的
        # 麦克风会一直指向虚拟声卡(2026-09-11 真实事故:会话报错后没还原)。
        if self.mic_switcher.available:
            try:
                await asyncio.to_thread(self.mic_switcher.restore)
            except Exception:
                pass
        if self._started and not self._ended:
            # Abort/daemon shutdown path: do not leave the IME listening.
            try:
                stop_key = getattr(self.keys, "voice_stop", None)
                if stop_key is not None:
                    await asyncio.to_thread(stop_key)
            except Exception as exc:
                print(f"[session] 结束残留语音状态失败: {exc}")
        try:
            await asyncio.to_thread(self.sink.close)
        except Exception as exc:
            print(f"[session] 关闭虚拟麦克风失败: {exc}")
