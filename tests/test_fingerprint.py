import random

import pytest

from zencloak.core.fingerprint import default_profile_draft, generate_seed


def test_generate_seed_is_within_range():
    value = generate_seed(random.Random(7))
    assert 10000 <= value <= 99999


def test_generate_seed_is_deterministic_for_same_source():
    assert generate_seed(random.Random(42)) == generate_seed(random.Random(42))


def test_generate_seed_from_os_random_still_in_range():
    value = generate_seed()
    assert 10000 <= value <= 99999


def test_default_profile_draft_has_valid_fingerprint_values():
    draft = default_profile_draft()
    assert draft["name"] == "本地档案"
    assert 10000 <= draft["seed"] <= 99999
    assert draft["timezone"] == "Asia/Shanghai"
    assert draft["locale"] == "zh-CN"
    assert draft["screen_width"] == 1920
    assert draft["screen_height"] == 1080
    assert draft["platform"] == "windows"
    assert draft["humanize"] is False
    assert draft["proxy"] is None


def test_default_profile_draft_contains_supported_option_values():
    draft = default_profile_draft()
    assert draft["hardware_concurrency"] in (2, 4, 8, 12, 16)
    assert draft["device_memory"] in (4, 8, 16, 32)
    assert draft["human_preset"] in ("default", "careful", "quick")
    assert draft["color"] in (
        "#0ea5a4",
        "#f59e0b",
        "#22c55e",
        "#38bdf8",
        "#f472b6",
    )


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1920, 1080),
        (2560, 1440),
    ],
)
def test_supported_screens_are_normalized(width, height):
    from zencloak.core.fingerprint import normalize_screen

    normalized = normalize_screen(width, height)
    assert normalized["screen_width"] == width
    assert normalized["screen_height"] == height


def test_unknown_screen_size_is_rejected():
    from zencloak.core.fingerprint import normalize_screen

    with pytest.raises(ValueError):
        normalize_screen(1234, 5678)
