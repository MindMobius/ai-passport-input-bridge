# ai-passport-input-bridge

把 **FoloToy AI Passport** 变成桌面上的**语音输入遥控器 + 无线麦克风**:设备负责采集和按键,
电脑负责把音频送进虚拟声卡、并把按键翻译成目标输入法/应用的快捷键。

```text
按一下 UP          Passport 开始推流(USB 或 BLE)
                   电脑把它们写进虚拟声卡 CABLE Input
                   电脑按下启动语音快捷键(默认 Ctrl+Win+Shift)
说话               目标输入法从 CABLE Output 听到声音,自己转写并落字
按任意键           电脑停流 + 送结束键(默认 Shift),输入法定稿/复制
按 DOWN            粘贴(Ctrl+V)
按 OK              回车发送
```

设备端只负责麦克风 + 三个键 + 屏幕;所有和系统/输入法对接的事都在电脑侧,所以**电脑端必须运行**。

## 快速开始

新电脑 + 已刷固件的设备,看 **[QUICKSTART.md](QUICKSTART.md)**(4 步一次性 + 4 步日常)。
体检用 `doctor.cmd`,控制台用 `open-console.cmd`。

## 各部分在哪

| 部分 | 位置 | 说明 |
|---|---|---|
| 固件 | `main/` `components/` `bootloader_components/` `partitions.csv` | ESP32-C3:ES8311 音频、ST7789 屏幕、BLE + USB 双通道常开、Recovery 分区保留 |
| 电脑桥接 | `companion/` | USB/BLE 收流 → 虚拟声卡;热键/剪贴板注入;会话内临时切默认麦克风 |
| 本地控制台 | `companion/dashboard/` + `dashboard_server.py` | 纯黑线条风配置页:连接配置 / 参数 / 状态 / 按键映射 / 日志 |
| 工具 | `tools/` | 构建、烧录、校验、体检、虚拟声卡回环测试 |
| 固件主机测试 | `tests/` | 状态机/协议/音频/USB 链路的 x86 host 测试(不依赖硬件) |
| 硬件实测记录 | `docs/` | 硬件调试、性能/内存复核、代码审查记录 |

## 已验证 / 未验证

**已实测**:固件可编译并通过 `tools/verify_firmware.py` 校验;应用分区可烧录且不动
`cardid`/`recovery`/NVS/分区表;USB 全流程(音频回环 + 粘贴/回车注入);Windows BLE 配对、
连接、断线自愈;会话内默认麦克风切换与还原;控制台配置读写与启停。

**未实测**:BLE 音频端到端(ADPCM 解码后真实转写)在 Windows 上还没跑过真人语音;
`companion/tests/` 有一批测试按 macOS 路径写的(`os.openpty`、`pytest-asyncio`),Windows 上会失败。

## 命名与后续

仓库名已经是通用的 `input-bridge`(任何自带语音输入的输入法/听写工具都能当目标),但内部模块名
仍有历史包袱(`wechat_bridge.py` / `wechat_config.json` / `doctor_wechat.py`),默认值也偏微信输入法。
后续计划:抽 `profiles/`(wechat-ime / windows-voice / …)+ 模块改名 `bridge_*`,旧名留兼容 shim。

## 烧录 / 恢复

换设备或重刷固件看 **[docs/FLASHING.md](docs/FLASHING.md)**:备份 → 构建 → 只烧应用分区
(`tools/passport_flash.py app`,不动 cardid/recovery/NVS/分区表)。

## 许可与致谢

MIT。来源于:

- [FoloToy/ai-passport](https://github.com/FoloToy/ai-passport) —— 硬件 BSP 与原始固件(MIT)
- [zhaohuaxiaoy/folo-ai-passport-voice](https://github.com/zhaohuaxiaoy/folo-ai-passport-voice) —— 语音链路实现(MIT)
- [ihonghong/ai-passport-macos-voice-remote](https://github.com/ihonghong/ai-passport-macos-voice-remote) —— macOS 版虚拟麦克风思路参考

详见 [LICENSE](LICENSE);Windows 侧完整参考手册在 [README.wechat.md](README.wechat.md)。
