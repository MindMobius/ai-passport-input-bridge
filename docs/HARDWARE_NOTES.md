# 硬件实测记录 / 坑位清单

跨机器复现过的硬件事实,避免重复排查。

## B&O Beoplay A1:USB 音频只出静音,麦克风要走蓝牙

**现象**(2026-09-12 实测,Windows 11):

- A1 用 **USB** 接到电脑时,会枚举出一个 USB 音频设备(`USB\VID_0CD4&PID_1004`,
  复合设备:MI_00=USB Audio、MI_03=厂商自定义 HID)。
  它的**播放正常**(播测试音能听到),但**采集通路恒为数字静音**:
  - 峰值 `0~9 / 32767`,任何采样率、任何 host API(MME/DirectSound/WASAPI/WDM-KS)都一样
  - **WASAPI 独占模式**(绕过全部音效/APO)同样静音
  - 采集流**准时且无丢包**:5 秒 50 个块(100ms/块)、`overflow=0` → 设备是在"正常地发送全零数据包"
- 换成 **蓝牙 HFP** 连接(Windows 里显示为 `耳机式麦克风 (2- Beplay A1)`,
  设备树 `BTHHFENUM\BTHHFPAUDIO`)→ **麦克风立刻正常**

**判定结论**:A1 的**麦克风本体与蓝牙通路是好的**,是它的 **USB 音频采集实现/固件**不产生麦克风数据
(USB 采集端点是"空壳")。与电脑、驱动、Windows 更新、本项目代码均无关。

**排查时已排除的因素**(都可复现):

| 疑点 | 实测结果 |
|---|---|
| Windows 输入音量被调低 / 静音 | `master volume = 100% (0.00 dB)`、`mute = False`、单声道 ch0=100% |
| 驱动异常 | `usbaudio`(wdma_usb.inf),Status=Started,无故障码 |
| 别的程序占用麦克风 | WASAPI 独占模式能打开 → 没有任何进程(含共享)占用 |
| 系统级麦克风静音 | 虚拟声卡回环 `CABLE Input → CABLE Output` 正常(peak=15015) |
| 音效/增强(APO) | 独占模式绕过音效后仍静音 |
| 重启电脑 / 设备重枚举 | 无效(采集流本来就准时无丢包) |

**建议做法**:

- **麦克风用蓝牙**:配对 A1 后把默认输入设为 `耳机式麦克风 (2- Beplay A1)`;
- **不要用电脑的 USB 口给 A1 供电**(用充电头):一旦插到电脑,Windows 就会多出那条
  "看着正常、实际全零"的 USB 麦克风,可能被应用或默认设备选中;
- 必须插电脑时,可在 设备管理器 → 音频输入和输出 → `耳机式麦克风 (Beplay A1)`(USB 那条)
  → **禁用**,只保留蓝牙那条。

**用本项目工具复现**:

```powershell
.venv\Scripts\python.exe tools\mic-level-test.py --device "A1" --seconds 6
```
(USB 连接时会是"基本静音";蓝牙连接时应能测到明显峰值)

## ⚠️ 更正(2026-09-12 稍后)

上面这段结论**被我写得太强了**,需要修正:

- 用户反馈**此前长期是用 USB 使用 A1 麦克风的**,所以"USB 采集永远是空壳"不成立。
- 当时测到的"全零"只是**那一个状态下**的事实;之后同一台设备的 **USB 复合父节点
  被发现处于"已禁用"状态**(`ProblemCode = 22 / CM_PROB_DISABLED`),子设备(MI_00 音频 /
  MI_03 HID)随之消失 —— 也就是说:**当前连 USB 麦克风通路都不存在,谈不上静音**。
- 该禁用状态**很可能是本项目 `reset-mic.cmd` 的早期版本造成的**:它先 `Disable-PnpDevice`
  再 `Enable-PnpDevice`,却没有"无论如何都启用回来"的兜底。脚本已改为安全版
  (检测到已禁用只做启用;结束前强制确保启用;新增 `-EnableOnly`)。

**正确的复测方法**(需要在 USB 通路可用且不与其他通路抢麦克风时做):

1. 先确保设备是启用状态:
   ```powershell
   pnputil /enable-device "USB\VID_0CD4&PID_1004\ABCDEF0123456789"   # 管理员
   ```
2. **断开 A1 的蓝牙**(Windows 蓝牙里断开/删除设备;同时确认手机等其它主机没连着它)
3. 只插 USB,跑:
   ```powershell
   .venv\Scripts\python.exe tools\mic-level-test.py --device "耳机式麦克风 (Beplay A1)" --seconds 6
   ```
4. 再对比"BT 同时连着"的情况 —— 用来判定 A1 是否**同一时间只把麦克风交给一条通路**
   (即 BT 占用时 USB 采集会是静音),这才是目前最可能的解释。
