const PALETTE = ["#0ea5a4", "#f59e0b", "#22c55e", "#38bdf8", "#f472b6"];

const STATUS_TEXT = {
  launching: "启动中",
  running: "运行中",
  stopping: "停止中",
  stopped: "已停止",
  error: "异常",
};

const state = {
  profiles: [],
  sessions: [],
  selectedId: null,
  selectedColor: PALETTE[0],
  engine: { available: false, version: null },
  selectedIds: new Set(),
};

const $ = (id) => document.getElementById(id);

let formDirty = false;
let apiTokenPromise = null;

function getApiToken() {
  if (!apiTokenPromise) {
    apiTokenPromise = (async () => {
      try {
        if (
          window.pywebview &&
          window.pywebview.api &&
          typeof window.pywebview.api.get_api_token === "function"
        ) {
          return await window.pywebview.api.get_api_token();
        }
      } catch (error) {
        // fall through to localStorage for headless/browser testing
      }
      return localStorage.getItem("zencloak_api_token") || "";
    })();
  }
  return apiTokenPromise;
}

async function api(path, options = {}) {
  const token = await getApiToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const response = await fetch(path, {
    headers,
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && (data.detail || data.message);
    throw new Error(detail || `请求失败 (${response.status})`);
  }
  return data;
}

function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => el.classList.remove("show"), 2600);
}

