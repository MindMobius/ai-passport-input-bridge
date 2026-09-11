// main/app_ui.c —— 产品 UI 实现。见 app_ui.h 布局说明。
#include "app_ui.h"
#include "bsp_battery.h"     // 电量(主循环已把真实值补进快照,此处仅渲染)
#include "bsp_display.h"
#include "time_sync.h"       // 顶栏 HH:MM(校时源仅电脑客户端,未校时 "--:--")
#include "ui_pixel.h"
#include "lvgl.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

// ---- 布局常量 ----
#define BAR_H        26   // 顶栏高
#define BANNER_Y     28   // OFFLINE / NET BUSY 横幅
#define BANNER_H     18
#define CONTENT_Y    48   // 内容区起点
#define HINT_Y       286  // 各页底部提示行
#define W            240
#define H            320

// 顶栏(无 BLE 点、无 CPU/RAM 监测):右侧对齐组:电池图标(描边框+右缘
// 触点,数字居中)、HH:MM 时间(最右贴 6px)。240px:144+34+4 / 182+52。
#define BATT_X       144
#define BATT_W       34
#define BATT_H       16
#define BATT_NUB_X   (BATT_X + BATT_W)   // 右缘触点
#define BATT_NUB_W   4
#define TIME_X       182
#define TIME_W       52

// ---- 页内部件索引(与 page 切换共用) ----
typedef struct {
    lv_obj_t *root;                       // 本页容器(显隐切换)
    lv_obj_t *rec_label;                  // LISTENING:RECORDING 大字
    lv_obj_t *rec_elapsed;                // LISTENING:计时
    lv_obj_t *tr_message;                 // TRANSCRIBING:消息
    lv_obj_t *run_state;                  // AGENT_RUNNING:状态名
    lv_obj_t *run_message;                // AGENT_RUNNING:消息
    lv_obj_t *ap_risk_banner;             // APPROVAL:风险条
    lv_obj_t *ap_risk_label;              // APPROVAL:风险文本
    lv_obj_t *ap_title;                   // APPROVAL:标题
    lv_obj_t *ap_target;                  // APPROVAL:目标
    lv_obj_t *ap_diff;                    // APPROVAL:摘要/详情
    lv_obj_t *stat_link;                  // HOME/READY:链路 + 电脑端状态行
    lv_obj_t *stat_mic;                   // HOME/READY:虚拟声卡/麦克风行
    lv_obj_t *stat_diag;                  // READY:电量 mV / MTU / 丢帧(诊断行)
} page_t;

static lv_obj_t *s_chrome;                // 顶层容器(lv_layer_top)
static lv_obj_t *s_batt_icon;   // 电池描边框(数字居中在框内)
static lv_obj_t *s_batt_nub;    // 右缘触点
static lv_obj_t *s_batt_label;
static lv_obj_t *s_time_label;
static lv_obj_t *s_offline_banner;
static lv_obj_t *s_offline_text;
static lv_obj_t *s_netbusy_banner;
static lv_obj_t *s_netbusy_text;
static lv_obj_t *s_toast;

static page_t s_pages[APP_ST_COUNT];
static app_stage_t s_cur_page = APP_ST_COUNT;
static bool s_last_screen_on = true;
static int  s_last_info_state = -1;   // 连接信息配色档(0=离线 1=仅链路 2=链路+PC)
static int  s_last_time_fresh = -1;   // 时钟配色档(-1=未初始化)
static lv_obj_t *s_bg;   // 基底屏:所有状态页都是它的子对象(单屏方案)

static const char *const RISK_NAMES[APP_RISK_COUNT] = { "LOW RISK", "MEDIUM RISK", "HIGH RISK" };
#define RISK_LOW 0x9A9A9A
static const uint32_t RISK_COLORS[APP_RISK_COUNT] = { RISK_LOW, UI_WARN, UI_RED };

// ---- 基础块(无 LVGL 样式噪音) ----
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

