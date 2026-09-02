from zencloak.core.subscriptions import (
    import_subscription,
    infer_region,
    list_subscriptions,
)


SAMPLE = """
proxies:
  - {name: 直连, type: direct}
  - name: NAT-新美国小鸡-VLESS
    type: vless
    server: 1.2.3.4
    port: 443
  - name: nat-vless
    type: vless
    server: 5.6.7.8
    port: 443
"""


def test_infer_region():
    assert infer_region("NAT-新美国小鸡-VLESS") == "US"
    assert infer_region("香港节点") == "HK"
    assert infer_region("无地区标记") is None


def test_import_subscription_filters_direct(tmp_path):
    meta = import_subscription(SAMPLE, tmp_path, name="测试")
    assert len(meta["nodes"]) == 2
    assert meta["nodes"][0]["region"] == "US"
    assert len(list_subscriptions(tmp_path)) == 1


PROVIDER_SOURCE = """
proxies:
  - name: 自建节点
    type: vless
    server: 9.9.9.9
    port: 443
proxy-providers:
  机场A:
    url: "https://example.com/sub-a"
    type: http
    override:
      additional-prefix: "[a] "
  机场B:
    url: "https://example.com/sub-b"
    type: http
"""

PROVIDER_A = """
proxies:
  - {name: 香港-01, type: ss, server: 1.1.1.1, port: 8388}
  - {name: 美国-02, type: vmess, server: 2.2.2.2, port: 443}
"""

PROVIDER_B = """
proxies:
  - {name: 日本-01, type: trojan, server: 3.3.3.3, port: 443}
"""


def _fake_fetch(url):
    if "sub-a" in url:
        return PROVIDER_A
    if "sub-b" in url:
        return PROVIDER_B
    raise OSError("unknown url")


def test_import_expands_providers_with_prefix(tmp_path):
    from zencloak.core.subscriptions import load_nodes

    meta = import_subscription(PROVIDER_SOURCE, tmp_path, name="带机场", fetch=_fake_fetch)
    names = [n["name"] for n in meta["nodes"]]
    assert names == ["自建节点", "[a] 香港-01", "[a] 美国-02", "日本-01"]
    regions = {n["name"]: n["region"] for n in meta["nodes"]}
    assert regions["[a] 香港-01"] == "HK"
    assert regions["[a] 美国-02"] == "US"
    assert meta["providers"] == {"机场A": "ok: 2", "机场B": "ok: 1"}

    resolved = load_nodes(tmp_path, meta["id"])
    assert [p["name"] for p in resolved] == names


def test_import_survives_one_failing_provider(tmp_path):
    def flaky_fetch(url):
        if "sub-b" in url:
            raise OSError("boom")
        return _fake_fetch(url)

    meta = import_subscription(PROVIDER_SOURCE, tmp_path, fetch=flaky_fetch)
    assert meta["providers"]["机场B"].startswith("error")
    assert [n["name"] for n in meta["nodes"]] == ["自建节点", "[a] 香港-01", "[a] 美国-02"]


def test_refresh_subscription_rebuilds_nodes(tmp_path):
    from zencloak.core.subscriptions import refresh_subscription

    meta = import_subscription(PROVIDER_SOURCE, tmp_path, name="带机场", fetch=_fake_fetch)
    assert len(meta["nodes"]) == 4

    def updated_fetch(url):
        if "sub-a" in url:
            return "proxies:\n  - {name: 新加坡-01, type: ss, server: 4.4.4.4, port: 8388}\n"
        return _fake_fetch(url)

    refreshed = refresh_subscription(tmp_path, meta["id"], fetch=updated_fetch)
    assert refreshed["name"] == "带机场"
    assert refreshed["imported_at"] == meta["imported_at"]
    names = [n["name"] for n in refreshed["nodes"]]
    assert "[a] 新加坡-01" in names
    assert "[a] 香港-01" not in names


def test_delete_subscription(tmp_path):
    from zencloak.core.subscriptions import delete_subscription

    meta = import_subscription(SAMPLE, tmp_path, name="待删")
    assert delete_subscription(tmp_path, meta["id"]) is True
    assert list_subscriptions(tmp_path) == []
    assert delete_subscription(tmp_path, meta["id"]) is False


def test_delete_subscription_rejects_bad_id(tmp_path):
    import pytest

    from zencloak.core.subscriptions import delete_subscription

    with pytest.raises(ValueError, match="订阅 ID 无效"):
        delete_subscription(tmp_path, "../../etc")
