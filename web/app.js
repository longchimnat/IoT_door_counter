/* Dashboard đề tài 2 - Đếm lượt người qua cửa. Không dùng thư viện ngoài (chạy được khi không có Internet). */
"use strict";

const TZ = "Asia/Ho_Chi_Minh";
const $ = (id) => document.getElementById(id);

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

const state = {
  token: store.get("token"),
  devices: [],
  deviceId: null,
  device: null,
  ws: null,
  wsRetry: 0,
  refreshTimer: null,
  lastResetAt: null,
};

/* ---------------- tiện ích ---------------- */
const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString("vi-VN", { timeZone: TZ, hour12: false }) : "–";
const fmtDateTime = (iso) => iso ? new Date(iso).toLocaleString("vi-VN", { timeZone: TZ, hour12: false }) : "–";
const todayLocal = () => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
const currentHour = () => Number(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", hour12: false }).format(new Date()));
function ago(iso) {
  if (!iso) return "chưa có";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s} giây trước`;
  if (s < 3600) return `${Math.floor(s / 60)} phút trước`;
  if (s < 86400) return `${Math.floor(s / 3600)} giờ trước`;
  return fmtDateTime(iso);
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, unit = "") => (v === null || v === undefined) ? "–" : `${Math.round(v * 10) / 10}${unit}`;
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

/* ---------------- API ---------------- */
async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (opts.body && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error("Phiên đăng nhập hết hạn"); }
  if (!res.ok) {
    let msg = `${res.status}`;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

/* ---------------- đăng nhập ---------------- */
function showLogin() { $("app-view").hidden = true; $("login-view").hidden = false; $("login-pass").focus(); }
function showApp() { $("login-view").hidden = true; $("app-view").hidden = false; }

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").textContent = "";
  try {
    const r = await fetch("/api/v1/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("login-user").value.trim(), password: $("login-pass").value }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "Đăng nhập thất bại");
    state.token = j.access_token;
    store.set("token", state.token);
    $("login-pass").value = "";
    await start();
  } catch (err) { $("login-error").textContent = err.message; }
});

function logout() {
  state.token = null;
  store.del("token");
  if (state.ws) { state.ws.onclose = null; state.ws.close(); state.ws = null; }
  clearInterval(state.refreshTimer);
  showLogin();
}
$("logout-btn").addEventListener("click", logout);

/* ---------------- render ---------------- */
function renderCount(count, lastResetAt, total) {
  const el = $("count-today");
  const prev = el.textContent;
  el.textContent = count;
  if (prev !== "–" && prev !== String(count)) { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
  const parts = [];
  if (lastResetAt) parts.push(`Đặt lại lúc ${fmtTime(lastResetAt)}`);
  if (total !== undefined && total !== count) parts.push(`cả ngày: ${total}`);
  $("count-meta").textContent = parts.join(" · ") || "Tính từ 0h hôm nay";
}

function renderDevice(d) {
  if (!d) return;
  state.device = d;
  const card = $("room-card");
  card.classList.remove("busy", "free");
  if (d.room_occupied === true) { card.classList.add("busy"); $("room-text").textContent = "Có người"; }
  else if (d.room_occupied === false) { card.classList.add("free"); $("room-text").textContent = "Phòng trống"; }
  else $("room-text").textContent = "Chưa có dữ liệu";
  $("room-meta").textContent = d.last_motion_at ? `Chuyển động gần nhất: ${ago(d.last_motion_at)}` : "Chưa ghi nhận chuyển động";

  const st = $("dev-status");
  st.className = `pill ${d.status}`;
  st.textContent = { online: "Online", offline: "Offline", unknown: "Chưa kết nối" }[d.status] || d.status;
  $("dev-location").textContent = d.location || "–";
  $("dev-ping").textContent = ago(d.last_ping);
  $("dev-distance").textContent = num(d.last_distance_cm, " cm");
}

function renderChart(data) {
  const W = 760, H = 260, padL = 34, padR = 8, padT = 22, padB = 28;
  const max = Math.max(4, ...data.buckets.map((b) => b.count));
  const step = Math.ceil(max / 4);
  const top = step * 4;
  const cw = (W - padL - padR) / 24;
  const bw = Math.max(6, cw * 0.62);
  const y = (v) => padT + (H - padT - padB) * (1 - v / top);
  const isToday = data.date === todayLocal();
  const nowH = currentHour();
  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for (let i = 0; i <= 4; i++) {
    const v = step * i, yy = y(v);
    svg += `<line class="grid" x1="${padL}" x2="${W - padR}" y1="${yy}" y2="${yy}"/><text x="${padL - 6}" y="${yy + 4}" text-anchor="end">${v}</text>`;
  }
  data.buckets.forEach((b) => {
    const x = padL + b.hour * cw + (cw - bw) / 2;
    const h = (H - padT - padB) * (b.count / top);
    const cls = isToday && b.hour === nowH ? "bar now" : "bar";
    svg += `<rect class="${cls}" x="${x}" y="${y(b.count)}" width="${bw}" height="${Math.max(0, h)}" rx="3"><title>${b.hour}h–${b.hour + 1}h: ${b.count} lượt</title></rect>`;
    if (b.count > 0) svg += `<text class="val" x="${x + bw / 2}" y="${y(b.count) - 5}" text-anchor="middle">${b.count}</text>`;
    if (b.hour % 2 === 0) svg += `<text x="${padL + b.hour * cw + cw / 2}" y="${H - 8}" text-anchor="middle">${b.hour}h</text>`;
  });
  svg += "</svg>";
  $("chart").innerHTML = svg;
  const peak = data.buckets.reduce((a, b) => (b.count > a.count ? b : a), { hour: -1, count: 0 });
  $("chart-total").textContent = `Tổng: ${data.total} lượt` + (peak.count ? ` · Cao điểm ${peak.hour}h–${peak.hour + 1}h (${peak.count} lượt)` : "")
    + (data.since_reset && data.last_reset_at ? ` · tính từ ${fmtTime(data.last_reset_at)}` : "");
}

function passageRow(p, fresh = false) {
  return `<tr class="${fresh ? "fresh" : ""}"><td>${fmtDateTime(p.occurred_at)}</td><td>${num(p.min_distance_cm, " cm")}</td>`
    + `<td>${num(p.baseline_cm, " cm")}</td><td>${p.duration_ms != null ? p.duration_ms + " ms" : "–"}</td></tr>`;
}

function renderPassages(page) {
  $("passages-total").textContent = `${page.total} lượt / 24 giờ`;
  $("passages-body").innerHTML = page.items.length
    ? page.items.map((p) => passageRow(p)).join("")
    : `<tr><td colspan="4" class="muted">Chưa có lượt nào</td></tr>`;
}

function renderAlerts(alerts) {
  const open = alerts.filter((a) => !a.is_resolved).slice(0, 8);
  $("alerts-list").innerHTML = open.length ? open.map((a) => `
    <li><span>${esc(a.message)}<br><span class="muted small">${fmtDateTime(a.created_at)}</span></span>
    <button class="btn ghost" data-resolve="${a.id}">Đã xử lý</button></li>`).join("") : `<li class="muted">Không có cảnh báo</li>`;
}

const CMD_STATUS = { pending: "chờ gửi", sent: "đã gửi", success: "thành công", failed: "thất bại", superseded: "bị thay" };
function renderCommands(cmds) {
  $("cmd-list").innerHTML = cmds.length ? cmds.slice(0, 6).map((c) => `
    <li><span>Đặt lại số đếm · <span class="muted small">${fmtDateTime(c.created_at)} · ${esc(c.triggered_by)}</span></span>
    <span class="tag ${c.status}">${CMD_STATUS[c.status] || c.status}</span></li>`).join("") : `<li class="muted">Chưa có lệnh</li>`;
}

/* ---------------- tải dữ liệu ---------------- */
async function loadSummary() {
  const s = await api(`/api/v1/stats/summary?device_id=${state.deviceId}`);
  state.lastResetAt = s.last_reset_at;
  renderCount(s.count_today, s.last_reset_at, s.total_today_before_reset);
  renderDevice(s.device);
}
async function loadChart() {
  const date = $("chart-date").value || todayLocal();
  const sr = $("since-reset").checked;
  renderChart(await api(`/api/v1/stats/hourly?device_id=${state.deviceId}&date=${date}&since_reset=${sr}`));
}
async function loadPassages() { renderPassages(await api(`/api/v1/passages?device_id=${state.deviceId}&limit=30`)); }
async function loadAlerts() { renderAlerts(await api(`/api/v1/alerts?device_id=${state.deviceId}&resolved=false`)); }
async function loadCommands() { renderCommands(await api(`/api/v1/devices/${state.deviceId}/control-logs?limit=10`)); }

async function refreshAll() {
  if (!state.deviceId) return;
  const results = await Promise.allSettled([loadSummary(), loadChart(), loadPassages(), loadAlerts(), loadCommands()]);
  results.filter((r) => r.status === "rejected").forEach((r) => console.warn(r.reason));
}
const refreshChartSoon = debounce(() => loadChart().catch(console.warn), 400);
const refreshCmdsSoon = debounce(() => loadCommands().catch(console.warn), 300);

async function loadDevices() {
  state.devices = await api("/api/v1/devices");
  const sel = $("device-select");
  sel.innerHTML = state.devices.map((d) => `<option value="${d.id}">${esc(d.name)} (${esc(d.device_uid)})</option>`).join("");
  const saved = Number(store.get("deviceId"));
  state.deviceId = state.devices.some((d) => d.id === saved) ? saved : state.devices[0]?.id ?? null;
  if (state.deviceId) sel.value = String(state.deviceId);
}
$("device-select").addEventListener("change", (e) => {
  state.deviceId = Number(e.target.value);
  store.set("deviceId", state.deviceId);
  refreshAll();
});
$("chart-date").addEventListener("change", () => loadChart().catch(console.warn));
$("since-reset").addEventListener("change", () => loadChart().catch(console.warn));

/* ---------------- nút đặt lại (bấm 2 lần để xác nhận) ---------------- */
let resetArmed = null;
function disarmReset() {
  clearTimeout(resetArmed); resetArmed = null;
  $("reset-btn").classList.remove("confirm");
  $("reset-btn").textContent = "Đặt lại số đếm";
  $("reset-cancel").hidden = true;
}
$("reset-cancel").addEventListener("click", disarmReset);
$("reset-btn").addEventListener("click", async () => {
  if (!resetArmed) {
    $("reset-btn").classList.add("confirm");
    $("reset-btn").textContent = "Bấm lần nữa để xác nhận";
    $("reset-cancel").hidden = false;
    resetArmed = setTimeout(disarmReset, 5000);
    return;
  }
  disarmReset();
  const btn = $("reset-btn");
  btn.disabled = true;
  try {
    const r = await api(`/api/v1/devices/${state.deviceId}/control`, { method: "POST", body: JSON.stringify({ command: "reset_counter" }) });
    renderCount(r.count_today, r.command.created_at);
    $("reset-msg").textContent = r.delivered_via.includes("mqtt")
      ? "Đã gửi lệnh tới thiết bị qua MQTT."
      : "Server đã về 0. Thiết bị sẽ nhận lệnh ở lần gửi dữ liệu kế tiếp.";
    await Promise.allSettled([loadChart(), loadCommands()]);
  } catch (err) {
    $("reset-msg").textContent = `Lỗi: ${err.message}`;
  } finally { btn.disabled = false; }
});

/* ---------------- xuất CSV ---------------- */
$("export-btn").addEventListener("click", async () => {
  const date = $("chart-date").value || todayLocal();
  const from = `${date}T00:00:00`;
  const d = new Date(`${date}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1);
  const to = `${d.toISOString().slice(0, 10)}T00:00:00`;
  try {
    const res = await api(`/api/v1/passages/export.csv?device_id=${state.deviceId}&from=${from}&to=${to}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `luot_qua_cua_${date}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (err) { $("chart-total").textContent = `Xuất CSV lỗi: ${err.message}`; }
});

