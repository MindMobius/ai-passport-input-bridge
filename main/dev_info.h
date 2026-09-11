// main/dev_info.h —— 设备身份(固件版本/芯片/Flash/MAC)。
// 只有 IDF 侧实现(dev_info.c);协议层 app_protocol.c 只消费纯数据结构,
// 因此本头文件不进宿主机测试的编译单元。
#pragma once

#include "app_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

// 首次调用时采集(esp_app_desc/芯片/Flash/MAC),此后返回同一份只读快照。
// 永不返回 NULL;任一字段取不到就是空串/0,调用方按"未知"处理。
const app_dev_info_t *dev_info_get(void);

#ifdef __cplusplus
}
#endif
