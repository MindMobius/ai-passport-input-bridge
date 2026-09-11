#pragma once

#include "lvgl.h"

/* 黑白线稿色板:纯黑底 + 细线 + 暖橙强调。
 * 与电脑端控制台(companion/dashboard/styles.css)共用同一套视觉语言。 */
#define UI_BG          0x050505   /* 页面底色 */
#define UI_PANEL       0x0B0B0B   /* 面板/浮层底色 */
#define UI_LINE        0x202020   /* 分隔细线 */
#define UI_LINE_BRIGHT 0x3A3A3A   /* 描边细线 */
#define UI_TEXT        0xF2F2F2   /* 主文字 */
#define UI_MUTED       0x8A8A8A   /* 次级文字 */
#define UI_DIM         0x5A5A5A   /* 提示文字 */
#define UI_ACCENT      0xFF8A3D   /* 暖橙强调 */
#define UI_RED         0xE4553F   /* 断线 / 高风险 */
#define UI_WARN        0xFFB23E   /* 中风险 */

lv_obj_t *ui_pixel_screen_create(const char *title);
lv_obj_t *ui_pixel_panel_create(lv_obj_t *parent, int x, int y, int w, int h,
                                uint32_t color);
lv_obj_t *ui_pixel_label(lv_obj_t *parent, const char *text,
                         const lv_font_t *font, uint32_t color);
lv_obj_t *ui_pixel_mascot_create(lv_obj_t *parent, int x, int y);
void ui_pixel_mascot_jump(lv_obj_t *mascot);
void ui_pixel_set_selected(lv_obj_t *panel, bool selected, bool enabled);
