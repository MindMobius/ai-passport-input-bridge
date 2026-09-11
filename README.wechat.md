# AI Passport -> Windows WeChat IME bridge

> **新电脑请先看 [QUICKSTART.md](QUICKSTART.md)**(5 步,含体检脚本 `doctor.cmd`)。
> 本文件是完整参考手册,包含架构、验证证据与已知限制。

This fork turns the AI Passport into a **wireless microphone + three-button
controller** for the Windows WeChat input method.

The intended workflow is:

```text
click UP on Passport
  -> Passport microphone starts streaming 16 kHz PCM
  -> Windows bridge writes PCM to VB-CABLE "CABLE Input"
  -> bridge sends Ctrl+Win+Shift
  -> WeChat IME listens through "CABLE Output"

press any Passport key while listening
  -> bridge stops the audio stream and sends a bare Shift
  -> WeChat IME finalizes the text / clipboard

press DOWN
  -> bridge sends Ctrl+V into the focused Codex input

press OK
  -> bridge sends Enter
```

No Codex API or Codex-specific integration is required.  Codex simply receives
normal keyboard input.

## Current button mapping

| Passport key | PC action |
| --- | --- |
| UP, click | Start WeChat IME voice input |
| Any key while listening | Stop WeChat IME voice input |
| DOWN, short | `Ctrl+V` |
| DOWN, long | Clear active editor (`Ctrl+A`, `Delete`) |
| OK, short | `Enter` |
| OK, long | Passport screen lock / power-saving behavior |

`OK` first enters the READY screen from HOME; after that a short `OK` sends
Enter.

## Windows prerequisites

1. Install a virtual audio cable such as **VB-CABLE**.
2. The bridge writes to the playback endpoint named **CABLE Input**.
3. In WeChat IME, select **CABLE Output** as the microphone.  If WeChat only
   follows the system default, set CABLE Output as the default recording and
   default communication device while using the bridge.
4. Keep Codex/ChatGPT focused when pressing DOWN or OK.

The repository does not install VB-CABLE automatically.

