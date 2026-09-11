const $ = (id) => document.getElementById(id);
let state = { config: {}, status: {}, bridge: {}, logs: { stdout: [], stderr: [] } };
let devices = {};
let selectedChannel = "usb";
let logSource = "stdout";

const fields = [
  "usb_port", "device_name", "audio_device", "target_title_regex",
  "voice_hotkey", "voice_stop_key", "paste_hotkey", "enter_hotkey",
  "clear_hotkey", "cancel_hotkey",
  "input_sample_rate", "output_sample_rate", "output_channels", "session_timeout_s"
];
const checks = ["require_target_for_paste", "require_target_for_enter"];

const KEYMAP = [
  { key: "UP", sub: "单击", action: "启动语音输入", field: "voice_hotkey" },
  { key: "任意键", sub: "语音中", action: "结束语音输入", field: "voice_stop_key" },
  { key: "DOWN", sub: "单击", action: "粘贴转写结果", field: "paste_hotkey" },
  { key: "DOWN", sub: "长按", action: "清空当前输入", field: "clear_hotkey" },
  { key: "OK", sub: "单击 / 长按", action: "发送（回车）", field: "enter_hotkey" },
];

function reportClient(kind, message, extra = {}) {
  try {
    fetch("/api/client-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, message, ...extra }),
    }).catch(() => {});
  } catch (err) { /* 上报失败不影响控制台 */ }
}

window.addEventListener("error", (e) => reportClient("error", e.message, { source: e.filename, line: e.lineno, col: e.colno }));
window.addEventListener("unhandledrejection", (e) => reportClient("rejection", String(e.reason)));

async function api(path, options = {}) {
  const res = await fetch(path, { cache: "no-store", ...options });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return await res.json();
}

function fmtTime(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour12: false });
}

function value(obj, key, fallback = "--") {
  const v = obj?.[key];
  return v === undefined || v === null || v === "" ? fallback : v;
}

function shortPath(p) {
  if (!p) return "--";
  const idx = p.lastIndexOf("#");
  return idx > 0 ? "…" + p.slice(idx) : p;
}

function applyConfig(cfg) {
  if (!cfg) return;
  fields.forEach((key) => { if ($(key) && cfg[key] !== undefined) $(key).value = cfg[key]; });
  checks.forEach((key) => { if ($(key)) $(key).checked = !!cfg[key]; });
  selectedChannel = cfg.channel === "ble" ? "ble" : "usb";
  document.querySelectorAll("#channel-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.channel === selectedChannel && !b.disabled);
  });
}

function collectConfig() {
  const cfg = { ...(state.config || {}) };
  fields.forEach((key) => {
    if ($(key)) cfg[key] = $(key).type === "number" ? Number($(key).value) : $(key).value;
  });
  checks.forEach((key) => { if ($(key)) cfg[key] = $(key).checked; });
  cfg.channel = selectedChannel;
  return cfg;
}

function renderKeymap() {
  const cfg = state.config || {};
  $("keymap-grid").innerHTML = KEYMAP.map((item) => {
    const combo = String(cfg[item.field] || "--");
    const keys = combo.split(/[+,]/).map((k) => k.trim()).filter(Boolean)
      .map((k) => `<kbd>${k.toUpperCase()}</kbd>`).join("");
    return `<div class="km-cell">
        <span class="km-key">${item.key}<em>${item.sub}</em></span>
        <strong>${item.action}</strong>
        <span class="km-keys">${keys || '<kbd>--</kbd>'}</span>
      </div>`;
  }).join("");
}

function renderChannelNote() {
  const usb = devices.usb || {};
  const ble = devices.ble || {};
  const notes = {
    usb: usb.available
      ? `USB 直连可用 · 自动识别 ${shortPath(usb.path)}${usb.in_use ? " · Bridge 已占用" : ""}`
      : "USB 未就绪：未发现 ESP32-C3 CDC 接口。",
    ble: ble.available
      ? "蓝牙 radio 就绪，可切换 BLE 无线音频（拔掉 USB 前先切换通道）。"
      : `蓝牙未就绪：${ble.reason || "Windows 未暴露 Bluetooth radio"}`,
    wifi: "WiFi 音频通道固件尚未实现（当前仅 USB/BLE 可用）。",
  };
  $("channel-note").textContent = notes[selectedChannel] || "";
  $("channel-note").dataset.channel = selectedChannel;
}

function renderStatus() {
  const bridge = state.bridge || {};
  const status = state.status || {};
  const link = status.connected ? "ONLINE" : (bridge.running ? "WAITING" : "OFFLINE");
  const pill = $("bridge-pill");
  pill.className = `status-pill ${status.connected ? "online" : bridge.running ? "" : "error"}`;
  pill.innerHTML = `<i class="dot"></i><span>${link}</span>`;
  const channel = (status.channel || state.config?.channel || "--").toUpperCase();
  const ds = status.device_status || {};
  $("top-transport").textContent = channel;
  $("top-battery").textContent = ds.battery_percent !== undefined ? `${ds.battery_percent}%` : "--";
  $("top-updated").textContent = fmtTime(status.updated_at);
  $("detail-channel").textContent = channel;
  $("detail-pid").textContent = bridge.pid || "--";
  $("detail-link").textContent = ds.link || (status.connected ? "up" : "down");
  $("metric-connected").textContent = status.connected ? "CONNECTED" : bridge.running ? "WAITING" : "STOPPED";
  $("metric-battery").textContent = ds.battery_percent !== undefined
    ? `${ds.battery_percent}% · ${ds.battery_mv || "--"} mV` : "--";
  $("metric-stream").textContent = ds.streaming || (status.voice?.active ? "active" : "--");
  $("metric-drops").textContent = ds.audio_drops !== undefined
    ? `${ds.audio_drops} / ${ds.event_drops ?? 0}` : "--";
  $("metric-voice").textContent = status.voice?.active ? "LISTENING" : (status.voice?.last_event || "--");
  $("metric-key").textContent = status.last_key?.action || "--";
  $("metric-audio").textContent = status.audio?.device || state.config?.audio_device || "--";
  $("sidebar-state").textContent = `${link} / ${channel}`;
  $("usb-device").textContent = devices.usb?.available ? "CONNECTED / READY" : "NOT FOUND";
  $("ble-device").textContent = devices.ble?.available ? "RADIO READY" : (devices.ble?.reason || "NOT READY");
  renderEvents(status.events || []);
}

