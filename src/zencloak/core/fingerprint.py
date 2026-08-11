import random

DEFAULT_COLORS = ("#0ea5a4", "#f59e0b", "#22c55e", "#38bdf8", "#f472b6")
SUPPORTED_SCREENS = (
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1920, 1080),
    (2560, 1440),
)
HARDWARE_CONCURRENCIES = (2, 4, 8, 12, 16)
DEVICE_MEMORIES = (4, 8, 16, 32)
HUMAN_PRESETS = ("default", "careful", "quick")


def generate_seed(rng: random.Random | None = None) -> int:
    """Return a stable fingerprint seed between 10000 and 99999."""
    return int((rng or random).randint(10000, 99999))


def normalize_screen(width: int, height: int) -> dict:
    """Return a supported screen pair or raise ValueError."""
    pair = (int(width), int(height))
    if pair not in SUPPORTED_SCREENS:
        raise ValueError(f"Unsupported screen size: {width}x{height}")
    return {"screen_width": pair[0], "screen_height": pair[1]}


def default_profile_draft() -> dict:
    """Return the personal default profile used on first launch."""
    return {
        "name": "本地档案",
        "color": DEFAULT_COLORS[0],
        "notes": "",
        "seed": generate_seed(),
        "timezone": "Asia/Shanghai",
        "locale": "zh-CN",
        "platform": "windows",
        "screen_width": 1920,
        "screen_height": 1080,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "user_agent": None,
        "proxy": None,
        "humanize": False,
        "human_preset": "default",
        "start_url": "https://www.baidu.com",
        "headless": False,
    }
