// main/nvs_settings.h —— 持久化设置(NVS 命名空间 "app")。
#pragma once

#include "esp_err.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t nvs_settings_init(void);

// 注:rf_mode 键已随双通道常开架构退役(2026-08-28,不再有互斥模式),
// get/set_mode 已删除;旧键残留 NVS 无读取方,无害。

// 时区偏移小时(int8,±12;缺省 8)
esp_err_t nvs_settings_get_tz_hour(int8_t *hour);
esp_err_t nvs_settings_set_tz_hour(int8_t hour);

// 最近一次已知的 wall-clock(UTC 秒;0 = 从未存过)。
// 设备没有 RTC 电池:复位/断电即失时,靠它把"上次知道的时间"兜回来,
// 电脑端下一次连接再校正(见 time_sync.c)。
esp_err_t nvs_settings_get_last_epoch(int64_t *epoch);
esp_err_t nvs_settings_set_last_epoch(int64_t epoch);

// 设备设置(电脑端控制台可改,见 app_types.h 的 app_beep_t):
//   beep_level   提示音档位(0=off / 1=soft / 2=full;缺省 1)
//   screen_off_s 背光熄灭秒数(0 = 不熄屏;缺省 120)
esp_err_t nvs_settings_get_beep_level(uint8_t *level);
esp_err_t nvs_settings_set_beep_level(uint8_t level);
esp_err_t nvs_settings_get_screen_off_s(uint16_t *seconds);
esp_err_t nvs_settings_set_screen_off_s(uint16_t seconds);

void nvs_settings_factory_reset(void);   // 清 "app" 命名空间

#ifdef __cplusplus
}
#endif
