// main/dev_info.c —— 设备身份采集实现(IDF 侧)。
// 用途:device.hello 上报固件版本/芯片/Flash/MAC,电脑端控制台据此填"设备信息"
// 面板(此前该面板读 build/wechat/device.json,而没有任何代码写它 → 恒为 "--")。
// 全部取值都是廉价只读调用,缓存一次即可;失败留空,不上报假值。
#include "dev_info.h"
#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_log.h"
#include <stdio.h>
#include <string.h>

static const char *TAG = "dev_info";

static app_dev_info_t s_info;
static bool s_ready;

// 有界拷贝:源(如 esp_app_desc.version[32])可能比目标长,用 snprintf("%s")
// 会被 -Werror=format-truncation 判为潜在截断 —— 显式截断 + 保证 NUL 更清楚。
static void copy_str(char *dst, size_t cap, const char *src)
{
    if (!dst || cap == 0) return;
    if (!src) { dst[0] = '\0'; return; }
    size_t n = strlen(src);
    if (n >= cap) n = cap - 1;
    memcpy(dst, src, n);
    dst[n] = '\0';
}

static void fill(void) {
    memset(&s_info, 0, sizeof(s_info));

    const esp_app_desc_t *app = esp_app_get_description();
    if (app) {
        copy_str(s_info.fw, sizeof(s_info.fw), app->version);
    }
    copy_str(s_info.idf, sizeof(s_info.idf), esp_get_idf_version());

    esp_chip_info_t chip;
    memset(&chip, 0, sizeof(chip));
    esp_chip_info(&chip);
    char model[12];
    switch (chip.model) {
    case CHIP_ESP32:   copy_str(model, sizeof(model), "ESP32");    break;
    case CHIP_ESP32S2: copy_str(model, sizeof(model), "ESP32-S2"); break;
    case CHIP_ESP32S3: copy_str(model, sizeof(model), "ESP32-S3"); break;
    case CHIP_ESP32C3: copy_str(model, sizeof(model), "ESP32-C3"); break;
    case CHIP_ESP32C2: copy_str(model, sizeof(model), "ESP32-C2"); break;
    case CHIP_ESP32C6: copy_str(model, sizeof(model), "ESP32-C6"); break;
    case CHIP_ESP32H2: copy_str(model, sizeof(model), "ESP32-H2"); break;
    default:           copy_str(model, sizeof(model), "unknown");  break;
    }
    // IDF 5.x 起 chip.revision 用 major*100+minor(真机 v1.1 = 101);
    // 旧编号(<100,如 v0.3 = 3)保持原样,避免打印出 "r101" 这种不可读版本号。
    if (chip.revision >= 100) {
        snprintf(s_info.chip, sizeof(s_info.chip), "%s r%d.%d", model,
                 chip.revision / 100, chip.revision % 100);
    } else {
        snprintf(s_info.chip, sizeof(s_info.chip), "%s r%d", model, chip.revision);
    }

    uint32_t flash_size = 0;
    if (esp_flash_get_size(NULL, &flash_size) == ESP_OK && flash_size > 0) {
        s_info.flash_mb = (int)(flash_size / (1024u * 1024u));
    }

    uint8_t mac[6] = {0};
    if (esp_read_mac(mac, ESP_MAC_BT) == ESP_OK) {
        snprintf(s_info.mac, sizeof(s_info.mac), "%02X:%02X:%02X:%02X:%02X:%02X",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }

    s_ready = true;
    ESP_LOGI(TAG, "fw=%s idf=%s chip=%s flash=%dMB mac=%s",
             s_info.fw, s_info.idf, s_info.chip, s_info.flash_mb, s_info.mac);
}

const app_dev_info_t *dev_info_get(void) {
    if (!s_ready) {
        fill();          // 单核 main 任务上下文调用,无并发窗口;重复调用只填一次
    }
    return &s_info;
}
