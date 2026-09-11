#include "ui_pixel.h"

static void start_blink(lv_obj_t *dot);

static lv_obj_t *block(lv_obj_t *parent, int x, int y, int w, int h, uint32_t color)
{
    lv_obj_t *obj = lv_obj_create(parent);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_radius(obj, 0, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_set_style_bg_color(obj, lv_color_hex(color), 0);
    return obj;
}

/* 线稿原子元素:1px 直线。整套主题只用方块与直线,不用圆角/阴影/色块。 */
static void hline(lv_obj_t *parent, int x, int y, int w, uint32_t color)
{
    block(parent, x, y, w, 1, color);
}

static void vline(lv_obj_t *parent, int x, int y, int h, uint32_t color)
{
    block(parent, x, y, 1, h, color);
}

lv_obj_t *ui_pixel_label(lv_obj_t *parent, const char *text,
                         const lv_font_t *font, uint32_t color)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    return label;
}

lv_obj_t *ui_pixel_screen_create(const char *title)
{
    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_BG), 0);
    lv_obj_set_style_border_width(scr, 0, 0);
    lv_obj_set_style_pad_all(scr, 0, 0);

    /* 标题行:左侧橙色竖标 + 标题 + 下缘细线 */
    block(scr, 12, 11, 3, 14, UI_ACCENT);
    lv_obj_t *heading = ui_pixel_label(scr, title, &lv_font_montserrat_20, UI_TEXT);
    lv_obj_set_pos(heading, 23, 8);
    hline(scr, 12, 34, 216, UI_LINE);
    return scr;
}

lv_obj_t *ui_pixel_panel_create(lv_obj_t *parent, int x, int y, int w, int h,
                                uint32_t color)
{
    lv_obj_t *panel = block(parent, x, y, w, h, color);
    lv_obj_set_style_border_color(panel, lv_color_hex(UI_LINE), 0);
    lv_obj_set_style_border_width(panel, 1, 0);
    lv_obj_set_style_pad_all(panel, 7, 0);
    return panel;
}

/* 线稿麦克风:1px 描边胶囊 + 拾音弧 + 支架,橙色指示灯呼吸闪烁。 */
lv_obj_t *ui_pixel_mascot_create(lv_obj_t *parent, int x, int y)
{
    lv_obj_t *m = lv_obj_create(parent);
    lv_obj_remove_flag(m, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(m, x, y);
    lv_obj_set_size(m, 40, 56);
    lv_obj_set_style_bg_opa(m, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(m, 0, 0);
    lv_obj_set_style_pad_all(m, 0, 0);

    hline(m, 14, 0, 12, UI_TEXT);
    vline(m, 14, 0, 26, UI_TEXT);
    vline(m, 25, 0, 26, UI_TEXT);
    hline(m, 14, 25, 12, UI_TEXT);
    lv_obj_t *lamp = block(m, 17, 8, 6, 6, UI_ACCENT);

    vline(m, 8, 13, 13, UI_LINE_BRIGHT);
    vline(m, 31, 13, 13, UI_LINE_BRIGHT);
    hline(m, 8, 26, 24, UI_LINE_BRIGHT);
    vline(m, 19, 27, 10, UI_LINE_BRIGHT);
    hline(m, 12, 37, 16, UI_LINE_BRIGHT);

    start_blink(lamp);
    return m;
}

static void jump_y(void *obj, int32_t value)
{
    lv_obj_set_y((lv_obj_t *)obj, value);
}

static void blink_dot(void *obj, int32_t value)
{
    lv_obj_set_style_opa((lv_obj_t *)obj, (lv_opa_t)value, 0);
}

static void start_blink(lv_obj_t *dot)
{
    lv_anim_t anim;
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, dot);
    lv_anim_set_exec_cb(&anim, blink_dot);
    lv_anim_set_values(&anim, LV_OPA_COVER, LV_OPA_20);
    lv_anim_set_duration(&anim, 70);
    lv_anim_set_playback_duration(&anim, 70);
    lv_anim_set_repeat_delay(&anim, 1700);
    lv_anim_set_repeat_count(&anim, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_path_cb(&anim, lv_anim_path_step);
    lv_anim_start(&anim);
}

void ui_pixel_mascot_jump(lv_obj_t *mascot)
{
    if (!mascot) return;
    int y = lv_obj_get_y(mascot);
    lv_anim_delete(mascot, jump_y);
    lv_anim_t anim;
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, mascot);
    lv_anim_set_exec_cb(&anim, jump_y);
    lv_anim_set_values(&anim, y, y - 5);
    lv_anim_set_duration(&anim, 110);
    lv_anim_set_playback_duration(&anim, 140);
    lv_anim_set_path_cb(&anim, lv_anim_path_step);
    lv_anim_start(&anim);
}

void ui_pixel_set_selected(lv_obj_t *panel, bool selected, bool enabled)
{
    uint32_t bg = selected ? 0x140D07 : UI_PANEL;
    uint32_t border = !enabled ? UI_LINE : (selected ? UI_ACCENT : UI_LINE_BRIGHT);
    lv_obj_set_style_bg_color(panel, lv_color_hex(bg), 0);
    lv_obj_set_style_border_color(panel, lv_color_hex(border), 0);
}
