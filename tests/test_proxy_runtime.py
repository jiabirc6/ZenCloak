from zencloak.core.proxy_runtime import allocate_ports


def test_allocate_ports_returns_distinct_ports():
    ports = allocate_ports(3)
    assert len(ports) == 3
    assert len(set(ports)) == 3


def test_allocate_ports_rejects_zero():
    import pytest

    with pytest.raises(ValueError):
        allocate_ports(0)
