import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .fingerprint import (
    DEVICE_MEMORIES,
    HARDWARE_CONCURRENCIES,
    HUMAN_PRESETS,
    SUPPORTED_SCREENS,
)

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def _default_scheme(value: str) -> str:
    host_part = value.split("/", 1)[0]
    host = host_part.split(":", 1)[0].lower()
    return "http://" if host in _LOCAL_HOSTS else "https://"


def normalize_start_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _SCHEME_RE.match(value):
        value = _default_scheme(value) + value
    return value


class ProxySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["http", "socks5"]
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    username: str = ""
    password: str = ""


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=12, max_length=12)
    name: str = Field(min_length=1, max_length=32)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    notes: str = ""
    seed: int = Field(ge=10000, le=99999)
    timezone: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    platform: Literal["windows"] = "windows"
    screen_width: int
    screen_height: int
    hardware_concurrency: int
    device_memory: int
    user_agent: str | None = None
    proxy: ProxySettings | None = None
    humanize: bool = False
    human_preset: Literal["default", "careful", "quick"] = "default"
    start_url: str | None = None
    headless: bool = False
    created_at: str
    updated_at: str

    @field_validator("hardware_concurrency")
    @classmethod
    def hardware_concurrency_supported(cls, value: int) -> int:
        if value not in HARDWARE_CONCURRENCIES:
            raise ValueError("Unsupported hardware concurrency")
        return value

    @field_validator("device_memory")
    @classmethod
    def device_memory_supported(cls, value: int) -> int:
        if value not in DEVICE_MEMORIES:
            raise ValueError("Unsupported device memory")
        return value

    @field_validator("human_preset")
    @classmethod
    def human_preset_supported(cls, value: str) -> str:
        if value not in HUMAN_PRESETS:
            raise ValueError("Unsupported human preset")
        return value

    @field_validator("start_url")
    @classmethod
    def normalize_start_url(cls, value: str | None) -> str | None:
        return normalize_start_url(value)

    @model_validator(mode="after")
    def screen_pair_supported(self) -> "Profile":
        if (self.screen_width, self.screen_height) not in SUPPORTED_SCREENS:
            raise ValueError("Unsupported screen size")
        return self
