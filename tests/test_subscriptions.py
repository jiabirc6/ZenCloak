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
