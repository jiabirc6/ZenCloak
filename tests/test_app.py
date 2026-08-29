import json

from zencloak.app import _runtime_info_path, write_runtime_info


def test_write_runtime_info_publishes_base_url_and_token(tmp_path):
    info_path = write_runtime_info(tmp_path, "http://127.0.0.1:12345", "tok-1")
    assert info_path == _runtime_info_path(tmp_path)
    data = json.loads(info_path.read_text(encoding="utf-8"))
    assert data == {"base_url": "http://127.0.0.1:12345", "token": "tok-1"}
