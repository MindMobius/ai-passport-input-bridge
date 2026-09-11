# 固件烧录与恢复(AI Passport / ESP32-C3)

一台全新电脑想"从零把设备恢复成可用状态",按顺序做这里的三步:备份 → 构建 → 烧录。

## 0. 前提

- 设备用 **USB 线**连电脑(ESP32-C3 原生 USB-Serial-JTAG 口,兼供电)
- Windows 侧装了本项目依赖(`install.cmd`),`esptool` 在其中
- 要**构建**固件才需要 WSL2 + ESP-IDF 5.5.x(只用现成镜像烧录则不需要)

> ⚠️ **不要在已配网的设备上跑 `idf.py erase-flash` / `erase_flash`**。
> 分区表里有出厂 `cardid`(设备身份)与 `recovery`(官方小程序恢复固件),擦掉就回不来了。

## 1. 先备份(拿到设备第一件事)

```powershell
.venv\Scripts\python.exe tools\passport_flash.py info     # 确认能连上,打印芯片与 MAC
.venv\Scripts\python.exe tools\passport_flash.py backup   # 分区表 / NVS / cardid / recovery
```

`--port` 可省略:工具会先找 USB-Serial-JTAG 的**设备接口路径**,再退回到 COM 口。
备份落在 `build/wechat/backup/`(该目录已在 `.gitignore` 里,**不要提交** —— 里面有设备唯一标识)。

## 2. 构建固件

```powershell
build-firmware.cmd
```

- 在 WSL 里跑 ESP-IDF build + `merge-bin`,产物写回 `build/wechat/`
- 需要 ESP-IDF:默认 `~/esp/esp-idf-5.5.3-jihu`,不同位置先 `set "IDF_DIR=~/esp/<你的>"` 再运行
- 脚本会自动用 `wslpath` 解析当前目录,换电脑/换盘符都不用改
- 结尾的 `verify_firmware.py` 会校验镜像与分区契约(应用必须在 `cardid` 之前结束)

产物:

| 文件 | 用途 |
|---|---|
| `build/wechat/segments/FoloToy-AI-Passport.bin` | 应用镜像,日常更新只烧它 |
| `build/wechat/segments/bootloader.bin` | 引导程序(含开机按 UP 进 Recovery 的 hook) |
| `build/wechat/segments/partition-table.bin` | 分区表 |
| `build/wechat/FoloToy-AI-Passport-full.bin` | 合并镜像(0x0 起整片烧,慎用) |

## 3. 烧录

### 只更新应用(推荐,日常迭代)

```powershell
.venv\Scripts\python.exe tools\passport_flash.py app
```

只写 `0x10000` 应用分区,**不动** bootloader / 分区表 / NVS / `cardid` / `recovery`。
写完全片 hash 校验。设备会自动重启(屏幕重绘属正常)。

### 分段烧录(bootloader 或分区表也变了才用)

```powershell
.venv\Scripts\python.exe tools\passport_flash.py flash
```

依次写 `0x0` bootloader、`0x8000` 分区表、`0x10000` 应用。写之前请确认分区表与
`partitions.csv` 一致(工具内部也会读回并校验 `factory/cardid/recovery` 三个偏移)。

## 常见坑(都踩过)

| 现象 | 原因 / 解法 |
|---|---|
| `Could not open COMx` / 端口"不存在或忙" | 该 COM 号被别的驱动(常见是蓝牙串口)占用 → **别用 COM 口**,用自动发现的设备接口路径(默认行为) |
| `Wrong boot mode detected (0xa)` | USB-Serial-JTAG 不认默认复位序列 → 工具已自动加 `--before usb-reset` |
| 设备重插后路径里 `&1&` 变 `&2&` | USB 实例号会变;工具每次重新发现,别硬编码路径 |
| `recovery partition too small` 警告 | 构建时的提示,应用实际烧在 `factory`(0x10000/3MB),可忽略 |
| 想强制进官方恢复 | 开机时**按住 UP 5 秒**,bootloader hook 会引导 `recovery` 分区 |

## 恢复出厂 / 官方恢复

- 设备自带官方小程序 Recovery 分区,开机按住 UP 5 秒进入(不要用 `erase-flash` 代替)
- 本项目固件只替换 `factory` 应用分区,随时可以用官方途径刷回去
