// time_sync 宿主测试:format_local 纯函数(时区偏移/跨日/未校时/零填充/负 epoch)
// + tz 边界 + NVS 桩重启恢复。宿主编译 time_sync.c(ESP_PLATFORM 未定义,
// settimeofday 不编译,零系统时间副作用);NVS 由本文件桩替代。
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "time_sync.h"
#include "nvs_settings.h"

// ---- NVS 桩(宿主无 ESP-IDF NVS:时区持久化走静态变量)----
static int8_t g_fake_tz = 8;
static int64_t g_fake_epoch = 0;
esp_err_t nvs_settings_get_tz_hour(int8_t *hour) { *hour = g_fake_tz; return ESP_OK; }
esp_err_t nvs_settings_set_tz_hour(int8_t hour) { g_fake_tz = hour; return ESP_OK; }
esp_err_t nvs_settings_get_last_epoch(int64_t *epoch) { if (epoch) *epoch = g_fake_epoch; return ESP_OK; }
esp_err_t nvs_settings_set_last_epoch(int64_t epoch) {
    if (epoch <= 0) return ESP_ERR_INVALID_ARG;
    g_fake_epoch = epoch;
    return ESP_OK;
}

// 2026-01-01 00:00:00 UTC(确定性基准,避免依赖 libc 相对时间)
#define EPOCH_2026_0101 1767225600LL

static void test_unset(void) {
    time_sync_init();
    char buf[16];
    assert(!time_sync_valid());
    int n = time_sync_format_local(buf, sizeof(buf));
    assert(n == 5 && strcmp(buf, "--:--") == 0);
}

static void test_tz_default8(void) {
    time_sync_init();
    assert(time_sync_tz_hour() == 8);
    time_sync_set_epoch(EPOCH_2026_0101);          // 00:00 UTC → +8 = 08:00
    char buf[16];
    assert(time_sync_valid());
    assert(time_sync_format_local(buf, sizeof(buf)) == 5);
    assert(strcmp(buf, "08:00") == 0);
}

static void test_tz_switch(void) {
    time_sync_init();
    time_sync_set_epoch(EPOCH_2026_0101);
    char buf[16];
    assert(time_sync_set_tz(0) == ESP_OK);
    assert(time_sync_format_local(buf, sizeof(buf)) == 5 && strcmp(buf, "00:00") == 0);
    assert(time_sync_set_tz(-8) == ESP_OK);
    // -8:2026-01-01 00:00 UTC → 2025-12-31 16:00(跨日由 gmtime_r 自动处理)
    assert(time_sync_format_local(buf, sizeof(buf)) == 5 && strcmp(buf, "16:00") == 0);
}

static void test_zero_pad(void) {
    time_sync_init();
    time_sync_set_tz(0);
    time_sync_set_epoch(EPOCH_2026_0101 + 5LL * 3600);   // 05:00 UTC
    char buf[16];
    assert(time_sync_format_local(buf, sizeof(buf)) == 5 && strcmp(buf, "05:00") == 0);
}

static void test_negative_epoch(void) {
    time_sync_init();
    time_sync_set_tz(0);
    time_sync_set_epoch(-1);                             // 1969-12-31 23:59:59 UTC
    char buf[16];
    assert(time_sync_format_local(buf, sizeof(buf)) == 5 && strcmp(buf, "23:59") == 0);
}

static void test_tz_bounds(void) {
    time_sync_init();
    assert(time_sync_set_tz(12) == ESP_OK && time_sync_tz_hour() == 12);
    assert(time_sync_set_tz(-12) == ESP_OK && time_sync_tz_hour() == -12);
    // 越界拒绝且不改变现值
    assert(time_sync_set_tz(13) != ESP_OK && time_sync_tz_hour() == -12);
    assert(time_sync_set_tz(-13) != ESP_OK && time_sync_tz_hour() == -12);
}

static void test_tz_persist_across_init(void) {
    // 模拟:set_tz 写 NVS(桩)→ 重启(init 重读)→ 时区保持。
    // 校时值本身是否跨重启,交给 test_epoch_persist_across_restart(2026-09-11
    // 起:会跨,设备没有 RTC 电池,靠 NVS 兜底)。
    time_sync_init();
    assert(time_sync_set_tz(-5) == ESP_OK);
    time_sync_init();                                    // 重新 init 模拟重启
    assert(time_sync_tz_hour() == -5);
}

// 时钟持久化:设备没有 RTC 电池,复位/断电后要能把"上次知道的时间"兜回来
// (USB 口一关就复位设备是实测行为,见 time_sync.c 注释)。
static void test_epoch_persist_across_restart(void) {
    time_sync_init();
    assert(time_sync_set_tz(8) == ESP_OK);               // 固定时区,避免受前序用例影响
    g_fake_epoch = 0;                                    // 全新设备:没有存档
    time_sync_init();
    assert(!time_sync_valid());                          // → "--:--"
    assert(!time_sync_is_fresh());

    time_sync_set_epoch(EPOCH_2026_0101);                // 电脑端校时
    assert(time_sync_is_fresh());                        // 本次开机校过 = 准点
    time_sync_persist();                                 // 落 NVS(宿主用 s_epoch 基线)
    assert(g_fake_epoch == EPOCH_2026_0101);

    time_sync_init();                                    // 复位重启
    assert(time_sync_valid());                           // 旧时间可用(不再 --:--)
    assert(!time_sync_is_fresh());                       // 但标记为"非本次校时"(UI 弱化)
    char buf[16];
    assert(time_sync_format_local(buf, sizeof(buf)) == 5 && strcmp(buf, "08:00") == 0);

    // 存档是垃圾值(0 / 1970 附近)时不冒充时间:仍然 "--:--"
    g_fake_epoch = 1;
    time_sync_init();
    assert(!time_sync_valid());
    // 未校时不得写盘:避免把垃圾值固化
    time_sync_persist();
    assert(g_fake_epoch == 1);
}

int main(void) {
    test_unset();
    test_tz_default8();
    test_tz_switch();
    test_zero_pad();
    test_negative_epoch();
    test_tz_bounds();
    test_tz_persist_across_init();
    test_epoch_persist_across_restart();
    printf("time_sync: all tests passed\n");
    return 0;
}
