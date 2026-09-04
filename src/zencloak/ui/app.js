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
  subscriptions: [],
  nodes: [],
  nodeLatency: {},
  selectedId: null,
  selectedColor: PALETTE[0],
  engine: { available: false, version: null },
  selectedIds: new Set(),
};

const $ = (id) => document.getElementById(id);

let formDirty = false;
let cachedApiToken = null;

function waitForPywebview() {
  return new Promise((resolve) => {
    if (!window.pywebview || window.pywebview.api) {
      resolve();
      return;
    }
    const onReady = () => {
      window.removeEventListener("pywebviewready", onReady);
      resolve();
    };
    window.addEventListener("pywebviewready", onReady);
    setTimeout(resolve, 1500);
  });
}

async function getApiToken() {
  if (cachedApiToken) return cachedApiToken;
  await waitForPywebview();
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    try {
      if (window.pywebview && window.pywebview.api) {
        const bridge = window.pywebview.api;
        const getter = bridge.get_api_token || bridge.getApiToken;
        if (typeof getter === "function") {
          const token = await getter();
          if (token) {
            cachedApiToken = token;
            return token;
          }
        }
      }
    } catch (error) {
      // bridge not ready yet; retry below
    }
    const token = localStorage.getItem("zencloak_api_token") || "";
    if (token) {
      cachedApiToken = token;
      return token;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return localStorage.getItem("zencloak_api_token") || "";
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
  $("downloadsBtn").disabled = !hasProfile;
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
  $("translateButton").checked = Boolean(profile.translate_button);
  $("cdpAttach").checked = Boolean(profile.cdp_attach);
  $("spoofVoices").checked = profile.spoof_voices !== false;
  const proxy = profile.proxy;
  const builtinProxy = Boolean(profile.proxy_enabled) && profile.proxy_mode === "mihomo";
  $("proxyBuiltin").checked = builtinProxy;
  state.selectedSubscriptionId = profile.proxy_subscription_id || "";
  $("proxySubscription").value = state.selectedSubscriptionId || "";
  $("proxyRegion").value = profile.proxy_region || "";
  setNodeValue(profile.proxy_node);
  setProxyBuiltinEnabled(builtinProxy);
  if (state.selectedSubscriptionId) {
    loadNodes(state.selectedSubscriptionId).then(() => {
      $("proxyRegion").value = profile.proxy_region || "";
      setNodeValue(profile.proxy_node);
    });
  } else {
    state.nodes = [];
    renderRegionOptions();
    renderNodeOptions();
  }
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

function setProxyBuiltinEnabled(enabled) {
  $("builtinProxySection").hidden = !enabled;
  $("manualProxySection").hidden = Boolean(enabled);
  $("proxyImportUrl").disabled = !enabled;
  $("proxyImportBtn").disabled = !enabled;
  $("proxySubscription").disabled = !enabled;
  $("proxyRegion").disabled = !enabled;
  setNodeDisabled(!enabled);
  $("proxyTestBtn").disabled = !enabled;
  $("proxyRefreshBtn").disabled = !enabled;
  $("proxyDeleteBtn").disabled = !enabled;
}

const REGION_LABELS = {
  US: "🇺🇸 美国",
  HK: "🇭🇰 香港",
  JP: "🇯🇵 日本",
  SG: "🇸🇬 新加坡",
  TW: "🇹🇼 台湾",
  KR: "🇰🇷 韩国",
  DE: "🇩🇪 德国",
  GB: "🇬🇧 英国",
};

function regionLabel(region) {
  return REGION_LABELS[region] || region;
}

function renderSubscriptionOptions() {
  const select = $("proxySubscription");
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "选择订阅";
  select.appendChild(empty);
  for (const item of state.subscriptions) {
    const option = document.createElement("option");
    option.value = item.id;
    const count = (item.nodes || []).length;
    option.textContent = `${item.name || item.id}（${count} 节点）`;
    select.appendChild(option);
  }
  select.value = state.selectedSubscriptionId || "";
  if (select.value) {
    loadNodes(select.value);
  } else {
    state.nodes = [];
    renderNodeOptions();
  }
}

function nodeLatencyHtml(name) {
  const latency = state.nodeLatency[name];
  if (!latency) return "";
  if (latency.error) return `<span class="node-latency fail">连接失败</span>`;
  return `<span class="node-latency ok">${escapeHtml(latency.ms)} ms</span>`;
}

function getNodeValue() {
  return state.selectedNode || "";
}

function setNodeValue(name) {
  state.selectedNode = name || "";
  renderNodeOptions();
}

function setNodeDisabled(disabled) {
  $("proxyNodeTrigger").disabled = disabled;
  if (disabled) closeNodeList();
}

function renderNodeOptions() {
  const region = $("proxyRegion").value;
  const filtered = region
    ? state.nodes.filter((node) => node.region === region)
    : state.nodes;
  if (!filtered.some((node) => node.name === state.selectedNode)) {
    state.selectedNode = "";
  }
  const trigger = $("proxyNodeTrigger");
  trigger.innerHTML = state.selectedNode
    ? `<span class="node-name">${escapeHtml(state.selectedNode)}</span>${nodeLatencyHtml(state.selectedNode)}`
    : `<span class="node-name placeholder">${filtered.length ? `选择节点（${filtered.length} 个）` : "选择节点"}</span>`;
  const list = $("proxyNodeList");
  list.innerHTML = "";
  for (const node of filtered) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "node-row" + (node.name === state.selectedNode ? " active" : "");
    row.innerHTML =
      `<span class="node-name">${escapeHtml(node.name)}</span>` +
      `<span class="node-meta">${escapeHtml(node.type || "")}${node.region ? ` · ${escapeHtml(regionLabel(node.region))}` : ""}</span>` +
      nodeLatencyHtml(node.name);
    row.addEventListener("click", () => {
      state.selectedNode = node.name;
      markFormDirty();
      renderNodeOptions();
      closeNodeList();
    });
    list.appendChild(row);
  }
}

function closeNodeList() {
  const list = $("proxyNodeList");
  if (list) list.hidden = true;
}

function closeMoreMenu() {
  const menu = $("moreMenu");
  if (!menu) return;
  menu.hidden = true;
  $("moreBtn").setAttribute("aria-expanded", "false");
}

function renderRegionOptions() {
  const select = $("proxyRegion");
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "全部地区";
  select.appendChild(empty);
  const regions = Array.from(new Set(state.nodes.map((node) => node.region).filter(Boolean)));
  for (const region of regions) {
    const option = document.createElement("option");
    option.value = region;
    const count = state.nodes.filter((node) => node.region === region).length;
    option.textContent = `${regionLabel(region)}（${count}）`;
    select.appendChild(option);
  }
}

async function loadSubscriptions() {
  try {
    state.subscriptions = await api("/api/proxy/subscriptions");
  } catch (error) {
    state.subscriptions = [];
  }
  renderSubscriptionOptions();
}

async function loadNodes(subscriptionId) {
  state.nodeLatency = {};
  if (!subscriptionId) {
    state.nodes = [];
    renderNodeOptions();
    renderRegionOptions();
    return;
  }
  try {
    state.nodes = await api(`/api/proxy/subscriptions/${subscriptionId}/nodes`);
  } catch (error) {
    state.nodes = [];
    toast(error.message, true);
  }
  renderRegionOptions();
  renderNodeOptions();
}

async function importSubscription() {
  const url = $("proxyImportUrl").value.trim();
  if (!url) return;
  try {
    const meta = await api("/api/proxy/subscriptions/import", {
      method: "POST",
      body: JSON.stringify({ url, name: subscriptionNameFromUrl(url) }),
    });
    state.subscriptions.push(meta);
    state.selectedSubscriptionId = meta.id;
    renderSubscriptionOptions();
    toast(`订阅已导入（${meta.nodes.length} 节点）`);
  } catch (error) {
    toast(error.message, true);
  }
}

function subscriptionNameFromUrl(url) {
  try {
    return new URL(url).hostname;
  } catch (error) {
    return "我的订阅";
  }
}

async function refreshSubscription() {  const subId = $("proxySubscription").value;
  if (!subId) return;
  const button = $("proxyRefreshBtn");
  button.disabled = true;
  try {
    const meta = await api(`/api/proxy/subscriptions/${subId}/refresh`, {
      method: "POST",
    });
    const index = state.subscriptions.findIndex((item) => item.id === meta.id);
    if (index >= 0) state.subscriptions[index] = meta;
    renderSubscriptionOptions();
    await loadNodes(subId);
    const failed = Object.entries(meta.providers || {}).filter(([, status]) =>
      !status.startsWith("ok")
    );
    toast(
      failed.length
        ? `已刷新 ${meta.nodes.length} 节点，${failed.length} 个机场失败`
        : `已刷新 ${meta.nodes.length} 节点`
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function deleteSubscription() {
  const subId = $("proxySubscription").value;
  if (!subId) return;
  const sub = state.subscriptions.find((item) => item.id === subId);
  const label = sub ? sub.name || subId : subId;
  if (!window.confirm(`删除订阅「${label}」？档案将不再能使用它的节点。`)) return;
  try {
    await api(`/api/proxy/subscriptions/${subId}`, { method: "DELETE" });
    state.subscriptions = state.subscriptions.filter((item) => item.id !== subId);
    if (state.selectedSubscriptionId === subId) {
      state.selectedSubscriptionId = "";
      $("proxySubscription").value = "";
      await loadNodes("");
    }
    renderSubscriptionOptions();
    toast("订阅已删除");
  } catch (error) {
    toast(error.message, true);
  }
}

async function testNode() {
  const subId = $("proxySubscription").value;
  const node = getNodeValue();
  const region = $("proxyRegion").value;
  if (!subId) return;
  const targets = region
    ? state.nodes.filter((item) => item.region === region).map((item) => item.name)
    : node
      ? [node]
      : [];
  if (!targets.length) {
    toast("请先选择地区或节点", true);
    return;
  }
  const status = $("proxyStatusText");
  const button = $("proxyTestBtn");
  button.disabled = true;
  try {
    if (targets.length === 1 && !region) {
      const result = await api("/api/proxy/nodes/test", {
        method: "POST",
        body: JSON.stringify({ subscription_id: subId, node: targets[0] }),
      });
      state.nodeLatency[targets[0]] = { ms: result.latency_ms };
      status.textContent = `${targets[0]} 延迟 ${result.latency_ms} ms`;
    } else {
      status.textContent = `正在测速 ${targets.length} 个节点…`;
      const response = await api("/api/proxy/nodes/test-batch", {
        method: "POST",
        body: JSON.stringify({ subscription_id: subId, nodes: targets }),
      });
      let ok = 0;
      for (const item of response.results) {
        if (item.error) {
          state.nodeLatency[item.node] = { error: item.error };
        } else {
          state.nodeLatency[item.node] = { ms: item.latency_ms };
          ok += 1;
        }
      }
      const best = response.results
        .filter((item) => item.latency_ms != null)
        .sort((a, b) => a.latency_ms - b.latency_ms)[0];
      status.textContent = best
        ? `已测 ${response.results.length} 个（${ok} 个连通），最快：${best.node} ${best.latency_ms} ms`
        : `已测 ${response.results.length} 个，全部连接失败`;
    }
    renderNodeOptions();
  } catch (error) {
    toast(error.message, true);
    status.textContent = "";
  } finally {
    button.disabled = false;
  }
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
  $("healthBtn").disabled = session.status !== "running";
  updateConsistencyBanner();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

// 一致性预检按 (档案, 本次启动) 缓存，避免轮询时反复请求 IP 归属接口
async function updateConsistencyBanner() {
  const banner = $("consistencyBanner");
  if (!banner || !state.selectedId) return;
  const session = statusOf(state.selectedId);
  const key = `${state.selectedId}:${session.started_at || ""}`;
  if (session.status !== "running") {
    state.consistencyKey = key;
    state.consistency = null;
    banner.hidden = true;
    return;
  }
  if (state.consistencyKey === key && state.consistency) {
    renderConsistencyBanner(state.consistency);
    return;
  }
  state.consistencyKey = key;
  state.consistency = { checked: false };
  banner.hidden = true;
  try {
    const data = await api(`/api/sessions/${state.selectedId}/consistency`);
    if (statusOf(state.selectedId).started_at !== session.started_at) return;
    state.consistency = data;
    renderConsistencyBanner(data);
  } catch (error) {
    // 检测是尽力而为，失败保持静默，直到下次启动或切换档案再重试
  }
}

function renderConsistencyBanner(data) {
  const banner = $("consistencyBanner");
  if (!data || !data.checked) {
    banner.hidden = true;
    return;
  }
  if (!data.warnings.length) {
    banner.hidden = false;
    banner.className = "consistency-banner ok";
    const place = data.country ? `（${escapeHtml(data.country)}）` : "";
    banner.innerHTML =
      `<i data-lucide="shield-check"></i>` +
      `<span>出口 IP ${escapeHtml(data.ip)}${place} 与档案指纹一致</span>`;
    if (window.lucide) lucide.createIcons();
    return;
  }
  banner.hidden = false;
  banner.className = "consistency-banner warn";
  banner.innerHTML = data.warnings
    .map((warning) => {
      const fix =
        warning.kind === "timezone"
          ? `<button class="btn mini" data-fix-tz="${escapeHtml(warning.suggested_timezone)}">` +
            `改为 ${escapeHtml(warning.suggested_timezone)}</button>`
          : "";
      return (
        `<div class="consistency-item">` +
        `<i data-lucide="alert-triangle"></i>` +
        `<span>${escapeHtml(warning.message)}</span>${fix}</div>`
      );
    })
    .join("");
  if (window.lucide) lucide.createIcons();
  banner.querySelectorAll("[data-fix-tz]").forEach((btn) => {
    btn.addEventListener("click", () => applyIpTimezone(btn.dataset.fixTz));
  });
}

async function applyIpTimezone() {
  try {
    const result = await api(`/api/sessions/${state.selectedId}/apply-ip-timezone`, {
      method: "POST",
    });
    const updated = result.profile;
    const index = state.profiles.findIndex((p) => p.id === updated.id);
    if (index >= 0) state.profiles[index] = updated;
    renderProfileList();
    renderForm();
    toast(`时区已改为 ${result.timezone}`);
    state.consistency = null;
    state.consistencyKey = null;
    updateConsistencyBanner();
  } catch (error) {
    toast(error.message, true);
  }
}

function readForm() {
  const screen = $("screen").value.split("x").map(Number);
  const proxyEnabled = $("proxyEnabled").checked;
  const builtinProxy = $("proxyBuiltin").checked;
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
    proxy_enabled: builtinProxy,
    proxy_mode: builtinProxy ? "mihomo" : "manual",
    proxy_subscription_id: builtinProxy ? $("proxySubscription").value || null : null,
    proxy_region: builtinProxy ? $("proxyRegion").value || null : null,
    proxy_node: builtinProxy ? getNodeValue() || null : null,
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
    translate_button: $("translateButton").checked,
    cdp_attach: $("cdpAttach").checked,
    spoof_voices: $("spoofVoices").checked,
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
    if (payload.proxy && (!payload.proxy.host || !payload.proxy.port)) {
      toast("已启用手动代理，请填写主机和端口（或取消勾选「启用手动代理」）", true);
      return false;
    }
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

async function openDownloadsFolder() {
  if (!state.selectedId) return;
  try {
    const result = await api(`/api/profiles/${state.selectedId}/open-downloads`, {
      method: "POST",
    });
    toast(result.path ? `下载目录：${result.path}` : "已打开下载目录");
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

async function quitApp() {
  try {
    await api("/api/shutdown", { method: "POST" });
  } catch (error) {
    toast(error.message, true);
  }
}

const HEALTH_STATUS_TEXT = { pass: "通过", warn: "警告", fail: "风险" };

async function runHealthCheck() {
  if (!state.selectedId) return;
  const session = statusOf(state.selectedId);
  if (session.status !== "running") {
    toast("请先启动档案", true);
    return;
  }
  $("healthModal").hidden = false;
  $("healthSummary").textContent = "正在体检…";
  $("healthList").innerHTML = "";
  try {
    const report = await api(`/api/sessions/${state.selectedId}/health-check`, {
      method: "POST",
    });
    renderHealthReport(report);
  } catch (error) {
    closeHealthModal();
    toast(error.message, true);
  }
}

function renderHealthReport(report) {
  const { pass, warn, fail } = report.summary;
  $("healthSummary").innerHTML =
    `<span class="health-pill pass">通过 ${pass}</span>` +
    `<span class="health-pill warn">警告 ${warn}</span>` +
    `<span class="health-pill fail">风险 ${fail}</span>`;
  $("healthList").innerHTML = report.checks
    .map(
      (check) => `
      <div class="health-item ${check.status}">
        <span class="health-dot"></span>
        <div class="health-text">
          <strong>${escapeHtml(check.title)}</strong>
          <small>${escapeHtml(check.detail)}</small>
        </div>
        <span class="health-status">${HEALTH_STATUS_TEXT[check.status] || check.status}</span>
      </div>`
    )
    .join("");
  if (window.lucide) window.lucide.createIcons();
}

function closeHealthModal() {
  $("healthModal").hidden = true;
}

/* ===== Backup / Restore ===== */

async function uploadApi(path, formData) {
  const token = await getApiToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(path, { method: "POST", headers, body: formData });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error((data && (data.detail || data.message)) || `请求失败 (${response.status})`);
  }
  return data;
}

function openBackupModal() {
  $("backupPass").value = "";
  $("backupPass2").value = "";
  $("backupModal").hidden = false;
}

async function runBackup() {
  const pass = $("backupPass").value;
  if (pass.length < 8) {
    toast("口令至少 8 位", true);
    return;
  }
  if (pass !== $("backupPass2").value) {
    toast("两次口令不一致", true);
    return;
  }
  $("backupRunBtn").disabled = true;
  try {
    const result = await api("/api/backup/export", {
      method: "POST",
      body: JSON.stringify({
        passphrase: pass,
        include_data: $("backupIncludeData").checked,
      }),
    });
    const skipped = result.skipped_running.length
      ? `（跳过 ${result.skipped_running.length} 个运行中）`
      : "";
    toast(`备份完成${skipped}：${result.path}`);
    $("backupModal").hidden = true;
  } catch (error) {
    toast(error.message, true);
  } finally {
    $("backupRunBtn").disabled = false;
  }
}

function openRestoreModal(file) {
  state.pendingRestoreFile = file;
  const sizeMb = Math.round((file.size / 1048576) * 10) / 10;
  $("restoreFileName").textContent = `已选择：${file.name}（${sizeMb} MB）`;
  $("restorePass").value = "";
  $("restoreOverwrite").checked = false;
  $("restoreModal").hidden = false;
}

async function runRestore() {
  const file = state.pendingRestoreFile;
  if (!file) return;
  $("restoreRunBtn").disabled = true;
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("passphrase", $("restorePass").value);
    form.append("overwrite", String($("restoreOverwrite").checked));
    const result = await uploadApi("/api/backup/import", form);
    const parts = [`恢复 ${result.restored.length} 个档案`];
    if (result.data_restored.length) parts.push(`含 ${result.data_restored.length} 份登录态`);
    if (result.skipped_existing.length) parts.push(`跳过已存在 ${result.skipped_existing.length}`);
    if (result.skipped_running.length) parts.push(`跳过运行中 ${result.skipped_running.length}`);
    toast(parts.join("，"));
    $("restoreModal").hidden = true;
    state.pendingRestoreFile = null;
    await loadProfiles();
  } catch (error) {
    toast(error.message, true);
  } finally {
    $("restoreRunBtn").disabled = false;
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
  $("downloadsBtn").addEventListener("click", openDownloadsFolder);
  $("importProfileBtn").addEventListener("click", pickImportFile);
  $("importFile").addEventListener("change", importProfileFromFile);
  $("batchLaunchBtn").addEventListener("click", batchLaunch);
  $("batchStopBtn").addEventListener("click", batchStop);
  $("recycleBinBtn").addEventListener("click", showRecycleBin);
  $("quitBtn").addEventListener("click", quitApp);
  $("recycleBackBtn").addEventListener("click", hideRecycleBin);
  $("profileForm").addEventListener("input", markFormDirty);
  $("profileForm").addEventListener("change", markFormDirty);
  $("proxyEnabled").addEventListener("change", (event) => {
    formDirty = true;
    setProxyEnabled(event.target.checked);
  });
  $("proxyBuiltin").addEventListener("change", (event) => {
    formDirty = true;
    setProxyBuiltinEnabled(event.target.checked);
  });
  $("proxyImportBtn").addEventListener("click", importSubscription);
  $("proxySubscription").addEventListener("change", (event) => {
    state.selectedSubscriptionId = event.target.value;
    loadNodes(event.target.value);
    markFormDirty();
  });
  $("proxyRegion").addEventListener("change", () => {
    renderNodeOptions();
    markFormDirty();
  });
  $("proxyNodeTrigger").addEventListener("click", () => {
    const list = $("proxyNodeList");
    list.hidden = !list.hidden;
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".node-select")) closeNodeList();
    if (!event.target.closest(".more-menu")) closeMoreMenu();
  });
  $("moreBtn").addEventListener("click", () => {
    const menu = $("moreMenu");
    menu.hidden = !menu.hidden;
    $("moreBtn").setAttribute("aria-expanded", String(!menu.hidden));
  });
  $("proxyTestBtn").addEventListener("click", testNode);
  $("proxyRefreshBtn").addEventListener("click", refreshSubscription);
  $("proxyDeleteBtn").addEventListener("click", deleteSubscription);
  $("healthBtn").addEventListener("click", runHealthCheck);
  $("healthCloseBtn").addEventListener("click", closeHealthModal);
  $("healthModal").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeHealthModal();
  });
  $("backupBtn").addEventListener("click", openBackupModal);
  $("backupCloseBtn").addEventListener("click", () => {
    $("backupModal").hidden = true;
  });
  $("backupRunBtn").addEventListener("click", runBackup);
  $("backupModal").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) $("backupModal").hidden = true;
  });
  $("restoreBtn").addEventListener("click", () => $("backupFile").click());
  $("backupFile").addEventListener("change", (event) => {
    const file = event.target.files[0];
    event.target.value = "";
    if (file) openRestoreModal(file);
  });
  $("restoreCloseBtn").addEventListener("click", () => {
    $("restoreModal").hidden = true;
  });
  $("restoreRunBtn").addEventListener("click", runRestore);
  $("restoreModal").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) $("restoreModal").hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("healthModal").hidden) closeHealthModal();
    if (event.key === "Escape" && !$("moreMenu").hidden) closeMoreMenu();
    if (event.key === "Escape" && !$("backupModal").hidden) $("backupModal").hidden = true;
    if (event.key === "Escape" && !$("restoreModal").hidden) $("restoreModal").hidden = true;
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
    await getApiToken();
    await Promise.all([loadEngine(), loadProfiles(), loadSessions(), loadSubscriptions()]);
    if (state.selectedId) renderForm();
  } catch (error) {
    toast(error.message, true);
  }
  setInterval(loadSessions, 2000);
}

init();