function renderDeviceInfo() {
  const d = devices.device || {};
  $("dev-model").textContent = d.model || "--";
  $("dev-mcu").textContent = d.mcu || "--";
  $("dev-flash").textContent = d.flash || "--";
  $("dev-display").textContent = d.display || "--";
  $("dev-audio").textContent = d.audio || "--";
  $("dev-usb-id").textContent = d.usb_vid_pid || "--";
  $("device-serial").textContent = state.status?.device?.serial || d.mac || "--";
  $("device-source").textContent = d.source ? `来源：${d.source}` : "";
  $("config-path").textContent = devices.config_path ? `写入 ${devices.config_path}` : "";
  const list = $("audio-device-list");
  if (list && !list.childElementCount && Array.isArray(devices.audio_outputs)) {
    const seen = new Set();
    list.innerHTML = devices.audio_outputs
      .map((d2) => (d2.name || "").trim())
      .filter((n) => n && !seen.has(n) && seen.add(n))
      .map((n) => `<option value="${n.replace(/"/g, "&quot;")}"></option>`).join("");
  }
}

function renderEvents(events) {
  const box = $("event-list");
  if (!events.length) { box.innerHTML = '<div class="empty">暂无事件</div>'; return; }
  box.innerHTML = events.slice(-40).reverse().map((e) => {
    const t = fmtTime(e.time);
    return `<div class="event"><span>${t}</span><em>${e.kind || "event"}</em><b>${e.message || ""}</b></div>`;
  }).join("");
}

function renderLogs() {
  const lines = state.logs?.[logSource] || [];
  $("log-output").textContent = lines.length ? lines.join("\n") : "等待 Bridge 日志...";
  document.querySelectorAll(".log-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.log === logSource));
}

let selfChecked = false;

function selfCheck() {
  if (selfChecked) return;
  selfChecked = true;
  const doc = document.documentElement;
  reportClient("ready", "dashboard rendered", {
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    scroll_width: doc.scrollWidth,
    overflow_x: doc.scrollWidth > window.innerWidth + 1,
    keymap_cells: document.querySelectorAll("#keymap-grid .km-cell").length,
    metric_cells: document.querySelectorAll(".metric-grid .metric").length,
    state: state.status?.phase || null,
  });
}

async function refresh() {
  try {
    const [s, d] = await Promise.all([api("/api/state"), api("/api/devices")]);
    state = s;
    devices = d;
    const typing = document.activeElement && document.activeElement.tagName === "INPUT";
    if (!typing) applyConfig(s.config);
    renderKeymap();
    renderStatus();
    renderDeviceInfo();
    renderChannelNote();
    renderLogs();
    if (!s.config?.usb_port && d.usb?.path) $("usb_port").placeholder = shortPath(d.usb.path);
    selfCheck();
  } catch (err) {
    const pill = $("bridge-pill");
    pill.className = "status-pill error";
    pill.innerHTML = '<i class="dot"></i><span>DASHBOARD ERROR</span>';
  }
}

async function saveConfig() {
  const cfg = collectConfig();
  state.config = cfg;
  await api("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg) });
  return cfg;
}

$("local-address").textContent = location.host;

$("channel-tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-channel]");
  if (!b || b.disabled) return;
  selectedChannel = b.dataset.channel;
  document.querySelectorAll("#channel-tabs button").forEach((x) => x.classList.toggle("active", x === b));
  renderChannelNote();
});

$("btn-save").addEventListener("click", async () => { await saveConfig(); await refresh(); });
$("btn-apply").addEventListener("click", async () => {
  const cfg = await saveConfig();
  await api("/api/bridge", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "restart", channel: cfg.channel }) });
  setTimeout(refresh, 900);
});
$("btn-stop").addEventListener("click", async () => {
  await api("/api/bridge", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "stop" }) });
  setTimeout(refresh, 400);
});
$("btn-test-mic").addEventListener("click", async () => {
  $("test-output").textContent = "运行虚拟声卡回环测试…";
  try {
    const r = await api("/api/test-mic", { method: "POST" });
    $("test-output").textContent = (r.output || (r.ok ? "PASS" : "FAIL")).trim();
  } catch (err) {
    $("test-output").textContent = `测试失败：${err.message}`;
  }
});
document.querySelectorAll(".log-tabs button").forEach((b) => b.addEventListener("click", () => {
  logSource = b.dataset.log; renderLogs();
}));

refresh();
setInterval(refresh, 2000);
