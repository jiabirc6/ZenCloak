from zencloak.core.health import PROBE_JS, build_report


def _profile():
    return {
        "locale": "en-US",
        "timezone": "America/New_York",
        "screen_width": 1920,
        "screen_height": 1080,
        "hardware_concurrency": 8,
        "device_memory": 16,
    }


def _signals():
    return {
        "webdriver": False,
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/146.0.0.0",
        "language": "en-US",
        "languages": ["en-US"],
        "timezone": "America/New_York",
        "screenWidth": 1920,
        "screenHeight": 1080,
        "deviceMemory": 16,
        "hardwareConcurrency": 8,
        "maxTouchPoints": 10,
        "pluginsCount": 5,
        "webrtcIps": [],
        "webgl": {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE"},
        "canvas": {"first": 123, "second": 123},
    }


def test_build_report_all_pass():
    report = build_report(_signals(), _profile(), geo=None)
    assert report["summary"]["fail"] == 0
    assert report["summary"]["warn"] == 0
    assert report["summary"]["pass"] == len(report["checks"])
    ids = [check["id"] for check in report["checks"]]
    assert {"webdriver", "user_agent", "language", "timezone", "webrtc",
            "canvas", "screen"} <= set(ids)


def test_build_report_flags_webdriver_and_headless():
    signals = _signals()
    signals["webdriver"] = True
    signals["userAgent"] = "Mozilla/5.0 HeadlessChrome/146.0.0.0"
    report = build_report(signals, _profile())
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["webdriver"] == "fail"
    assert statuses["user_agent"] == "fail"


def test_build_report_flags_timezone_and_language_mismatch():
    profile = _profile()
    signals = _signals()
    signals["timezone"] = "Asia/Shanghai"
    signals["language"] = "zh-CN"
    signals["languages"] = ["zh-CN"]
    report = build_report(signals, profile)
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["timezone"] == "fail"
    assert statuses["language"] == "warn"


def test_build_report_geo_checks():
    signals = _signals()
    report = build_report(
        signals,
        _profile(),
        geo={"ip": "1.2.3.4", "country": "US", "timezone": "America/New_York"},
    )
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["geo_timezone"] == "pass"
    assert statuses["geo_locale"] == "pass"

    report = build_report(
        signals,
        _profile(),
        geo={"ip": "1.2.3.4", "country": "JP", "timezone": "Asia/Tokyo"},
    )
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["geo_timezone"] == "warn"
    assert statuses["geo_locale"] == "warn"


def test_build_report_webrtc_private_and_public_leaks():
    profile = _profile()

    signals = _signals()
    signals["webrtcIps"] = ["192.168.1.5"]
    report = build_report(signals, profile)
    webrtc = next(c for c in report["checks"] if c["id"] == "webrtc")
    assert webrtc["status"] == "warn"
    assert "192.168.1.5" in webrtc["detail"]

    signals = _signals()
    signals["webrtcIps"] = ["8.8.8.8"]
    report = build_report(signals, profile)
    webrtc = next(c for c in report["checks"] if c["id"] == "webrtc")
    assert webrtc["status"] == "warn"
    assert "8.8.8.8" in webrtc["detail"]


def test_build_report_screen_and_hardware_mismatch():
    profile = _profile()
    profile["screen_width"] = 1440
    profile["screen_height"] = 900
    profile["device_memory"] = 8
    report = build_report(_signals(), profile)
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["screen"] == "warn"
    assert statuses["device_memory"] == "warn"
    assert statuses["hardware_concurrency"] == "pass"


def test_build_report_canvas_noise_detected():
    profile = _profile()
    signals = _signals()
    signals["canvas"] = {"first": 111, "second": 222}
    report = build_report(signals, profile)
    canvas = next(c for c in report["checks"] if c["id"] == "canvas")
    assert canvas["status"] == "pass"
    assert "噪声" in canvas["detail"]


def test_probe_js_is_async_function():
    assert PROBE_JS.strip().startswith("async () =>")
    assert "RTCPeerConnection" in PROBE_JS
    assert "webdriver" in PROBE_JS