static lv_obj_t *label(lv_obj_t *parent, const char *text, const lv_font_t *font,
                       uint32_t color, int x, int y, int w)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, text);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
    lv_obj_set_pos(l, x, y);
    lv_obj_set_width(l, w);
    lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
    return l;
}

static lv_obj_t *hint_label(lv_obj_t *parent, const char *text)
{
    return label(parent, text, &lv_font_montserrat_14, UI_MUTED, 0, HINT_Y, W);
}

// ---- 基底屏:纯黑底 + 上/下细线(黑白线稿主题) ----
static void build_background(void)
{
    lv_obj_t *scr = lv_obj_create(NULL);  // LVGL 9.5: 创建顶层 screen(旧 lv_screen_create 已移除)
    s_bg = scr;
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_BG), 0);
    lv_obj_set_style_border_width(scr, 0, 0);
    lv_obj_set_style_pad_all(scr, 0, 0);

    // 顶栏下缘线 + 底部提示区上缘线:线稿语言的两条骨架线
    block(scr, 0, BAR_H - 1, W, 1, UI_LINE);
    block(scr, 12, HINT_Y - 12, W - 24, 1, UI_LINE);
    lv_screen_load(scr);
}

// ---- chrome:常驻顶栏 / 横幅 / Toast(顶层,所有页共用) ----
static void build_chrome(void)
{
    s_chrome = lv_display_get_layer_top(lv_display_get_default());  // LVGL 9.5 改名
    lv_obj_remove_flag(s_chrome, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_pad_all(s_chrome, 0, 0);

    // 顶栏:不铺底色,只用"橙色方块 + 弱化设备名"标记品牌位(线稿风格)
    block(s_chrome, 12, 10, 5, 5, UI_ACCENT);
    label(s_chrome, "AI PASSPORT", &lv_font_montserrat_14, UI_MUTED, 22, 5, 100);

    // 电池:1px 描边框 + 右缘触点(线稿),数字居中(无 % 后缀)
    s_batt_icon = block(s_chrome, BATT_X, 5, BATT_W, BATT_H, UI_BG);
    lv_obj_set_style_border_width(s_batt_icon, 1, 0);
    lv_obj_set_style_border_color(s_batt_icon, lv_color_hex(UI_LINE_BRIGHT), 0);
    lv_obj_set_style_radius(s_batt_icon, 2, 0);
    s_batt_nub = block(s_chrome, BATT_NUB_X, 10, 2, 6, UI_LINE_BRIGHT);
    // 数字位置在 render 按真实字宽/字形高精确计算(batt_label_reposition):
    // 实测 montserrat_14 数字字形高 10px,label 行高 16 → y=1 靠上视觉居中
    s_batt_label = label(s_batt_icon, "--", &lv_font_montserrat_14, UI_TEXT,
                         0, -2, BATT_W - 2);
    s_time_label = label(s_chrome, "--:--", &lv_font_montserrat_14, UI_TEXT,
                         TIME_X, 5, TIME_W);

    // 断线横幅(链路断时整宽显示;link_up = EVENT 特征已订阅)。
    // 文本是子 label(render 按通道名改写文案);banner 本体是 block,不能
    // 对 block 调 label_set_*(会按 label 布局读越界内存 → Load access fault)。
    s_offline_banner = block(s_chrome, 0, BANNER_Y, W, BANNER_H, UI_PANEL);
    block(s_offline_banner, 0, 0, 3, BANNER_H, UI_RED);
    s_offline_text = label(s_offline_banner, "USB DISCONNECTED - reconnecting...",
                           &lv_font_montserrat_14, UI_RED, 0, 1, W);

    // 网络拥塞(音频丢帧中)
    s_netbusy_banner = block(s_chrome, 0, BANNER_Y, W, BANNER_H, UI_PANEL);
    block(s_netbusy_banner, 0, 0, 3, BANNER_H, UI_WARN);
    s_netbusy_text = label(s_netbusy_banner, "USB BUSY - dropping frames",
                           &lv_font_montserrat_14, UI_WARN, 0, 1, W);

    // Toast(底部浮层,空文本即隐藏)
    lv_obj_t *tbg = block(s_chrome, 30, 272, 180, 30, UI_PANEL);
    lv_obj_set_style_border_width(tbg, 1, 0);
    lv_obj_set_style_border_color(tbg, lv_color_hex(UI_LINE_BRIGHT), 0);
    s_toast = label(tbg, "", &lv_font_montserrat_14, UI_TEXT, 0, 6, 178);
}

// ---- 各状态页 ----
static void build_home(void)
{
    page_t *p = &s_pages[APP_ST_HOME];
    p->root = lv_obj_create(s_bg);   // 基底屏的子对象:切换只显隐,不动活动屏
    lv_obj_remove_flag(p->root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(p->root, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(p->root, 0, 0);
    lv_obj_set_style_pad_all(p->root, 0, 0);
    lv_obj_set_size(p->root, W, H);
    lv_obj_set_pos(p->root, 0, 0);

    // 页眉:小号弱化标识 + 主标题 + 橙色细线(线稿语言的三段式标题)
    label(p->root, "PASSPORT / VOICE BRIDGE", &lv_font_montserrat_14, UI_DIM,
          0, CONTENT_Y + 6, W);
    label(p->root, "VOICE INPUT", &lv_font_montserrat_20, UI_TEXT, 0, 86, W);
    block(p->root, 60, 114, 120, 1, UI_ACCENT);

    ui_pixel_mascot_create(p->root, 100, 132);
    label(p->root, "TAP UP TO START", &lv_font_montserrat_14, UI_MUTED, 0, 216, W);
    // 连接信息两行:上=链路+电脑端是否在线,下=虚拟声卡/麦克风(render 填文本)
    p->stat_link = label(p->root, "", &lv_font_montserrat_14, UI_MUTED, 0, 236, W);
    p->stat_mic  = label(p->root, "", &lv_font_montserrat_14, UI_DIM, 0, 254, W);
    hint_label(p->root, "UP: SPEAK   DOWN: PASTE   OK: SEND");
}

static void build_ready(void)
{
    page_t *p = &s_pages[APP_ST_READY];
    p->root = lv_obj_create(s_bg);   // 基底屏的子对象:切换只显隐,不动活动屏
    lv_obj_remove_flag(p->root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(p->root, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(p->root, 0, 0);
    lv_obj_set_style_pad_all(p->root, 0, 0);
    lv_obj_set_size(p->root, W, H);
    lv_obj_set_pos(p->root, 0, 0);

    // 工作流切换已取消(固定 build),READY 为简单就绪页
    label(p->root, "READY", &lv_font_montserrat_20, UI_TEXT, 0, CONTENT_Y + 40, W);
    block(p->root, 104, CONTENT_Y + 70, 32, 1, UI_ACCENT);
    // 原静态 "LINK UP / MIC ARMED" 升级为实时链路/电脑端状态(render 填文本)
    p->stat_link = label(p->root, "", &lv_font_montserrat_14, UI_DIM, 0, 190, W);
    p->stat_mic  = label(p->root, "", &lv_font_montserrat_14, UI_DIM, 0, 210, W);
    // 诊断行(电量毫伏/MTU/丢帧):只在 READY 页,技术细节不占主页版面
    p->stat_diag = label(p->root, "", &lv_font_montserrat_14, UI_DIM, 0, 230, W);
    hint_label(p->root, "UP: SPEAK   DOWN: PASTE   OK: SEND");
}

static void build_listening(void)
{
    page_t *p = &s_pages[APP_ST_LISTENING];
    p->root = lv_obj_create(s_bg);   // 基底屏的子对象:切换只显隐,不动活动屏
    lv_obj_remove_flag(p->root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(p->root, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(p->root, 0, 0);
    lv_obj_set_style_pad_all(p->root, 0, 0);
    lv_obj_set_size(p->root, W, H);
    lv_obj_set_pos(p->root, 0, 0);

    // 录音中不画图标, 直接文字 + 橙色细线 + 静态电平条
    p->rec_label = label(p->root, "RECORDING", &lv_font_montserrat_20, UI_TEXT, 0, 86, W);
    block(p->root, 60, 116, 120, 1, UI_ACCENT);

    block(p->root, 100, 136, 4, 10, UI_ACCENT);
    block(p->root, 108, 130, 4, 22, UI_ACCENT);
    block(p->root, 116, 125, 4, 32, UI_ACCENT);
    block(p->root, 124, 130, 4, 22, UI_ACCENT);
    block(p->root, 132, 136, 4, 10, UI_ACCENT);

    p->rec_elapsed = label(p->root, "0s", &lv_font_montserrat_20, UI_TEXT, 0, 200, W);
    hint_label(p->root, "PRESS ANY KEY TO STOP");
}

static void build_transcribing(void)
{
    page_t *p = &s_pages[APP_ST_TRANSCRIBING];
    p->root = lv_obj_create(s_bg);   // 基底屏的子对象:切换只显隐,不动活动屏
    lv_obj_remove_flag(p->root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(p->root, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(p->root, 0, 0);
    lv_obj_set_style_pad_all(p->root, 0, 0);
    lv_obj_set_size(p->root, W, H);
    lv_obj_set_pos(p->root, 0, 0);

    label(p->root, "TRANSCRIBING", &lv_font_montserrat_20, UI_TEXT, 0, 96, W);
    block(p->root, 60, 126, 120, 1, UI_ACCENT);
    block(p->root, 96, 144, 4, 4, UI_ACCENT);
    block(p->root, 108, 144, 4, 4, UI_LINE_BRIGHT);
    block(p->root, 120, 144, 4, 4, UI_LINE);
    p->tr_message = label(p->root, "", &lv_font_montserrat_14, UI_MUTED, 20, 168, 200);
    hint_label(p->root, "PLEASE WAIT");
}

static void build_running(void)
{
    page_t *p = &s_pages[APP_ST_AGENT_RUNNING];
    p->root = lv_obj_create(s_bg);   // 基底屏的子对象:切换只显隐,不动活动屏
    lv_obj_remove_flag(p->root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(p->root, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(p->root, 0, 0);
    lv_obj_set_style_pad_all(p->root, 0, 0);
    lv_obj_set_size(p->root, W, H);
    lv_obj_set_pos(p->root, 0, 0);

    // 静态"spinner":1px 描边的空方块(线稿风格,替代原蓝色实心块)
    lv_obj_t *spinner = block(p->root, 110, 76, 20, 20, UI_PANEL);
    lv_obj_set_style_border_width(spinner, 1, 0);
    lv_obj_set_style_border_color(spinner, lv_color_hex(UI_ACCENT), 0);
    p->run_state = label(p->root, "running", &lv_font_montserrat_20, UI_TEXT,
                         0, 112, W);
    block(p->root, 60, 144, 120, 1, UI_LINE);
    p->run_message = label(p->root, "", &lv_font_montserrat_14, UI_MUTED,
                           20, 158, 200);
    hint_label(p->root, "AGENT WORKING...");
}

static void build_approval(void)
{
    page_t *p = &s_pages[APP_ST_APPROVAL];
    p->root = lv_obj_create(s_bg);   // 基底屏的子对象:切换只显隐,不动活动屏
    lv_obj_remove_flag(p->root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(p->root, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(p->root, 0, 0);
    lv_obj_set_style_pad_all(p->root, 0, 0);
    lv_obj_set_size(p->root, W, H);
    lv_obj_set_pos(p->root, 0, 0);

    // 风险条:1px 描边 + 同色文字(颜色由 render 按风险等级写入)
    p->ap_risk_banner = block(p->root, 20, CONTENT_Y + 8, 200, 28, UI_PANEL);
    lv_obj_set_style_border_width(p->ap_risk_banner, 1, 0);
    lv_obj_set_style_border_color(p->ap_risk_banner, lv_color_hex(UI_LINE_BRIGHT), 0);
    p->ap_risk_label = label(p->ap_risk_banner, "", &lv_font_montserrat_14, UI_TEXT,
                             0, 5, 198);

    p->ap_title = label(p->root, "", &lv_font_montserrat_20, UI_TEXT, 20, 108, 200);
    lv_obj_set_style_text_align(p->ap_title, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(p->ap_title, LV_LABEL_LONG_WRAP);

    block(p->root, 20, 146, 200, 1, UI_LINE);
    p->ap_target = label(p->root, "", &lv_font_montserrat_14, UI_ACCENT, 20, 154, 200);
    p->ap_diff = label(p->root, "", &lv_font_montserrat_14, UI_MUTED, 20, 178, 200);
    lv_obj_set_style_text_align(p->ap_diff, LV_TEXT_ALIGN_LEFT, 0);
    lv_label_set_long_mode(p->ap_diff, LV_LABEL_LONG_WRAP);
    lv_obj_set_height(p->ap_diff, 88);

    hint_label(p->root, "OK: APPROVE   VOL+: REJECT   DOWN: ENTER");
}

static void set_hidden(lv_obj_t *o, bool hidden)
{
    if (hidden) lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
}

// U1 dirty-check:文本未变则跳过 set_text。set_text 会重排标签并标记整行
// 无效重绘——LISTENING 10fps 渲染下反复写相同文本(计时秒数、电量、CPU/RAM、
// agent 消息)是无谓开销。lv_label_get_text 返回当前文本,比较后决定是否写。
static void label_set_if_changed(lv_obj_t *l, const char *text)
{
    if (!l || !text) return;
    const char *cur = lv_label_get_text(l);
    if (cur && strcmp(cur, text) == 0) return;
    lv_label_set_text(l, text);
}

static void label_set_fmt_if_changed(lv_obj_t *l, const char *fmt, ...)
{
    char buf[64];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    label_set_if_changed(l, buf);
}

// 转写预览态:文本尾部附一个光标感字符 '_'(未定稿视觉);定稿后移除。
// 改动最小方案:不动样式,只改文本。栈缓冲覆盖 满长文本 + 光标。
static void set_agent_message(lv_obj_t *label_obj, const char *msg, bool preview)
{
    char buf[APP_AGENT_MSG_MAX + 2];
    if (preview && msg && msg[0]) {
        snprintf(buf, sizeof(buf), "%s_", msg);
        label_set_if_changed(label_obj, buf);
    } else {
        label_set_if_changed(label_obj, msg ? msg : "");
    }
}

// ---- 页切换 ----
static void show_page(app_stage_t st)
{
    if (st == s_cur_page) return;
    if (s_cur_page < APP_ST_COUNT) lv_obj_add_flag(s_pages[s_cur_page].root, LV_OBJ_FLAG_HIDDEN);
    if (st < APP_ST_COUNT) lv_obj_remove_flag(s_pages[st].root, LV_OBJ_FLAG_HIDDEN);
    s_cur_page = st;
}

esp_err_t app_ui_init(void)
{
    build_background();
    build_chrome();
    build_home();
    build_ready();
    build_listening();
    build_transcribing();
    build_running();
    build_approval();
    for (int i = 0; i < APP_ST_COUNT; i++) {
        lv_obj_add_flag(s_pages[i].root, LV_OBJ_FLAG_HIDDEN);
    }
    show_page(APP_ST_HOME);
    return ESP_OK;
}

// ---- 渲染 ----
// 连接信息两行(仅 HOME/READY 显示):
//   LINK <通道> / PC <ONLINE|WAITING>
//   MIC <虚拟声卡麦克风>(auto)  或  MIC AUTO OFF / START BRIDGE ON PC
// 配色档只在跨档时写样式 —— 每帧 set_style 会让整行重绘(与 label 的
// dirty-check 同一动机)。
static void render_link_info(const app_ui_snapshot_t *snap)
{
    char l1[48];
    char l2[48];
    const int info_state = !snap->link_up ? 0 : (snap->pc_online ? 2 : 1);

    snprintf(l1, sizeof(l1), "LINK %s / PC %s",
             snap->link_up ? snap->link_name : "NONE",
             snap->pc_online ? "ONLINE" : "WAITING");
    if (snap->pc_online) {
        if (snap->pc_mic_auto && snap->pc_mic[0]) {
            snprintf(l2, sizeof(l2), "MIC %s (auto)", snap->pc_mic);
        } else if (snap->pc_mic[0]) {
            snprintf(l2, sizeof(l2), "MIC %s", snap->pc_mic);
        } else if (snap->pc_sink[0]) {
            snprintf(l2, sizeof(l2), "SINK %s", snap->pc_sink);
        } else {
            snprintf(l2, sizeof(l2), "MIC AUTO OFF");
        }
    } else if (snap->link_up) {
        // 链路在但收不到心跳:桥接进程没跑/卡住(最容易踩的一种)
        snprintf(l2, sizeof(l2), "PC BRIDGE NOT RESPONDING");
    } else {
        // 双通道都没通:设备在广播/等 USB,等的是电脑端那一步
        snprintf(l2, sizeof(l2), "START BRIDGE ON PC");
    }

    for (int pg = APP_ST_HOME; pg <= APP_ST_READY; pg++) {
        label_set_if_changed(s_pages[pg].stat_link, l1);
        label_set_if_changed(s_pages[pg].stat_mic, l2);
    }

    // 诊断行(READY):电量毫伏 + BLE MTU + 音频/事件丢帧。MTU 仅 BLE 有意义,
    // 无连接时为 0 → 省略,免得 USB 会话里显示 "MTU0" 这种噪音。
    {
        char l3[48];
        char mtu[12] = "";
        if (snap->mtu > 0) snprintf(mtu, sizeof(mtu), "  MTU%u", (unsigned)snap->mtu);
        if (snap->battery_mv >= 0) {
            snprintf(l3, sizeof(l3), "%dmV%s  DROP %u/%u", snap->battery_mv, mtu,
                     (unsigned)snap->audio_drops, (unsigned)snap->event_drops);
        } else {
            snprintf(l3, sizeof(l3), "--mV%s  DROP %u/%u", mtu,
                     (unsigned)snap->audio_drops, (unsigned)snap->event_drops);
        }
        label_set_if_changed(s_pages[APP_ST_READY].stat_diag, l3);
    }

    if (info_state != s_last_info_state) {
        // 2 = 链路 + 电脑端都在线(暖橙);1 = 只有链路(次级灰);0 = 无链路(弱化)
        static const uint32_t LINK_COLORS[3] = { UI_DIM, UI_MUTED, UI_ACCENT };
        uint32_t color = LINK_COLORS[info_state];
        for (int pg = APP_ST_HOME; pg <= APP_ST_READY; pg++) {
            lv_obj_set_style_text_color(s_pages[pg].stat_link, lv_color_hex(color), 0);
        }
        s_last_info_state = info_state;
    }
}

void app_ui_render(const app_ui_snapshot_t *snap)
{
    // 息屏/唤醒:背光切换(内容照常更新,唤醒后即为最新)
    if (snap->screen_on != s_last_screen_on) {
        bsp_display_backlight(snap->screen_on ? 100 : 0);
        s_last_screen_on = snap->screen_on;
    }
    if (!snap->screen_on) return;

    // ---- chrome ----
    if (snap->battery_available) {
        label_set_fmt_if_changed(s_batt_label, "%d", snap->battery_soc);
    } else {
        label_set_if_changed(s_batt_label, "--");
    }
    {
        char t[16];
        time_sync_format_local(t, sizeof(t));
        label_set_if_changed(s_time_label, t);
    }
    // 时钟配色:电脑端本次开机校过时 = 正常白;NVS 恢复的旧时间 = 弱化灰
    // (设备无 RTC 电池,复位后先显示"上次已知时间",不自称准确)。
    if ((int)snap->time_fresh != s_last_time_fresh) {
        lv_obj_set_style_text_color(s_time_label,
                                    lv_color_hex(snap->time_fresh ? UI_TEXT : UI_DIM), 0);
        s_last_time_fresh = snap->time_fresh;
    }

    // 横幅互斥:OFFLINE(通道断线)> BUSY(同位置 BANNER_Y)
    // 文案按当前链路通道渲染(BLE/USB;断线横幅显示 link_name 字样)
    label_set_fmt_if_changed(s_offline_text, "%s DISCONNECTED - reconnecting...",
                             snap->link_name);
    label_set_fmt_if_changed(s_netbusy_text, "%s BUSY - dropping frames",
                             snap->link_name);
    set_hidden(s_offline_banner, snap->link_up);
    set_hidden(s_netbusy_banner, !snap->net_busy || !snap->link_up);

    // 连接信息(HOME/READY 两页共用同一份文本)
    render_link_info(snap);

    if (snap->toast[0]) {
        label_set_if_changed(s_toast, snap->toast);
        set_hidden(lv_obj_get_parent(s_toast), false);
    } else {
        set_hidden(lv_obj_get_parent(s_toast), true);
    }

    // ---- 页内容 ----
    show_page(snap->state);
    switch (snap->state) {
    case APP_ST_LISTENING:
        // 录音中只显示麦克风图标(静态), 无音量可视化; 仅计时实时刷新
        label_set_fmt_if_changed(s_pages[APP_ST_LISTENING].rec_elapsed, "%ds",
                                 snap->elapsed_ms / 1000);
        break;
    case APP_ST_TRANSCRIBING:
        set_agent_message(s_pages[APP_ST_TRANSCRIBING].tr_message,
                          snap->agent_message, !snap->transcript_final);
        break;
    case APP_ST_AGENT_RUNNING:
        label_set_if_changed(s_pages[APP_ST_AGENT_RUNNING].run_state,
                             snap->agent_state_name);
        set_agent_message(s_pages[APP_ST_AGENT_RUNNING].run_message,
                          snap->agent_message, !snap->transcript_final);
        break;
    case APP_ST_APPROVAL: {
        uint8_t r = snap->approval_risk < APP_RISK_COUNT ? snap->approval_risk : APP_RISK_MEDIUM;
        lv_obj_set_style_bg_color(s_pages[APP_ST_APPROVAL].ap_risk_banner,
                                  lv_color_hex(UI_PANEL), 0);
        lv_obj_set_style_border_color(s_pages[APP_ST_APPROVAL].ap_risk_banner,
                                      lv_color_hex(RISK_COLORS[r]), 0);
        lv_obj_set_style_text_color(s_pages[APP_ST_APPROVAL].ap_risk_label,
                                    lv_color_hex(RISK_COLORS[r]), 0);
        label_set_if_changed(s_pages[APP_ST_APPROVAL].ap_risk_label, RISK_NAMES[r]);
        label_set_if_changed(s_pages[APP_ST_APPROVAL].ap_title, snap->approval_title);
        label_set_fmt_if_changed(s_pages[APP_ST_APPROVAL].ap_target, "target: %s",
                                 snap->approval_target);
        label_set_if_changed(s_pages[APP_ST_APPROVAL].ap_diff, snap->approval_diff);
        break;
    }
    default:
        break;
    }
}
