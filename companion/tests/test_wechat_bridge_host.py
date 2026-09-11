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
from wechat_bridge import (  # noqa: E402
    build_device_info,
    client_status_payload,
    write_device_info,
)


def test_device_info_from_hello(tmp_path):
    """device.hello → 设备信息:设备上报字段照抄,缺字段留空(不编造)。"""
    ev = {"event": "device.hello", "proto": 2, "chip": "ESP32-C3 r1.1",
          "flash_mb": 8, "mac": "4C:11:AE:32:F1:4A", "fw": "v2026.09.11", "idf": "v5.5.3"}
    info = build_device_info(ev, {"channel": "usb"})
    assert info["mcu"] == "ESP32-C3 r1.1"
    assert info["flash"] == "8 MB"
    assert info["mac"] == "4C:11:AE:32:F1:4A"
    assert info["fw"] == "v2026.09.11"
    assert info["model"]  # 档案里的硬件事实仍在
    assert "fw=v2026.09.11" in info["source"]

    # 旧固件只有 proto:不写假值,面板按 "--" 渲染
    old = build_device_info({"event": "device.hello", "proto": 1}, {"channel": "ble"})
    assert old["mcu"] == "" and old["mac"] == "" and old["flash"] == ""

    # 落盘是原子替换 + 合法 JSON
    path = tmp_path / "device.json"
    written = write_device_info(path, ev, {"channel": "usb"})
    assert json.loads(path.read_text(encoding="utf-8")) == written
    assert not (tmp_path / "device.json.tmp").exists()


def test_client_status_payload_respects_mic_auto():
    on = client_status_payload({"audio_device": "CABLE Input", "mic_auto_switch": True,
                                "mic_switch_target": "CABLE Output"})
    assert on["auto"] is True and on["mic"] == "CABLE Output" and on["sink"] == "CABLE Input"
    assert on["host"]  # 主机名非空,设备屏幕用它显示"谁在连"
    off = client_status_payload({"audio_device": "CABLE Input", "mic_auto_switch": False,
                                 "mic_switch_target": "CABLE Output"})
    assert off["auto"] is False and off["mic"] == ""   # 显示 MIC AUTO OFF,不谎报切换目标


def test_client_status_payload_truncates_for_screen():
    """设备端字段上限 24B(含 NUL):超长名必须在此截断,不能靠设备丢字段。"""
    payload = client_status_payload({"audio_device": "X" * 80, "mic_auto_switch": True,
                                     "mic_switch_target": "Y" * 80})
    assert len(payload["sink"]) <= 23 and len(payload["mic"]) <= 23


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