/* ---------------- cảnh báo: đánh dấu đã xử lý ---------------- */
$("alerts-list").addEventListener("click", async (e) => {
  const id = e.target?.dataset?.resolve;
  if (!id) return;
  try { await api(`/api/v1/alerts/${id}/resolve`, { method: "POST" }); await loadAlerts(); } catch (err) { console.warn(err); }
});

/* ---------------- WebSocket realtime ---------------- */
function setLive(on) {
  const el = $("ws-status");
  el.className = `live ${on ? "on" : "off"}`;
  el.textContent = on ? "● Realtime" : "● Mất kết nối";
}

function connectWs() {
  if (!state.token) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(state.token)}`);
  state.ws = ws;
  let pinger;
  ws.onopen = () => { state.wsRetry = 0; setLive(true); pinger = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000); };
  ws.onmessage = (ev) => {
    if (ev.data === "pong") return;
    let msg; try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.device_id !== state.deviceId) return;
    handleEvent(msg);
  };
  ws.onclose = (ev) => {
    clearInterval(pinger);
    setLive(false);
    if (ev.code === 1008) { logout(); return; }
    const wait = Math.min(30000, 1000 * 2 ** state.wsRetry++);
    setTimeout(() => { if (state.token) { connectWs(); refreshAll(); } }, wait);
  };
}

function handleEvent(msg) {
  const d = msg.data || {};
  switch (msg.type) {
    case "passage": {
      renderCount(d.count_today, state.lastResetAt);
      const body = $("passages-body");
      if (body.querySelector("td[colspan]")) body.innerHTML = "";
      body.insertAdjacentHTML("afterbegin", passageRow(d, true));
      while (body.rows.length > 30) body.deleteRow(-1);
      refreshChartSoon();
      break;
    }
    case "room_state":
    case "device_status":
      renderDevice(d);
      if (d.count_today !== undefined) $("count-today").textContent = d.count_today;
      break;
    case "counter_reset":
      state.lastResetAt = d.last_reset_at;
      renderCount(d.count_today, d.last_reset_at);
      refreshChartSoon();
      refreshCmdsSoon();
      break;
    case "command":
      refreshCmdsSoon();
      break;
    case "command_ack":
      if (d.command === "reset_counter") {
        $("reset-msg").textContent = d.status === "success"
          ? `Thiết bị đã xác nhận đặt lại lúc ${fmtTime(d.acked_at)}.`
          : `Thiết bị báo đặt lại thất bại: ${d.detail || "không rõ lý do"}`;
      }
      refreshCmdsSoon();
      break;
    case "alert":
      loadAlerts().catch(console.warn);
      break;
  }
}

/* ---------------- khởi động ---------------- */
async function start() {
  if (!state.token) { showLogin(); return; }
  try {
    await api("/api/v1/auth/me");
  } catch { return; } // api() đã chuyển về màn đăng nhập nếu 401
  showApp();
  $("chart-date").value = todayLocal();
  await loadDevices();
  await refreshAll();
  if (!state.ws) connectWs();
  clearInterval(state.refreshTimer);
  // làm mới định kỳ: cập nhật "x giây trước", qua ngày mới, và phòng khi WS rớt
  state.refreshTimer = setInterval(() => {
    if (state.device) renderDevice(state.device);
    if (!state.ws || state.ws.readyState !== 1) refreshAll();
  }, 15000);
}

start();
