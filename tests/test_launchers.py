import pytest

from zencloak.core.launchers import (
    KERNELS,
    _chromium_kwargs,
    kernel_availability,
    launch_extra_kernel,
)


def test_kernel_availability_reports_three():
    avail = kernel_availability()
    assert set(avail) == {"cloak", "camoufox", "chromium"}
    assert avail["cloak"][0] is True
    assert avail["chromium"][0] is True
    # camoufox 未安装时给出安装指引
    ok, reason = avail["camoufox"]
    assert ok is (reason is None)
    if not ok:
        assert "pip install" in reason


def test_kernels_metadata_shape():
    assert [k["id"] for k in KERNELS] == ["cloak", "camoufox", "chromium"]
    assert all(k["label"] and k["stealth"] for k in KERNELS)


def _profile(**over):
    base = {
        "id": "aaaaaaaaaaaa",
        "locale": "zh-HK",
        "timezone": "Asia/Hong_Kong",
        "user_agent": None,
        "proxy": None,
    }
    base.update(over)
    return base


def test_chromium_kwargs_lang_cdp_extension_no_proxy():
    kwargs = _chromium_kwargs(
        _profile(), "C:/data/aaaaaaaaaaaa", None, 55555, "C:/ext/newtab-v3"
    )
    assert "--lang=zh-HK" in kwargs["args"]
    assert "--remote-debugging-port=55555" in kwargs["args"]
    assert "--load-extension=C:/ext/newtab-v3" in kwargs["args"]
    assert "--no-proxy-server" in kwargs["args"]
    assert kwargs["user_data_dir"] == "C:/data/aaaaaaaaaaaa"
    assert kwargs["timezone_id"] == "Asia/Hong_Kong"
    assert kwargs["locale"] == "zh-HK"
    assert "proxy" not in kwargs


def test_chromium_kwargs_proxy_server_and_manual_proxy():
    kwargs = _chromium_kwargs(_profile(), "dir", "socks5://127.0.0.1:1080", None, None)
    assert kwargs["proxy"] == {"server": "socks5://127.0.0.1:1080"}
    assert "--no-proxy-server" not in kwargs["args"]
    manual = _chromium_kwargs(
        _profile(proxy={"type": "http", "host": "p.example", "port": 8080,
                        "username": "u", "password": "p"}),
        "dir", None, None, None,
    )
    assert manual["proxy"]["server"] == "http://p.example:8080"
    assert manual["proxy"]["username"] == "u"


def test_chromium_kwargs_user_agent():
    kwargs = _chromium_kwargs(_profile(user_agent="CustomUA/1.0"), "dir", None, None, None)
    assert "--user-agent=CustomUA/1.0" in kwargs["args"]


def test_unknown_kernel_raises():
    with pytest.raises(RuntimeError, match="未知内核"):
        launch_extra_kernel("netscape", _profile(), None, None, None)