function statusOf(profileId) {
  return state.sessions.find((s) => s.profile_id === profileId) || {
    status: "stopped",
    started_at: null,
    stopped_at: null,
    error: null,
  };
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

async function loadEngine() {
  state.engine = await api("/api/engine");
  const dot = $("engineDot");
  const version = $("engineVersion");
  const label = $("engineLabel");
  dot.classList.toggle("ok", state.engine.available);
  dot.classList.toggle("bad", !state.engine.available);
  version.textContent = state.engine.available
    ? `CloakBrowser ${state.engine.version || ""}`.trim()
    : "引擎不可用";
  label.textContent = state.engine.available ? "引擎就绪" : "引擎检测中";
}

async function loadProfiles() {
  state.profiles = await api("/api/profiles");
  const activeIds = new Set(state.profiles.map((p) => p.id));
  for (const id of state.selectedIds) {
    if (!activeIds.has(id)) state.selectedIds.delete(id);
  }
  updateBatchButtons();
  if (!state.selectedId || !state.profiles.some((p) => p.id === state.selectedId)) {
    state.selectedId = state.profiles[0] ? state.profiles[0].id : null;
  }
  renderProfileList();
  renderForm();
}

function renderProfileList() {
  const list = $("profileList");
  list.innerHTML = "";
  for (const profile of state.profiles) {
    const item = document.createElement("button");
    item.className = "profile-item" + (profile.id === state.selectedId ? " active" : "");
    item.type = "button";
    item.dataset.profileId = profile.id;
    const status = statusOf(profile.id);
    item.innerHTML = `
      <input type="checkbox" class="profile-check" data-profile-id="${profile.id}" aria-label="选择档案">
      <span class="pcolor" style="background:${profile.color}"></span>
      <span class="pname">${escapeHtml(profile.name)}<small>指纹 ${profile.seed}</small></span>
      <span class="pstatus ${status.status}"></span>
    `;
    const check = item.querySelector(".profile-check");
    check.checked = state.selectedIds.has(profile.id);
    check.addEventListener("click", (event) => event.stopPropagation());
    check.addEventListener("change", () => {
      if (check.checked) {
        state.selectedIds.add(profile.id);
      } else {
        state.selectedIds.delete(profile.id);
      }
      updateBatchButtons();
    });
    item.addEventListener("click", () => selectProfile(profile.id));
    list.appendChild(item);
  }
  $("profileTitle").textContent = state.selectedId
    ? state.profiles.find((p) => p.id === state.selectedId)?.name || "未选择档案"
    : "未选择档案";
}

function updateBatchButtons() {
  const hasSelection = state.selectedIds.size > 0;
  $("batchLaunchBtn").disabled = !hasSelection;
  $("batchStopBtn").disabled = !hasSelection;
}

function updateProfileStatuses() {
  for (const item of document.querySelectorAll(".profile-item")) {
    const profileId = item.dataset.profileId;
    if (!profileId) continue;
    const status = statusOf(profileId);
    const dot = item.querySelector(".pstatus");
    if (dot) dot.className = "pstatus " + status.status;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectProfile(id) {
  if (state.selectedId === id) {
    loadSessions();
    return;
  }
  if (formDirty) {
    const keep = window.confirm("当前档案有未保存的修改，确定放弃吗？");
    if (!keep) return;
    formDirty = false;
  }
  state.selectedId = id;
  renderProfileList();
  renderForm();
  loadSessions();
}

function renderForm() {
  const profile = state.profiles.find((p) => p.id === state.selectedId);
  const hasProfile = Boolean(profile);
  $("saveBtn").disabled = !hasProfile;
  $("launchBtn").disabled = !hasProfile;
  $("deleteBtn").disabled = !hasProfile;
  $("stopBtn").disabled = true;
  $("duplicateBtn").disabled = !hasProfile;
  $("exportBtn").disabled = !hasProfile;
  if (!profile) {
    $("profileForm").reset();
    $("colorPicker").innerHTML = "";
    $("statusBadge").textContent = "已停止";
    formDirty = false;
    return;
  }
  $("name").value = profile.name || "";
  $("startUrl").value = profile.start_url || "";
  $("notes").value = profile.notes || "";
  $("seed").value = profile.seed;
  $("timezone").value = profile.timezone;
  $("locale").value = profile.locale;
  $("screen").value = `${profile.screen_width}x${profile.screen_height}`;
  $("hardwareConcurrency").value = String(profile.hardware_concurrency);
  $("deviceMemory").value = String(profile.device_memory);
  $("userAgent").value = profile.user_agent || "";
  $("humanize").checked = Boolean(profile.humanize);
  $("humanPreset").value = profile.human_preset || "default";
  const proxy = profile.proxy;
  $("proxyEnabled").checked = Boolean(proxy);
  $("proxyType").value = proxy ? proxy.type : "http";
  $("proxyHost").value = proxy ? proxy.host : "";
  $("proxyPort").value = proxy ? proxy.port : "";
  $("proxyUsername").value = proxy ? proxy.username || "" : "";
  $("proxyPassword").value = proxy ? proxy.password || "" : "";
  renderColorSwatches(profile.color || PALETTE[0]);
  setProxyEnabled(Boolean(proxy));
  formDirty = false;
  renderSessionControls();
}

function renderColorSwatches(activeColor) {
  state.selectedColor = activeColor;
  const picker = $("colorPicker");
  picker.innerHTML = "";
  for (const color of PALETTE) {
    const swatch = document.createElement("button");
    swatch.type = "button";
    swatch.className = "swatch" + (color === activeColor ? " active" : "");
    swatch.style.background = color;
    swatch.title = color;
    swatch.addEventListener("click", () => {
      state.selectedColor = color;
      formDirty = true;
      renderColorSwatches(color);
    });
    picker.appendChild(swatch);
  }
}

function setProxyEnabled(enabled) {
  $("proxyType").disabled = !enabled;
  $("proxyHost").disabled = !enabled;
  $("proxyPort").disabled = !enabled;
  $("proxyUsername").disabled = !enabled;
  $("proxyPassword").disabled = !enabled;
}

async function loadSessions() {
  try {
    state.sessions = await api("/api/sessions");
  } catch (error) {
    return;
  }
  updateProfileStatuses();
  renderSessionControls();
}

function renderSessionControls() {
  if (!state.selectedId) return;
  const session = statusOf(state.selectedId);
  const badge = $("statusBadge");
  badge.className = "badge " + session.status;
  badge.textContent = STATUS_TEXT[session.status] || session.status;
  if (session.status === "error" && session.error) {
    badge.title = session.error;
    $("statusTime").textContent = session.error;
  } else {
    badge.title = "";
    $("statusTime").textContent =
      session.status === "running" && session.started_at
        ? `启动于 ${formatTime(session.started_at)}`
        : session.status === "stopped" && session.stopped_at
          ? `停止于 ${formatTime(session.stopped_at)}`
          : "";
  }
  const running = session.status === "running" || session.status === "launching";
  $("launchBtn").disabled = running;
  $("stopBtn").disabled = !running;
  $("deleteBtn").disabled = Boolean(running);
}

function readForm() {
  const screen = $("screen").value.split("x").map(Number);
  const proxyEnabled = $("proxyEnabled").checked;
  return {
    name: $("name").value.trim() || "未命名档案",
    color: state.selectedColor,
    notes: $("notes").value,
    seed: Number($("seed").value),
    timezone: $("timezone").value,
    locale: $("locale").value,
    screen_width: screen[0],
    screen_height: screen[1],
    hardware_concurrency: Number($("hardwareConcurrency").value),
    device_memory: Number($("deviceMemory").value),
    user_agent: $("userAgent").value.trim() || null,
    start_url: $("startUrl").value.trim() || null,
    proxy: proxyEnabled
      ? {
          type: $("proxyType").value,
          host: $("proxyHost").value.trim(),
          port: Number($("proxyPort").value),
          username: $("proxyUsername").value.trim(),
          password: $("proxyPassword").value,
        }
      : null,
    humanize: $("humanize").checked,
    human_preset: $("humanPreset").value,
    headless: false,
  };
}

async function createProfile() {
  try {
    const created = await api("/api/profiles", {
      method: "POST",
      body: JSON.stringify({ name: "新档案" }),
    });
    state.selectedId = created.id;
    await loadProfiles();
    await loadSessions();
    toast("已创建新档案");
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveProfile() {
  if (!state.selectedId) return false;
  try {
    const payload = readForm();
    const updated = await api(`/api/profiles/${state.selectedId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    const index = state.profiles.findIndex((p) => p.id === updated.id);
    if (index >= 0) state.profiles[index] = updated;
    renderProfileList();
    renderForm();
    formDirty = false;
    toast("档案已保存");
    return true;
  } catch (error) {
    toast(error.message, true);
    return false;
  }
}

async function deleteProfile() {
  if (!state.selectedId) return;
  const profile = state.profiles.find((p) => p.id === state.selectedId);
  if (!window.confirm(`将档案「${profile ? profile.name : ""}」移入回收站？`)) return;
  try {
    await api(`/api/profiles/${state.selectedId}`, { method: "DELETE" });
    state.selectedId = null;
    await loadProfiles();
    await loadSessions();
    toast("档案已移入回收站");
  } catch (error) {
    toast(error.message, true);
  }
}

async function duplicateProfile() {
  if (!state.selectedId) return;
  try {
    const duplicated = await api(`/api/profiles/${state.selectedId}/duplicate`, {
      method: "POST",
    });
    state.selectedId = duplicated.id;
    await loadProfiles();
    await loadSessions();
    toast("已复制档案");
  } catch (error) {
    toast(error.message, true);
  }
}

function safeFileName(name) {
  return String(name || "profile").replace(/[\\/:*?"<>|]/g, "-");
}

async function exportProfile() {
  if (!state.selectedId) return;
  try {
    const data = await api(`/api/profiles/${state.selectedId}/export`);
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `zencloak-${safeFileName(data.name)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    toast("档案已导出");
  } catch (error) {
    toast(error.message, true);
  }
}

function pickImportFile() {
  $("importFile").click();
}

async function importProfileFromFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const created = await api("/api/profiles/import", {
      method: "POST",
      body: JSON.stringify(data),
    });
    state.selectedId = created.id;
    await loadProfiles();
    await loadSessions();
    toast("档案已导入");
  } catch (error) {
    toast(error.message, true);
  } finally {
    event.target.value = "";
  }
}

async function batchLaunch() {
  const ids = Array.from(state.selectedIds);
  if (!ids.length) return;
  try {
    const results = await api("/api/sessions/batch-launch", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
    const failed = results.filter((item) => !item.ok);
    toast(failed.length ? `${failed.length} 个档案启动失败` : "已批量启动");
    await loadSessions();
  } catch (error) {
    toast(error.message, true);
  }
}

async function batchStop() {
  const ids = Array.from(state.selectedIds);
  if (!ids.length) return;
  try {
    const results = await api("/api/sessions/batch-stop", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
    const failed = results.filter((item) => !item.ok);
    toast(failed.length ? `${failed.length} 个档案停止失败` : "已批量停止");
    await loadSessions();
  } catch (error) {
    toast(error.message, true);
  }
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { hour12: false });
}

async function showRecycleBin() {
  $("recycleView").hidden = false;
  document.querySelector(".panel").hidden = true;
  document.querySelector(".detect-wrap").hidden = true;
  document.querySelector(".toolbar").hidden = true;
  await loadRecycleBin();
}

function hideRecycleBin() {
  $("recycleView").hidden = true;
  document.querySelector(".panel").hidden = false;
  document.querySelector(".detect-wrap").hidden = false;
  document.querySelector(".toolbar").hidden = false;
}

async function loadRecycleBin() {
  try {
    const items = await api("/api/recycle-bin");
    const list = $("recycleList");
    list.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "recycle-empty";
      empty.textContent = "回收站是空的";
      list.appendChild(empty);
      return;
    }
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "recycle-item";
      row.innerHTML = `
        <div class="recycle-info">
          <strong>${escapeHtml(item.name)}</strong>
          <small>${escapeHtml(formatDateTime(item.deleted_at))}</small>
        </div>
        <div class="recycle-actions">
          <button class="btn" type="button" data-action="restore"><i data-lucide="rotate-ccw"></i>恢复</button>
          <button class="btn danger" type="button" data-action="delete"><i data-lucide="trash-2"></i>永久删除</button>
        </div>
      `;
      row
        .querySelector('[data-action="restore"]')
        .addEventListener("click", () => restoreProfile(item.id));
      row
        .querySelector('[data-action="delete"]')
        .addEventListener("click", () => permanentDeleteProfile(item.id));
      list.appendChild(row);
    }
    if (window.lucide) window.lucide.createIcons();
  } catch (error) {
    toast(error.message, true);
  }
}

async function restoreProfile(profileId) {
  try {
    await api(`/api/recycle-bin/${profileId}/restore`, { method: "POST" });
    toast("已恢复档案");
    await loadRecycleBin();
    await loadProfiles();
  } catch (error) {
    toast(error.message, true);
  }
}

async function permanentDeleteProfile(profileId) {
  if (!window.confirm("永久删除后无法恢复，确定吗？")) return;
  try {
    await api(`/api/recycle-bin/${profileId}`, { method: "DELETE" });
    toast("已永久删除");
    await loadRecycleBin();
  } catch (error) {
    toast(error.message, true);
  }
}

async function launchProfile() {
  if (!state.selectedId) return;
  if (formDirty) {
    const saved = await saveProfile();
    if (!saved) return;
  }
  try {
    await api(`/api/sessions/${state.selectedId}/launch`, { method: "POST" });
    await loadSessions();
    toast("浏览器正在启动");
  } catch (error) {
    toast(error.message, true);
  }
}

async function stopProfile() {
  if (!state.selectedId) return;
  try {
    await api(`/api/sessions/${state.selectedId}/stop`, { method: "POST" });
    await loadSessions();
    toast("浏览器已停止");
  } catch (error) {
    toast(error.message, true);
  }
}

async function openDetectUrl(url) {
  if (!state.selectedId) return;
  const session = statusOf(state.selectedId);
  if (session.status !== "running") {
    toast("请先启动档案", true);
    return;
  }
  try {
    const result = await api(`/api/sessions/${state.selectedId}/open`, {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    if (result && result.opened === false) {
      toast("页面打开失败", true);
      return;
    }
    toast("页面已打开");
  } catch (error) {
    toast(error.message, true);
  }
}

function markFormDirty() {
  formDirty = true;
}

function bindEvents() {
  $("newProfileBtn").addEventListener("click", createProfile);
  $("saveBtn").addEventListener("click", saveProfile);
  $("launchBtn").addEventListener("click", launchProfile);
  $("stopBtn").addEventListener("click", stopProfile);
  $("deleteBtn").addEventListener("click", deleteProfile);
  $("duplicateBtn").addEventListener("click", duplicateProfile);
  $("exportBtn").addEventListener("click", exportProfile);
  $("importProfileBtn").addEventListener("click", pickImportFile);
  $("importFile").addEventListener("change", importProfileFromFile);
  $("batchLaunchBtn").addEventListener("click", batchLaunch);
  $("batchStopBtn").addEventListener("click", batchStop);
  $("recycleBinBtn").addEventListener("click", showRecycleBin);
  $("recycleBackBtn").addEventListener("click", hideRecycleBin);
  $("profileForm").addEventListener("input", markFormDirty);
  $("profileForm").addEventListener("change", markFormDirty);
  $("proxyEnabled").addEventListener("change", (event) => {
    formDirty = true;
    setProxyEnabled(event.target.checked);
  });

  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", String(t === tab));
      });
      document.querySelectorAll(".view").forEach((view) => {
        view.classList.toggle("active", view.dataset.view === tab.dataset.tab);
      });
    });
  }

  for (const button of document.querySelectorAll(".detect-btn")) {
    button.addEventListener("click", () => openDetectUrl(button.dataset.url));
  }
}

async function init() {
  bindEvents();
  if (window.lucide) window.lucide.createIcons();
  try {
    await Promise.all([loadEngine(), loadProfiles(), loadSessions()]);
  } catch (error) {
    toast(error.message, true);
  }
  setInterval(loadSessions, 2000);
}

init();
