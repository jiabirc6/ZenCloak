from zencloak.core.lock import InstanceLock


def test_lock_can_only_be_acquired_once(tmp_path):
    lock_path = tmp_path / "zencloak.lock"
    first = InstanceLock(lock_path)
    second = InstanceLock(lock_path)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
