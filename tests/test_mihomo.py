import yaml

from zencloak.core.mihomo import generate_runtime_config


def _nodes():
    return [
        {
            "name": "美国节点",
            "type": "vless",
            "server": "1.2.3.4",
            "port": 443,
        },
        {
            "name": "香港节点",
            "type": "vmess",
            "server": "5.6.7.8",
            "port": 80,
        },
    ]


def test_generate_runtime_config_is_valid_global_config():
    config = generate_runtime_config(_nodes(), [17891, 19091, 15353], "secret")
    assert config["mixed-port"] == 17891
    assert config["external-controller"] == "127.0.0.1:19091"
    assert config["mode"] == "global"
    assert config["proxy-groups"][0]["proxies"] == ["美国节点", "香港节点"]
    assert config["rules"] == ["MATCH,GLOBAL"]
    assert config["dns"]["listen"] == "127.0.0.1:15353"
    dumped = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    assert yaml.safe_load(dumped)["mixed-port"] == 17891


def test_test_nodes_queries_controller_delay_and_cleans_up(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from zencloak.core.mihomo import ProxyManager

    manager = ProxyManager(tmp_path)
    handle = SimpleNamespace(mixed_port=1, controller_port=2, secret="s")
    monkeypatch.setattr(manager, "start", lambda pid, nodes, node_name=None: handle)
    stopped = []
    monkeypatch.setattr(manager, "stop", lambda pid: stopped.append(pid))
    paths = []

    def fake_request(h, method, path, body=None):
        paths.append(path)
        return {"delay": 176}

    monkeypatch.setattr(manager, "_controller_request", fake_request)
    results = manager.test_nodes([{"name": "美国 A"}, {"name": "🇺🇸节点|B"}])
    assert [r["node"] for r in results] == ["美国 A", "🇺🇸节点|B"]
    assert all(r["delay_ms"] == 176 and r["error"] is None for r in results)
    assert stopped == [ProxyManager.SPEEDTEST_ID]
    # 节点名经过 URL 编码
    assert any("%E7%BE%8E%E5%9B%BD%20A" in p or "美国" not in p for p in paths)


def test_test_nodes_records_per_node_errors(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from zencloak.core.mihomo import MihomoError, ProxyManager

    manager = ProxyManager(tmp_path)
    handle = SimpleNamespace(mixed_port=1, controller_port=2, secret="s")
    monkeypatch.setattr(manager, "start", lambda pid, nodes, node_name=None: handle)
    monkeypatch.setattr(manager, "stop", lambda pid: None)

    def fake_request(h, method, path, body=None):
        if "dead" in path:
            raise MihomoError("503 timeout")
        return {"delay": 88}

    monkeypatch.setattr(manager, "_controller_request", fake_request)
    results = manager.test_nodes([{"name": "dead-node"}, {"name": "live-node"}])
    assert results[0]["delay_ms"] is None and "timeout" in results[0]["error"]
    assert results[1]["delay_ms"] == 88


def test_test_nodes_empty_returns_empty(tmp_path):
    from zencloak.core.mihomo import ProxyManager

    assert ProxyManager(tmp_path).test_nodes([]) == []