## Install Python dependencies

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r companion\requirements-wechat.txt
```

## Configure

Copy the example:

```powershell
Copy-Item companion\wechat_config.example.json companion\wechat_config.json
```

Important fields:

```json
{
  "channel": "ble",
  "audio_device": "CABLE Input",
  "voice_hotkey": "ctrl+win",
  "paste_hotkey": "ctrl+v",
  "enter_hotkey": "enter",
  "target_title_regex": "(Codex|ChatGPT)"
}
```

If WeChat IME uses `Ctrl+Shift+Win`, set:

```json
"voice_hotkey": "ctrl+shift+win"
```

## List audio devices

```powershell
.\.venv\Scripts\python.exe companion\wechat_bridge.py --list-audio-devices
```

Look for a playback endpoint such as `CABLE Input`.

## Dry run

Dry run does not open the virtual cable and does not inject keys.  It is useful
for checking configuration and protocol wiring:

```powershell
.\.venv\Scripts\python.exe companion\wechat_bridge.py --dry-run
```

Without a connected device the bridge will time out while scanning.  With a
device it prints the virtual-mic and key action sequence.

## Run the bridge

BLE:

```powershell
.\.venv\Scripts\python.exe companion\wechat_bridge.py
```

UDP-free USB serial mode:

```powershell
.\.venv\Scripts\python.exe companion\wechat_bridge.py --channel usb
```

The USB mode requires the device to be in its USB serial mode (`mode usb`).
The bridge uses the same custom serial protocol as the upstream project; it
does not pretend that the ESP32-C3 is a USB Audio device.

## Verify the virtual cable

Run:

```powershell
test-virtual-mic.cmd
```

It writes a short 440 Hz test signal through the same `VirtualMicSink` used by
the bridge and reads it back from `CABLE Output`. A PASS means VB-CABLE is
working end to end without a Passport connected.

## Firmware

The firmware in this tree is based on:

- `FoloToy/ai-passport` hardware BSP and MIT licence
- `zhaohuaxiaoy/folo-ai-passport-voice` MIT implementation

The WeChat-specific firmware changes are:

- `APP_KEY_PASTE` was added;
- DOWN short emits `paste`;
- OK short in READY emits `enter`;
- DOWN long remains `clear`;
- the device screen hint matches the new mapping.

The partition table and bootloader now preserve the official layout:

```text
factory   0x10000 / 0x300000
cardid    0x356000 / 0x4000
recovery  0x700000 / 0x100000
```

The bootloader includes the five-second UP-hold hook that boots the
factory-installed permanent Recovery. Do not run `idf.py erase-flash` on a
provisioned device.

Build from Windows with WSL:

```powershell
build-firmware.cmd
```

The script reuses the WSL ESP-IDF checkout, builds `esp32c3`, verifies the
protected partition contract and writes:

`build\wechat\FoloToy-AI-Passport-full.bin`

For a provisioned device, prefer installing this artifact through the official
AI Passport mini-program Recovery. For development, segmented USB flashing is
safer than a raw `0x0` write because it does not erase runtime NVS. A raw
single-file write is only acceptable when the artifact ends before `cardid`.

## Local console (Windows)

`open-console.cmd` starts the local control panel (and opens it in the browser):

```text
http://127.0.0.1:8790/
```

The panel is a single-file static UI served by `companion/dashboard_server.py`; it
never talks to the network beyond `127.0.0.1`.

| Area | What it does |
| --- | --- |
| 连接配置 | USB / BLE / WiFi 通道选择、设备路径、Bridge 一键重启或停止 |
| 参数调整 | 虚拟声卡、热键、目标窗口正则、采样率/声道/超时,写回 `companion/wechat_config.json` |
| 状态监控 | 连接相位、电池、链路、丢帧、语音状态、最后按键、事件流 |
| 按键映射 | 就地编辑/录制每个手势触发的电脑按键（与“参数调整”同源，改一处两处同步） |
| 设备信息 | 设备 `device.hello` 上报的型号/MCU/Flash/显示/音频/USB ID/序列号/固件版本（落盘 `build/wechat/device.json`） |
| 设备设置 | 设备提示音档位（关闭 / 柔和 / 原始）与背光熄灭秒数（0 = 不熄屏）；保存并重连后由桥接下发，设备写 NVS，断电重启仍保留 |
| 运行日志 | Bridge 的 stdout / stderr 实时尾部 |

Device console（USB 串口 / SYS 命令面）另有两组设备侧设置，改完立即生效并写 NVS：

```
beep | beep off|soft|full      提示音档位
screen | screen <秒>|off       背光熄灭秒数（0 = 不熄屏；面板断电按 ×5 推导）
time | time set <epoch> | time tz <±hhh>
st | log [offset] | rst | reboot | factory
```

Why the default microphone keeps working:

- The Passport needs the system default recorder to be the virtual cable while
  WeChat IME is listening, but leaving it there silences the user's own headset
  mic. The bridge therefore switches the default recorder to `CABLE Output` only
  for the duration of one Passport session and restores the previous device the
  moment the session ends (`companion/win_default_mic.py`).
- The switch is crash-safe: the previous endpoints are written to
  `build/wechat/mic-saved.json` and restored on the next bridge start.
  `tools/restore-default-mic.py` performs the restore manually if needed.
- `mic_auto_switch: false` in `companion/wechat_config.json` turns the whole
  behaviour off (useful when WeChat IME is configured with its own input device).

Facts worth knowing:

- Port `8765` is already taken by 百度输入法 on this machine, so the console
  defaults to `8790` (`--port` overrides).
- `companion/open_console.py` reuses an already running server instead of
  starting a second one.
- The panel posts its own render self-check (viewport, horizontal overflow, JS
  errors) to `build/wechat/logs/dashboard-client.log`, so a broken layout leaves
  evidence instead of a silent blank page.
- WiFi is listed but not implemented: the firmware has no WiFi audio path yet.
  BLE needs a working Windows Bluetooth radio (see Known limitations).

The device screen uses the same black-line theme as the panel (`main/ui_pixel.h`
holds the shared palette); the PC console and the 240x320 panel deliberately use
one visual language.

The panel also mirrors this in the other direction: the device screen carries two
status lines (`LINK <channel> / PC <ONLINE|WAITING>` and the microphone/sink the
bridge is driving) fed by the bridge's 2s `bridge.status` heartbeat, plus a
diagnostic line on the READY page (battery mV, BLE MTU, audio/event drops). If the
bridge process dies without dropping the link, the device flips back to
`PC WAITING` on its own after 6s of silence.

## Known limitations

- VB-CABLE, a virtual audio driver, must be installed by the user.
- The `Ctrl+Win` hotkey is sent with Windows `keybd_event`; if WeChat IME
  filters synthetic input, the fallback is a BLE HID keyboard implementation.
- Windows BLE needs pairing before the protected CTRL characteristic accepts
  writes; `BleakTransport` pairs automatically on connect (`_ensure_encrypted_link`).
- The default recording device is switched to `CABLE Output` **only for the
  duration of a voice session** and restored right after (`mic_auto_switch`).
- The firmware has not been flashed to a real Passport in this workspace.
- BLE audio quality is 16 kHz mono PCM; it is optimized for speech, not music.
- Windows 10/11 only for the bridge UI/injection path.

## Source layout

- `companion/wechat_bridge.py` - bridge entry point
- `companion/virtual_mic.py` - VB-CABLE output and PCM resampling
- `companion/keyinject_win.py` - Ctrl+Win / Ctrl+V / Enter injection
- `companion/virtual_asr.py` - adapts audio frames to the existing relay
- `companion/wechat_bridge_config.py` - configuration
- `main/` - ESP-IDF firmware
- `tests/` - upstream host tests
