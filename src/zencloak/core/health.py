"""In-browser fingerprint probe and local health report builder.

The probe runs inside a page of the running profile (via Playwright in
the session thread) and collects raw signals. ``build_report`` turns the
signals plus the profile config and egress geo into a list of checks the
panel renders as a report.
"""

PROBE_JS = """
async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const webrtcIps = await (async () => {
    try {
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      });
      pc.createDataChannel('zencloak-probe');
      const ips = new Set();
      pc.addEventListener('icecandidate', (event) => {
        if (!event.candidate) return;
        const match = /candidate:\\d+ \\S+ \\d+ (\\S+) \\d+ typ/.exec(
          event.candidate.candidate
        );
        if (match) ips.add(match[1]);
      });
      await pc.setLocalDescription(await pc.createOffer());
      await sleep(2500);
      pc.close();
      return [...ips];
    } catch (error) {
      return null;
    }
  })();
  const canvasHash = () => {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 240;
      canvas.height = 60;
      const ctx = canvas.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = "16px 'Arial'";
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 120, 30);
      ctx.fillStyle = '#069';
      ctx.fillText('ZenCloak FP <@*#%>', 2, 2);
      ctx.strokeStyle = 'rgba(0,150,255,0.7)';
      ctx.beginPath();
      ctx.arc(50, 50, 20, 0, Math.PI * 2);
      ctx.stroke();
      const data = canvas.toDataURL();
      let hash = 0;
      for (let i = 0; i < data.length; i++) {
        hash = (hash * 31 + data.charCodeAt(i)) | 0;
      }
      return hash;
    } catch (error) {
      return null;
    }
  };
  let webgl = null;
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    webgl = {
      vendor: ext
        ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL)
        : gl.getParameter(gl.VENDOR),
      renderer: ext
        ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER),
    };
  } catch (error) {}
  const canvasFirst = canvasHash();
  await sleep(50);
  const canvasSecond = canvasHash();
  return {
    webdriver: navigator.webdriver,
    userAgent: navigator.userAgent,
    language: navigator.language,
    languages: navigator.languages,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    screenWidth: screen.width,
    screenHeight: screen.height,
    deviceMemory: navigator.deviceMemory,
    hardwareConcurrency: navigator.hardwareConcurrency,
    maxTouchPoints: navigator.maxTouchPoints,
    pluginsCount: navigator.plugins.length,
    webrtcIps,
    webgl,
    canvas: { first: canvasFirst, second: canvasSecond },
  };
}
"""

_PRIVATE_IP_PREFIXES = (
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "169.254.",
)


def _check(check_id: str, title: str, status: str, detail: str) -> dict:
    return {"id": check_id, "title": title, "status": status, "detail": detail}


def _is_private_ip(ip: str) -> bool:
    return ip.startswith(_PRIVATE_IP_PREFIXES)


