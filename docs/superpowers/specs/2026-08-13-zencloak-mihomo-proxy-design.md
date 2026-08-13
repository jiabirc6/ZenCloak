# ZenCloak 内置 Mihomo 代理功能设计

> 日期：2026-08-13
> 状态：已确认，进入实施

## 目标

让 ZenCloak 为每个档案启动一个独立的 mihomo 内核实例。档案可以选择自己的出口节点，多个档案可同时使用不同地区的 IP，网络出口、DNS、控制器全部按档案隔离，不再依赖系统 Clash 的智能分流。

## 范围

### 本期包含

- mihomo 二进制下载、校验、缓存。
- 每个档案一个独立 mihomo 实例：独立 mixed-port、external-controller、DNS 端口、配置目录。
- 订阅导入：读取用户提供的 Clash/Mihomo YAML，提取内联 `proxies` 节点。
- 按档案选择节点，启动后通过控制器 API 设置 `GLOBAL` 组指向该节点。
- 全局代理模式（`mode: global`），本期不做规则编辑，避免 DNS/出口分裂。
- 浏览器启动/停止时联动代理生命周期。
- 代理状态、出口 IP 检测、节点延迟测试的 API 和 UI。

### 本期不包含

- 远程 `proxy-providers` 节点自动合并（二期）。
- 规则编辑器、按域名分流（二期）。
- 多订阅同时启用的复杂管理（二期）。

## 架构

```text
ZenCloak UI
  -> /api/proxy/* 接口
  -> ProxyManager
       -> 每档案生成 runtime config.yaml
       -> 启动独立 mihomo.exe
       -> 控制器 API 选择节点
       -> 浏览器通过 127.0.0.1:<mixed-port> 走代理
```

### 新增模块

- `src/zencloak/core/mihomo.py`
  - 定位/下载 mihomo 二进制。
  - 生成每个档案的运行时配置。
  - 启动/停止进程、健康检查、端口分配、进程回收。
- `src/zencloak/core/subscriptions.py`
  - 导入订阅 YAML。
  - 解析 `proxies` 节点并去掉 `direct`。
  - 按节点名推断地区（US/HK/JP/SG/TW/KR 等关键字）。
- `src/zencloak/core/proxy_runtime.py`
  - 维护运行中实例的端口、控制器 secret、配置路径。
  - 通过控制器 API 选择节点、查询延迟、查询出口 IP。

### 数据模型

档案新增字段：

```python
proxy_enabled: bool = False
proxy_mode: Literal["mihomo"] = "mihomo"
proxy_subscription_id: str | None = None
proxy_region: str | None = None
proxy_node: str | None = None
```

订阅数据保存在：

```text
~/.zencloak/proxy/subscriptions/<id>/source.yaml
~/.zencloak/proxy/subscriptions/<id>/meta.json
```

运行数据保存在：

```text
~/.zencloak/proxy/runtime/<profile_id>/config.yaml
~/.zencloak/proxy/runtime/<profile_id>/mihomo.log
```

### 配置生成

从订阅中提取内联 `proxies`，去掉 `direct`，生成最小运行配置：

```yaml
mixed-port: <唯一端口>
allow-lan: false
mode: global
log-level: silent
external-controller: 127.0.0.1:<唯一控制器端口>
secret: <随机>
dns:
  enable: true
  listen: 127.0.0.1:<唯一 DNS 端口>
  nameserver:
    - https://dns.alidns.com/dns-query
  fallback:
    - https://dns.google/dns-query
  fallback-filter:
    geoip: false
proxies:
  - <内联节点>
proxy-groups:
  - name: GLOBAL
    type: select
    proxies:
      - <全部节点名>
rules:
  - MATCH,GLOBAL
```

启动成功后通过 `PUT /proxies/GLOBAL` 选择 `proxy_node`。

### 生命周期

1. 用户启动档案。
2. `SessionManager.launch` 检测 `proxy_enabled`。
3. `ProxyManager.start(profile)` 生成配置并启动 mihomo。
4. 健康检查 `GET /version` 通过后，返回 `socks5://127.0.0.1:<mixed-port>`。
5. `SessionManager` 将代理传给 CloakBrowser。
6. 停止档案时先停止浏览器，再 `ProxyManager.stop(profile_id)`。
7. 进程异常退出时标记代理错误，档案状态显示中文错误。

### API

- `POST /api/proxy/subscriptions/import`：导入订阅 URL 或 YAML。
- `GET /api/proxy/subscriptions`：列出订阅。
- `GET /api/proxy/subscriptions/{id}/nodes`：列出节点和地区。
- `POST /api/proxy/nodes/{node}/test`：延迟测试。
- `GET /api/sessions/{id}/proxy/status`：代理运行状态、出口 IP。

### 安全

- mihomo 控制器只绑定 `127.0.0.1`，每个实例独立随机 secret。
- 订阅凭证只存在用户数据目录，不写入仓库和日志。
- 进程结束后关闭所有端口和控制器。

### 错误处理

- mihomo 二进制缺失：自动下载失败时返回可理解的中文错误。
- 配置解析失败：提示订阅格式错误。
- 节点不可达：浏览器仍可启动，但状态栏显示代理异常。
- 端口冲突：自动重新分配端口。

### 测试

- 单元：配置生成、节点解析、端口分配、生命周期（fake mihomo）。
- 集成：真实 mihomo 双实例同时启动，分别通过不同节点访问出口 IP。
- 端到端：两个档案同时启动，ping0/BrowserScan 分数和一致性校验。

### 实施阶段

1. 技术验证：下载 mihomo，双实例同时代理。
2. 核心管理器：配置生成、进程生命周期、健康检查。
3. 订阅与节点解析。
4. API 与档案模型。
5. 会话集成。
6. UI 代理控制台。
7. 端到端验证。
