import asyncio
import json
import sys
from pathlib import Path

import pytest

COMPANION = Path(__file__).resolve().parents[1]
if str(COMPANION) not in sys.path:
    sys.path.insert(0, str(COMPANION))

from keyinject_win import KeyInjectError, parse_combo, parse_sequence  # noqa: E402
from relay import AUDIO_UUID, EVENT_UUID, CTRL_UUID, Relay  # noqa: E402
from virtual_asr import VirtualMicSession  # noqa: E402
from virtual_mic import NullMicSink, resample_pcm16_mono  # noqa: E402
from wechat_bridge_config import DEFAULTS  # noqa: E402


def test_resample_16k_mono_to_48k_stereo():
    pcm = b"\x00\x10" * 1600  # 1600 samples = 100 ms @ 16 kHz
    out = resample_pcm16_mono(pcm, 16000, 48000, 2)
    assert len(out) == 4800 * 2 * 2


def test_key_parsing():
    assert parse_combo("ctrl+win") == [0x11, 0x5B]
    assert parse_sequence("ctrl+a,delete") == [[0x11, 0x41], [0x2E]]
    with pytest.raises(KeyInjectError):
        parse_combo("ctrl+does-not-exist")


def test_virtual_mic_session_brackets_audio():
    sink = NullMicSink()
    keys = _FakeKeys()

    async def scenario():
        session = VirtualMicSession(sink, keys, DICT)
        await session.connect()
        await session.send_frame(b"\x01\x02" * 1600)
        await session.send_end()
        results = [item async for item in session.results()]
        await session.close()
        return results

    results = asyncio.run(scenario())
    assert results == [("", True)]
    assert keys.events == ["voice_start", "voice_stop"]
    assert sink.frames == 1
    assert sink.bytes_written == 3200
    assert sink.closed is True


class _FakeKeys:
    def __init__(self):
        self.events = []

    def voice_start(self):
        self.events.append("voice_start")

    def voice_stop(self):
        self.events.append("voice_stop")

    def voice_toggle(self):
        self.voice_start()

    def key_action(self, action):
        self.events.append(action)


class _FakeTransport:
    def __init__(self):
        self.handlers = {}
        self.writes = []
        self.disconnected = False

    async def scan_for_device(self, name, timeout):
        return "fake-device"

    async def connect(self, address, on_disconnect=None):
        self.address = address
        self.on_disconnect = on_disconnect

    async def start_notify(self, uuid, handler):
        self.handlers[uuid] = handler

    async def write_gatt_char(self, uuid, payload):
        self.writes.append((uuid, bytes(payload)))

    async def disconnect(self):
        self.disconnected = True

    def event(self, obj):
        self.handlers[EVENT_UUID]((json.dumps(obj, ensure_ascii=False) + "\n").encode())

    def audio(self, payload):
        self.handlers[AUDIO_UUID](payload)


DICT = dict(DEFAULTS)
DICT["target_title_regex"] = ""


def test_relay_event_flow_to_virtual_mic_and_keys():
    transport = _FakeTransport()
    sink = NullMicSink()
    keys = _FakeKeys()
    relay = Relay(
        transport=transport,
        asr_factory=lambda: VirtualMicSession(sink, keys, DICT),
        inject_fn=lambda _text: None,
        key_action_fn=keys.key_action,
        timeout=1.0,
        do_inject=False,
        do_approval=False,
    )

    async def scenario():
        task = asyncio.create_task(relay.run("fake-device", console_stdin=False))
        for _ in range(200):
            if EVENT_UUID in transport.handlers and AUDIO_UUID in transport.handlers:
                break
            await asyncio.sleep(0.01)
        assert EVENT_UUID in transport.handlers
        assert AUDIO_UUID in transport.handlers

        transport.event({"event": "voice.start", "audio": "pcm"})
        await asyncio.sleep(0.05)
        transport.audio(b"\x00\x00" * 1600)
        await asyncio.sleep(0.05)
        transport.event({"event": "voice.end"})
        await asyncio.sleep(0.35)
        transport.event({"event": "key.action", "action": "paste"})
        transport.event({"event": "key.action", "action": "enter"})
        await asyncio.sleep(0.15)

        relay._handle_disconnect()
        await asyncio.wait_for(task, 2.0)

    asyncio.run(scenario())
    assert keys.events == ["voice_start", "voice_stop", "paste", "enter"]
    assert sink.frames == 1
    assert transport.disconnected is True