def build_report(signals: dict, profile: dict, geo: dict | None = None) -> dict:
    """Turn raw probe signals into a health check report.

    ``geo`` is the egress IP geo (see consistency.lookup_ip_geo) when it
    could be resolved; checks that need it are skipped otherwise.
    """
    checks: list[dict] = []

    checks.append(
        _check(
            "webdriver",
            "自动化痕迹 (navigator.webdriver)",
            "pass" if not signals.get("webdriver") else "fail",
            "未暴露 webdriver" if not signals.get("webdriver") else "navigator.webdriver 为 true",
        )
    )

    ua = signals.get("userAgent") or ""
    headless = "HeadlessChrome" in ua
    checks.append(
        _check(
            "user_agent",
            "User-Agent",
            "fail" if headless else "pass",
            ua or "未获取到 User-Agent"
            if not headless
            else "User-Agent 含 HeadlessChrome 痕迹",
        )
    )

    locale = profile.get("locale")
    language = signals.get("language")
    if locale and language:
        matched = language == locale or language.startswith(locale.split("-")[0])
        checks.append(
            _check(
                "language",
                "浏览器语言与档案配置",
                "pass" if matched else "warn",
                f"实际 {language}，档案配置 {locale}"
                + ("" if matched else "，与配置不一致"),
            )
        )

    profile_timezone = profile.get("timezone")
    actual_timezone = signals.get("timezone")
    if profile_timezone and actual_timezone:
        checks.append(
            _check(
                "timezone",
                "浏览器时区与档案配置",
                "pass" if actual_timezone == profile_timezone else "fail",
                f"实际 {actual_timezone}，档案配置 {profile_timezone}",
            )
        )

    if geo:
        ip_timezone = geo.get("timezone")
        if ip_timezone and actual_timezone:
            checks.append(
                _check(
                    "geo_timezone",
                    "时区与出口 IP 一致性",
                    "pass" if ip_timezone == actual_timezone else "warn",
                    f"出口 IP 时区 {ip_timezone}，浏览器时区 {actual_timezone}",
                )
            )
        ip_country = geo.get("country")
        locale_country = None
        if locale and "-" in locale:
            region = locale.rsplit("-", 1)[-1]
            locale_country = region.upper() if len(region) == 2 else None
        if ip_country and locale_country:
            checks.append(
                _check(
                    "geo_locale",
                    "语言与出口国家一致性",
                    "pass" if locale_country == ip_country else "warn",
                    f"出口国家 {ip_country}，语言 {locale}",
                )
            )

    webrtc_ips = signals.get("webrtcIps")
    if webrtc_ips is None:
        checks.append(
            _check("webrtc", "WebRTC 泄漏", "pass", "WebRTC 不可用或被禁用")
        )
    elif not webrtc_ips:
        checks.append(
            _check("webrtc", "WebRTC 泄漏", "pass", "未收集到任何本地候选地址")
        )
    else:
        private = [ip for ip in webrtc_ips if _is_private_ip(ip)]
        public = [ip for ip in webrtc_ips if not _is_private_ip(ip)]
        if public:
            status = "warn"
            detail = f"WebRTC 暴露公网地址: {', '.join(public)}"
        elif private:
            status = "warn"
            detail = f"WebRTC 暴露本地地址: {', '.join(private)}"
        else:
            status = "pass"
            detail = "未收集到可识别地址"
        checks.append(_check("webrtc", "WebRTC 泄漏", status, detail))

    canvas = signals.get("canvas") or {}
    first, second = canvas.get("first"), canvas.get("second")
    if first is None or second is None:
        checks.append(
            _check("canvas", "Canvas 指纹", "warn", "Canvas 不可读")
        )
    elif first != second:
        checks.append(
            _check("canvas", "Canvas 指纹", "pass", "两次读取结果不同，噪声已启用")
        )
    else:
        checks.append(
            _check(
                "canvas",
                "Canvas 指纹",
                "pass",
                f"读取稳定（hash {first}）",
            )
        )

    screen_pair = (
        profile.get("screen_width"),
        profile.get("screen_height"),
    )
    actual_screen = (signals.get("screenWidth"), signals.get("screenHeight"))
    if all(actual_screen):
        matched = screen_pair == actual_screen
        checks.append(
            _check(
                "screen",
                "屏幕分辨率与档案配置",
                "pass" if matched else "warn",
                f"实际 {actual_screen[0]}x{actual_screen[1]}，"
                f"档案配置 {screen_pair[0]}x{screen_pair[1]}",
            )
        )

    for check_id, title, signal_key in (
        ("hardware_concurrency", "CPU 核数与档案配置", "hardwareConcurrency"),
        ("device_memory", "设备内存与档案配置", "deviceMemory"),
    ):
        configured = profile.get(
            "hardware_concurrency" if signal_key == "hardwareConcurrency"
            else "device_memory"
        )
        actual = signals.get(signal_key)
        if configured and actual:
            checks.append(
                _check(
                    check_id,
                    title,
                    "pass" if actual == configured else "warn",
                    f"实际 {actual}，档案配置 {configured}",
                )
            )

    webgl = signals.get("webgl")
    if webgl:
        checks.append(
            _check(
                "webgl",
                "WebGL 信息",
                "pass",
                f"{webgl.get('vendor') or '?'} / {webgl.get('renderer') or '?'}",
            )
        )

    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        summary[check["status"]] = summary.get(check["status"], 0) + 1
    return {"checks": checks, "summary": summary}
