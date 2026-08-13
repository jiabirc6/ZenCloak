# ZenCloak 内置 Mihomo 代理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每个 ZenCloak 档案拥有独立 mihomo 代理实例，可按档案选择出口节点并全局代理。

**Architecture:** 每个档案生成独立 mihomo 配置并启动独立进程，浏览器只连接本机对应端口；代理生命周期随档案启动/停止联动。

**Tech Stack:** Python 3.12、mihomo core、FastAPI、Playwright/CloakBrowser、PyYAML、pytest。

---

## Phase 0: mihomo 内核验证

### Task 0.1: 获取 mihomo 二进制

**Files:**
- Create: `scripts/fetch_mihomo.py`
- Test: `tests/test_fetch_mihomo.py`

- [ ] **Step 1: 写失败测试**

```python
def test_binary_path_created(tmp_path):
    from zencloak.core.mihomo import ensure_binary
    path = ensure_binary(tmp_path)
    assert path.exists()
```

- [ ] **Step 2: 确认失败**

Run: `pytest tests/test_fetch_mihomo.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现下载与校验**

从 GitHub mihomo 官方 release 下载 Windows amd64 压缩包，解压到 `~/.zencloak/bin/mihomo.exe`，记录 SHA256。

- [ ] **Step 4: 测试通过并提交**

Run: `pytest tests/test_fetch_mihomo.py -v`

### Task 0.2: 双实例同时代理验证

- [ ] 写脚本启动两个最小 mihomo 配置（不同端口），分别 `curl -x socks5://127.0.0.1:<port> https://api.ipify.org`。
- [ ] 验证两个实例同时在线且端口互不影响。
- [ ] 提交验证脚本与说明。

## Phase 1: 核心代理管理器

### Task 1.1: 端口分配

**Files:**
- Create: `src/zencloak/core/proxy_runtime.py`
- Test: `tests/test_proxy_runtime.py`

- [ ] 实现 `allocate_ports(n=3) -> list[int]`：随机选取未占用 TCP 端口。
- [ ] 测试：连续调用不重复，且端口可连接失败（未被占用）。

### Task 1.2: 运行时配置生成

- [ ] 实现 `generate_runtime_config(nodes, profile, ports, secret) -> dict`。
- [ ] 配置包含 `mixed-port`、`external-controller`、`secret`、`dns.listen`、`mode: global`、`GLOBAL` 组、`MATCH,GLOBAL` 规则。
- [ ] 测试：生成的 YAML 可被 `yaml.safe_load` 解析，端口唯一。

### Task 1.3: ProxyManager 生命周期

**Files:**
- Create: `src/zencloak/core/mihomo.py`
- Test: `tests/test_mihomo.py`

- [ ] `start(profile, nodes) -> ProxyHandle`：写配置、启动进程、`GET /version` 健康检查、`PUT /proxies/GLOBAL` 选节点。
- [ ] `stop(profile_id)`：结束进程、清理端口。
- [ ] `status(profile_id)`：返回运行状态和出口 IP。
- [ ] 用 fake mihomo 进程做单元测试，再用真实 mihomo 做集成测试。

## Phase 2: 订阅与节点

### Task 2.1: 订阅导入

**Files:**
- Create: `src/zencloak/core/subscriptions.py`
- Test: `tests/test_subscriptions.py`

- [ ] `import_subscription(source_yaml) -> Subscription`：解析 `proxies`，剔除 `direct`。
- [ ] 保存到 `~/.zencloak/proxy/subscriptions/<id>/source.yaml` 和 `meta.json`。
- [ ] 测试：用内置样例 YAML 验证解析数量与字段。

### Task 2.2: 地区推断

- [ ] `infer_region(node_name) -> str | None`：按 `美国/香港/日本/新加坡/台湾/韩国` 等关键字推断。
- [ ] 测试：`NAT-新美国小鸡-VLESS -> US`，`nat-vless -> HK`。

## Phase 3: API 与档案模型

### Task 3.1: 档案字段

**Files:**
- Modify: `src/zencloak/core/models.py`

- [ ] 增加 `proxy_enabled`、`proxy_mode`、`proxy_subscription_id`、`proxy_region`、`proxy_node`。
- [ ] 更新 `default_profile_draft()`。
- [ ] 更新测试。

### Task 3.2: 代理 API

**Files:**
- Modify: `src/zencloak/api.py`

- [ ] `POST /api/proxy/subscriptions/import`
- [ ] `GET /api/proxy/subscriptions`
- [ ] `GET /api/proxy/subscriptions/{id}/nodes`
- [ ] `POST /api/proxy/nodes/{node}/test`
- [ ] `GET /api/sessions/{id}/proxy/status`
- [ ] 用 TestClient 写 API 测试。

## Phase 4: 会话集成

**Files:**
- Modify: `src/zencloak/core/sessions.py`

- [ ] `SessionManager.launch` 在 `proxy_enabled` 时调用 `ProxyManager.start`。
- [ ] `_build_launch_kwargs` 接收 `ProxyHandle.server` 并写入 `kwargs["proxy"]`。
- [ ] `stop` / `stop_all` 时调用 `ProxyManager.stop`。
- [ ] 测试：fake launcher 验证 kwargs 包含代理；fake ProxyManager 验证停止调用。

## Phase 5: UI 代理控制台

**Files:**
- Modify: `src/zencloak/ui/index.html`
- Modify: `src/zencloak/ui/app.js`
- Modify: `src/zencloak/ui/styles.css`

- [ ] 代理 tab 增加：订阅导入、节点列表、地区筛选、选择节点、测速、代理状态。
- [ ] 保存档案时提交代理字段。
- [ ] UI smoke 测试：代理 tab 可见、节点可选中。

## Phase 6: 端到端验证

- [ ] 两个档案同时启动，分别选不同节点，访问 `ping0.cc/env` 和 BrowserScan。
- [ ] 验证 IP、时区、语言、DNS 一致，分数显著提升。
- [ ] 提交验证记录到 `docs/`。

## 验收标准

- 两个档案可同时运行且出口 IP 不同。
- 停止档案后 mihomo 进程退出，端口释放。
- 代理异常时 UI 有中文提示，不影响其他档案。
- 全量测试通过。
