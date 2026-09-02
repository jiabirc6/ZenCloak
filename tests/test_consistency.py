import pytest

from zencloak.core.consistency import (
    ConsistencyError,
    check_consistency,
    country_from_locale,
    lookup_ip_geo,
)


def test_country_from_locale():
    assert country_from_locale("zh-CN") == "CN"
    assert country_from_locale("en-US") == "US"
    assert country_from_locale("zh") is None
    assert country_from_locale(None) is None
    assert country_from_locale("") is None


def test_check_consistency_clean():
    profile = {"timezone": "America/New_York", "locale": "en-US"}
    geo = {"ip": "1.2.3.4", "country": "US", "timezone": "America/New_York"}
    assert check_consistency(profile, geo) == []


def test_check_consistency_timezone_mismatch():
    profile = {"timezone": "Asia/Shanghai", "locale": "en-US"}
    geo = {"ip": "1.2.3.4", "country": "US", "timezone": "America/New_York"}
    warnings = check_consistency(profile, geo)
    kinds = [w["kind"] for w in warnings]
    assert "timezone" in kinds
    timezone_warning = next(w for w in warnings if w["kind"] == "timezone")
    assert timezone_warning["suggested_timezone"] == "America/New_York"


def test_check_consistency_locale_mismatch():
    profile = {"timezone": "America/New_York", "locale": "zh-CN"}
    geo = {"ip": "1.2.3.4", "country": "US", "timezone": "America/New_York"}
    warnings = check_consistency(profile, geo)
    kinds = [w["kind"] for w in warnings]
    assert "locale" in kinds


def test_check_consistency_missing_data_is_not_a_warning():
    profile = {"timezone": None, "locale": "zh"}
    geo = {"ip": "1.2.3.4", "country": None, "timezone": None}
    assert check_consistency(profile, geo) == []


def test_lookup_ip_geo_prefers_ipinfo():
    def fake_fetch(url, proxy_url, timeout):
        assert url == "https://ipinfo.io/json"
        assert proxy_url == "http://127.0.0.1:9999"
        return {"ip": "5.6.7.8", "country": "JP", "city": "Tokyo",
                "timezone": "Asia/Tokyo"}

    geo = lookup_ip_geo("http://127.0.0.1:9999", fetch=fake_fetch)
    assert geo == {
        "ip": "5.6.7.8",
        "country": "JP",
        "city": "Tokyo",
        "timezone": "Asia/Tokyo",
    }


def test_lookup_ip_geo_falls_back_to_ipapi():
    def fake_fetch(url, proxy_url, timeout):
        if "ipinfo" in url:
            raise OSError("down")
        return {"query": "9.9.9.9", "countryCode": "de", "city": "Berlin",
                "timezone": "Europe/Berlin"}

    geo = lookup_ip_geo(fetch=fake_fetch)
    assert geo["ip"] == "9.9.9.9"
    assert geo["country"] == "DE"


def test_lookup_ip_geo_all_providers_fail():
    def fake_fetch(url, proxy_url, timeout):
        raise OSError("down")

    with pytest.raises(ConsistencyError):
        lookup_ip_geo(fetch=fake_fetch)


def test_lookup_ip_geo_prefers_country_code_over_full_name():
    """ip-api 的 country 是全称（United States），必须优先取 countryCode。"""
    def fake_fetch(url, proxy_url, timeout):
        return {
            "query": "1.2.3.4",
            "country": "United States",
            "countryCode": "US",
            "city": "Los Angeles",
            "timezone": "America/Los_Angeles",
        }

    geo = lookup_ip_geo(fetch=fake_fetch)
    assert geo["country"] == "US"


def test_check_consistency_with_full_country_name_does_not_warn():
    geo = {"ip": "1.2.3.4", "country": "UNITED STATES", "timezone": "America/Los_Angeles"}
    profile = {"timezone": "America/Los_Angeles", "locale": "en-US"}
    assert check_consistency(profile, geo) == []
