// main/nvs_settings.c —— 设置存储实现。
#include "nvs_settings.h"
#include "app_types.h"   // APP_BEEP_FULL(档位上限校验)
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"
#include <string.h>

static const char *TAG = "settings";
#define APP_NS "app"

// 注:rf_mode 键已随双通道常开架构退役(2026-08-28,不再有互斥模式);旧键
// 残留于 NVS 无读取方,无害(factory 清空可除)。
static const char *K_TZ_HOUR   = "tz_hour";
static const char *K_LAST_EPOCH = "last_epoch";
static const char *K_BEEP_LEVEL = "beep_level";
static const char *K_SCREEN_OFF_S = "screen_off_s";

// 缺省设备设置:提示音"柔和"、背光 2 分钟(桌面场景 20s 太短,2026-09-11 反馈)
#define BEEP_LEVEL_DEFAULT   1
#define SCREEN_OFF_S_DEFAULT 120

esp_err_t nvs_settings_init(void) {
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READWRITE, &h);
    if (e == ESP_OK) nvs_close(h);
    return e;
}

// 时区偏移小时(int8 支持负偏移,±12);缺省 8(Asia/Shanghai)
esp_err_t nvs_settings_get_tz_hour(int8_t *hour) {
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READONLY, &h);
    if (e != ESP_OK) { if (hour) *hour = 8; return ESP_OK; }   // 打不开按默认兜底
    int8_t v = 8;
    e = nvs_get_i8(h, K_TZ_HOUR, &v);
    nvs_close(h);
    if (e == ESP_ERR_NVS_NOT_FOUND) v = 8;   // 首次使用:默认 +8
    if (hour) *hour = (v >= -12 && v <= 12) ? v : 8;   // 损坏值兜底
    return ESP_OK;
}

esp_err_t nvs_settings_set_tz_hour(int8_t hour) {
    if (hour < -12 || hour > 12) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READWRITE, &h);
    if (e != ESP_OK) return e;
    e = nvs_set_i8(h, K_TZ_HOUR, hour);
    if (e == ESP_OK) e = nvs_commit(h);
    nvs_close(h);
    ESP_LOGI(TAG, "tz_hour = %d", (int)hour);
    return e;
}

// 最近一次已知时间(UTC 秒)。读失败/缺省一律回 0,调用方按"没有存档"处理。
esp_err_t nvs_settings_get_last_epoch(int64_t *epoch) {
    if (epoch) *epoch = 0;
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READONLY, &h);
    if (e != ESP_OK) return ESP_OK;              // 命名空间还没建:当作没有存档
    int64_t v = 0;
    e = nvs_get_i64(h, K_LAST_EPOCH, &v);
    nvs_close(h);
    if (e == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    if (e != ESP_OK) return e;
    if (epoch) *epoch = v;
    return ESP_OK;
}

esp_err_t nvs_settings_set_last_epoch(int64_t epoch) {
    if (epoch <= 0) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READWRITE, &h);
    if (e != ESP_OK) return e;
    e = nvs_set_i64(h, K_LAST_EPOCH, epoch);
    if (e == ESP_OK) e = nvs_commit(h);
    nvs_close(h);
    return e;
}

// ---- 设备设置(提示音档位 / 息屏秒数)----
// 读失败/缺省一律回默认值,不把"没存过"当错误(首次开机的正常路径)。
esp_err_t nvs_settings_get_beep_level(uint8_t *level) {
    if (level) *level = BEEP_LEVEL_DEFAULT;
    nvs_handle_t h;
    if (nvs_open(APP_NS, NVS_READONLY, &h) != ESP_OK) return ESP_OK;
    uint8_t v = BEEP_LEVEL_DEFAULT;
    esp_err_t e = nvs_get_u8(h, K_BEEP_LEVEL, &v);
    nvs_close(h);
    if (e == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    if (e != ESP_OK) return e;
    if (v > APP_BEEP_FULL) v = BEEP_LEVEL_DEFAULT;   // 损坏值兜底
    if (level) *level = v;
    return ESP_OK;
}

esp_err_t nvs_settings_set_beep_level(uint8_t level) {
    if (level > APP_BEEP_FULL) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READWRITE, &h);
    if (e != ESP_OK) return e;
    e = nvs_set_u8(h, K_BEEP_LEVEL, level);
    if (e == ESP_OK) e = nvs_commit(h);
    nvs_close(h);
    return e;
}

esp_err_t nvs_settings_get_screen_off_s(uint16_t *seconds) {
    if (seconds) *seconds = SCREEN_OFF_S_DEFAULT;
    nvs_handle_t h;
    if (nvs_open(APP_NS, NVS_READONLY, &h) != ESP_OK) return ESP_OK;
    uint16_t v = SCREEN_OFF_S_DEFAULT;
    esp_err_t e = nvs_get_u16(h, K_SCREEN_OFF_S, &v);
    nvs_close(h);
    if (e == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    if (e != ESP_OK) return e;
    if (seconds) *seconds = v;   // 0 合法 = 不熄屏
    return ESP_OK;
}

esp_err_t nvs_settings_set_screen_off_s(uint16_t seconds) {
    nvs_handle_t h;
    esp_err_t e = nvs_open(APP_NS, NVS_READWRITE, &h);
    if (e != ESP_OK) return e;
    e = nvs_set_u16(h, K_SCREEN_OFF_S, seconds);
    if (e == ESP_OK) e = nvs_commit(h);
    nvs_close(h);
    return e;
}

void nvs_settings_factory_reset(void) {
    nvs_handle_t h;
    if (nvs_open(APP_NS, NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
        ESP_LOGW(TAG, "app 命名空间已清空");
    }
}
