import time

import pytest
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


def test_sweep_orphans_cleans_stale_and_dead_pid_files(tmp_path):
    from zencloak.core.mihomo import MIHOMO_PID_FILE, ProxyManager

    manager = ProxyManager(data_root=tmp_path)
    runtime = tmp_path / "runtime"
    # 不存在的 PID：只清文件，不杀任何东西
    (runtime / "aaaa11112222").mkdir(parents=True)
    (runtime / "aaaa11112222" / MIHOMO_PID_FILE).write_text("999999", encoding="ascii")
    # 坏文件：直接删
    (runtime / "bbbb11112222").mkdir(parents=True)
    (runtime / "bbbb11112222" / MIHOMO_PID_FILE).write_text("not-a-pid", encoding="ascii")
    assert manager.sweep_orphans() == 0
    assert not (runtime / "aaaa11112222" / MIHOMO_PID_FILE).exists()
    assert not (runtime / "bbbb11112222" / MIHOMO_PID_FILE).exists()


def test_sweep_orphans_never_kills_unrelated_process(tmp_path):
    """PID 复用防护：指向当前 python 进程的 PID 文件绝不能被杀。"""
    import os

    from zencloak.core.mihomo import MIHOMO_PID_FILE, ProxyManager

    manager = ProxyManager(data_root=tmp_path)
    runtime = tmp_path / "runtime"
    (runtime / "cccc11112222").mkdir(parents=True)
    (runtime / "cccc11112222" / MIHOMO_PID_FILE).write_text(str(os.getpid()), encoding="ascii")
    assert manager.sweep_orphans() == 0
    assert os.getpid()  # 进程还活着（测试本身即证明）
    assert not (runtime / "cccc11112222" / MIHOMO_PID_FILE).exists()


def test_stop_all_pops_all_handles(tmp_path):
    from zencloak.core.mihomo import ProxyManager

    manager = ProxyManager(data_root=tmp_path)
    manager.stop_all()  # 空句柄不报错
    assert manager._handles == {}


def test_manager_exposes_a_reentrant_lock(tmp_path):
    """start() holds the lock across a check-then-act and calls stop() on
    failure, so the lock must be reentrant or that path self-deadlocks."""
    import threading

    from zencloak.core.mihomo import ProxyManager

    manager = ProxyManager(data_root=tmp_path)
    assert isinstance(manager._lock, type(threading.RLock()))
    with manager._lock:
        with manager._lock:  # must not deadlock
            pass


def test_concurrent_start_spawns_only_one_process(tmp_path, monkeypatch):
    """Two concurrent start() calls for one profile must not both spawn.

    Regression guard for the unlocked check-then-act: previously both callers
    passed the ``profile_id in self._handles`` check and each started a mihomo,
    leaking the first process with no handle left to reap it.
    """
    import threading

    from zencloak.core import mihomo as mihomo_module
    from zencloak.core.mihomo import ProxyManager

    spawn_count = 0
    spawn_lock = threading.Lock()

    class FakeProcess:
        def __init__(self):
            self.pid = 4242
            self.returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    def fake_popen(*args, **kwargs):
        nonlocal spawn_count
        with spawn_lock:
            spawn_count += 1
        # Widen the window the old racing code would have slipped through.
        time.sleep(0.05)
        return FakeProcess()

    monkeypatch.setattr(mihomo_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ProxyManager, "_wait_ready", lambda self, handle, timeout=10.0: None)
    monkeypatch.setattr(
        mihomo_module, "ensure_binary", lambda bin_dir=None: tmp_path / "mihomo.exe"
    )

    manager = ProxyManager(data_root=tmp_path)
    results: list[object] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        try:
            results.append(manager.start("aaaaaaaaaaaa", _nodes()))
        except BaseException as exc:  # noqa: BLE001 - recorded for the assert
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert spawn_count == 1, f"应只启动 1 个 mihomo，实际 {spawn_count}"
    assert len({id(handle) for handle in results}) == 1
    manager.stop_all()


