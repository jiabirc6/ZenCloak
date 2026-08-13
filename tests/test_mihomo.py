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
