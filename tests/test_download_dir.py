"""Tests for the per-profile download directory.

Downloads used to always land in ``<data root>/data/<id>/Downloads``, which is
both hard to find and impossible to change, so a user who downloaded a file
could not locate it afterwards. A profile may now point at any folder on the
machine.
"""

import tempfile
from pathlib import Path

import pytest

from zencloak.core.downloads_dir import download_dir_for
from zencloak.core.fingerprint import default_profile_draft
from zencloak.core.profiles import ProfileStore
from zencloak.core.sessions import SessionManager


@pytest.fixture()
def store(tmp_path):
    return ProfileStore(tmp_path, auto_init=False)


def _draft(**over):
    return {**default_profile_draft(), "name": "下载测试", **over}


def test_default_is_the_per_profile_folder(store):
    profile = store.create_profile(_draft())
    resolved = download_dir_for(store, profile)
    assert resolved == store.profile_data_subdir(profile["id"], "Downloads")


def test_custom_directory_wins(store, tmp_path):
    custom = tmp_path / "D盘下载" / "浏览器"
    profile = store.create_profile(_draft(download_dir=str(custom)))
    assert download_dir_for(store, profile) == custom


def test_custom_directory_is_outside_the_data_root(store, tmp_path):
    """The point of the setting is to escape the data root, so it must not be
    confined to it."""
    custom = tmp_path / "totally-elsewhere"
    profile = store.create_profile(_draft(download_dir=str(custom)))
    resolved = download_dir_for(store, profile)
    assert not resolved.is_relative_to(store.data_dir)


def test_blank_values_fall_back_to_default(store):
    for blank in ("", "   ", None):
        profile = store.create_profile(_draft(download_dir=blank))
        assert profile["download_dir"] is None
        assert download_dir_for(store, profile) == store.profile_data_subdir(
            profile["id"], "Downloads"
        )


def test_surrounding_quotes_are_stripped(store, tmp_path):
    """Users paste paths copied from Explorer, which arrive quoted."""
    quoted = f'"{tmp_path / "quoted dir"}"'
    profile = store.create_profile(_draft(download_dir=quoted))
    assert profile["download_dir"] == str(tmp_path / "quoted dir")


def test_relative_paths_are_rejected(store):
    with pytest.raises(ValueError):
        store.create_profile(_draft(download_dir="relative/downloads"))
    with pytest.raises(ValueError):
        store.create_profile(_draft(download_dir="./downloads"))


def test_null_byte_is_rejected(store):
    with pytest.raises(ValueError):
        store.create_profile(_draft(download_dir="C:\\bad\x00path"))


def test_path_may_not_exist_yet(store, tmp_path):
    """Choosing a folder before creating it must be allowed; the session
    creates it at launch."""
    future = tmp_path / "not-created-yet"
    profile = store.create_profile(_draft(download_dir=str(future)))
    assert download_dir_for(store, profile) == future
    assert not future.exists()


def test_unc_style_path_is_accepted(store):
    profile = store.create_profile(_draft(download_dir=r"\\server\share\dl"))
    assert profile["download_dir"] == r"\\server\share\dl"


def test_session_manager_uses_the_custom_directory(store, tmp_path):
    """Launch kwargs must point the browser at the chosen folder."""
    custom = tmp_path / "session-custom"
    manager = SessionManager(data_root=store.data_dir)
    profile = store.create_profile(_draft(download_dir=str(custom)))

    resolved = manager._downloads_dir(profile)
    assert resolved == custom

    kwargs = manager._build_launch_kwargs(profile)
    assert Path(kwargs["downloads_path"]) == custom


def test_session_manager_falls_back_without_custom_dir(store):
    manager = SessionManager(data_root=store.data_dir)
    profile = store.create_profile(_draft())
    resolved = manager._downloads_dir(profile)
    assert resolved == store.profile_data_subdir(profile["id"], "Downloads")
    kwargs = manager._build_launch_kwargs(profile)
    assert Path(kwargs["downloads_path"]) == resolved


def test_update_persists_the_directory(store, tmp_path):
    profile = store.create_profile(_draft())
    custom = tmp_path / "updated"
    store.update_profile(profile["id"], {"download_dir": str(custom)})
    reloaded = store.get_profile(profile["id"])
    assert reloaded["download_dir"] == str(custom)


def test_clearing_the_directory_persists(store, tmp_path):
    profile = store.create_profile(_draft(download_dir=str(tmp_path / "x")))
    store.update_profile(profile["id"], {"download_dir": None})
    reloaded = store.get_profile(profile["id"])
    assert reloaded["download_dir"] is None