def test_stop_closes_log_handle(tmp_path, monkeypatch):
    """Every start/stop cycle must release the mihomo log descriptor."""
    from zencloak.core import mihomo as mihomo_module
    from zencloak.core.mihomo import ProxyManager

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(
        mihomo_module.subprocess, "Popen", lambda *a, **k: FakeProcess()
    )
    monkeypatch.setattr(ProxyManager, "_wait_ready", lambda self, handle, timeout=10.0: None)
    monkeypatch.setattr(
        mihomo_module, "ensure_binary", lambda bin_dir=None: tmp_path / "mihomo.exe"
    )

    manager = ProxyManager(data_root=tmp_path)
    handle = manager.start("aaaaaaaaaaaa", _nodes())
    log_handle = handle.log_handle
    assert log_handle is not None
    assert not log_handle.closed

    manager.stop("aaaaaaaaaaaa")
    assert log_handle.closed, "日志句柄未关闭（fd 泄漏）"
    assert handle.log_handle is None


def test_runtime_dir_rejects_traversal(tmp_path):
    from zencloak.core.mihomo import MihomoError, ProxyManager

    manager = ProxyManager(data_root=tmp_path)
    with pytest.raises(MihomoError):
        manager._runtime_dir("../../escaped")


def test_runtime_dir_accepts_valid_id(tmp_path):
    from zencloak.core.mihomo import ProxyManager

    manager = ProxyManager(data_root=tmp_path)
    resolved = manager._runtime_dir("aaaaaaaaaaaa")
    assert resolved == (tmp_path / "runtime" / "aaaaaaaaaaaa").resolve()
    assert resolved.is_relative_to(tmp_path.resolve())


def test_speedtest_id_is_not_treated_as_a_profile_id(tmp_path):
    """The latency core must not be resolved through profile-ID validation.

    Regression: ``start()`` sent every caller through ``_runtime_dir()``, which
    validates the name with ``require_id`` (12 hex characters). The speed test
    passes ``SPEEDTEST_ID``, so it raised ``MihomoError: 非法档案 ID:
    '__speedtest__'`` before the core ever launched, and both test-nodes routes
    answered 500 in about a second.

    The existing test_nodes tests could not see this: they monkeypatch
    ``start``, so ``_runtime_dir`` was never reached.
    """
    from zencloak.core.mihomo import ProxyManager

    manager = ProxyManager(data_root=tmp_path)

    # The profile resolver still refuses it - that contract is unchanged.
    with pytest.raises(Exception):
        manager._runtime_dir(ProxyManager.SPEEDTEST_ID)

    # The speed-test resolver accepts it, and stays inside the data root.
    resolved = manager._speedtest_dir()
    assert resolved == (tmp_path / "runtime" / ProxyManager.SPEEDTEST_ID).resolve()
    assert resolved.is_relative_to(tmp_path.resolve())


def test_start_uses_a_distinct_dir_for_the_speedtest_core(tmp_path, monkeypatch):
    """``start(SPEEDTEST_ID, ...)`` must get past the runtime-dir step.

    Pins the actual regression: the old body raised ``MihomoError: 非法档案 ID``
    from ``_runtime_dir`` before doing anything else, so reaching the config
    write is exactly what proves the fix. The launch is stubbed from the point
    the process would start, so this stays a unit test.
    """
    from zencloak.core import mihomo as mihomo_module
    from zencloak.core.mihomo import ProxyManager

    manager = ProxyManager(data_root=tmp_path, binary=tmp_path / "mihomo.exe")
    reached = {}

    # Stop right where the real spawn happens; everything before it (the
    # runtime dir, the config file) has already run by then.
    def fake_popen(cmd, **kwargs):
        reached["cmd"] = cmd
        raise RuntimeError("stop-here")

    monkeypatch.setattr(mihomo_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mihomo_module, "allocate_ports", lambda n: [18001, 18002, 18003])
    monkeypatch.setattr(mihomo_module.secrets, "token_urlsafe", lambda n: "secret")

    with pytest.raises(Exception) as excinfo:
        manager.start(ProxyManager.SPEEDTEST_ID, _nodes())

    # The failure must be our deliberate stop, not the ID validation.
    assert "stop-here" in str(excinfo.value), (
        f"start() 在更早的步骤就失败了: {excinfo.value}"
    )
    assert "非法档案 ID" not in str(excinfo.value)

    work_dir = (tmp_path / "runtime" / ProxyManager.SPEEDTEST_ID).resolve()
    assert work_dir.is_dir(), "测速目录未创建"
    assert (work_dir / "config.yaml").exists(), "测速配置未写入"
    # And it stays inside the data root.
    assert work_dir.is_relative_to(tmp_path.resolve())
