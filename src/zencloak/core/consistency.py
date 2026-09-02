"""Proxy/fingerprint consistency preflight checks.

After a profile launches through a proxy, its fingerprint (timezone,
locale) should match the proxy's egress location. A US exit node with
an Asia/Shanghai clock is an easy anti-fraud signal, so the panel runs
these checks against the running proxy and offers one-click fixes.
"""

import json
import urllib.request

IPINFO_URL = "https://ipinfo.io/json"
IPAPI_URL = "http://ip-api.com/json"


class ConsistencyError(RuntimeError):
    """Raised when the egress IP location cannot be determined."""


def _fetch_json(
    url: str, proxy_url: str | None = None, timeout: float = 10.0
) -> dict:
    handlers = (
        [urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})]
        if proxy_url
        else []
    )
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 ZenCloak"}
    )
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def lookup_ip_geo(
    proxy_url: str | None = None,
    timeout: float = 10.0,
    fetch=_fetch_json,
) -> dict:
    """Resolve the egress IP location, preferring ipinfo then ip-api."""
    last_error: Exception | None = None
    for url in (IPINFO_URL, IPAPI_URL):
        try:
            data = fetch(url, proxy_url, timeout)
        except Exception as exc:  # noqa: BLE001 - try the next provider
            last_error = exc
            continue
        geo = {
            "ip": data.get("ip") or data.get("query"),
            # countryCode 是 ISO 码（两家都有）；ip-api 的 country 是全称
            # （"United States"），只在拿不到码时兜底。
            "country": (data.get("countryCode") or data.get("country") or "").upper()
            or None,
            "city": data.get("city"),
            "timezone": data.get("timezone"),
        }
        if geo["ip"]:
            return geo
    raise ConsistencyError(f"出口 IP 查询失败: {last_error}")


# ip-api 等源的 country 字段可能是英文全称；locale 比较需要 ISO 码。
# 只收录常见出口国家，其余走精确匹配不受影响。
COUNTRY_NAME_TO_CODE = {
    "UNITED STATES": "US",
    "HONG KONG": "HK",
    "JAPAN": "JP",
    "SINGAPORE": "SG",
    "TAIWAN": "TW",
    "SOUTH KOREA": "KR",
    "KOREA, REPUBLIC OF": "KR",
    "GERMANY": "DE",
    "UNITED KINGDOM": "GB",
    "FRANCE": "FR",
    "NETHERLANDS": "NL",
    "CANADA": "CA",
    "AUSTRALIA": "AU",
    "RUSSIA": "RU",
    "TURKEY": "TR",
    "MALAYSIA": "MY",
    "THAILAND": "TH",
    "VIETNAM": "VN",
    "PHILIPPINES": "PH",
    "INDIA": "IN",
    "BRAZIL": "BR",
    "ARGENTINA": "AR",
    "MEXICO": "MX",
    "CHINA": "CN",
    "MACAO": "MO",
    "MACAU": "MO",
}


def normalize_country(value: str | None) -> str | None:
    """Normalize a country field to an ISO-2-ish code when recognizable."""
    if not value:
        return None
    upper = value.strip().upper()
    if len(upper) == 2:
        return upper
    return COUNTRY_NAME_TO_CODE.get(upper, upper)


def country_from_locale(locale: str | None) -> str | None:
    """Extract the ISO country code from a BCP-47 locale like zh-CN."""
    if not locale or "-" not in locale:
        return None
    region = locale.rsplit("-", 1)[-1]
    return region.upper() if len(region) == 2 and region.isalpha() else None


def check_consistency(profile: dict, geo: dict) -> list[dict]:
    """Compare a profile's fingerprint settings against the egress location.

    Returns a list of warnings; each has a ``kind`` the UI can act on.
    """
    warnings: list[dict] = []
    profile_timezone = profile.get("timezone")
    ip_timezone = geo.get("timezone")
    if profile_timezone and ip_timezone and profile_timezone != ip_timezone:
        warnings.append(
            {
                "kind": "timezone",
                "message": f"档案时区 {profile_timezone} 与出口 IP 时区 {ip_timezone} 不一致",
                "suggested_timezone": ip_timezone,
            }
        )
    locale_country = country_from_locale(profile.get("locale"))
    ip_country = normalize_country(geo.get("country"))
    if locale_country and ip_country and locale_country != ip_country:
        warnings.append(
            {
                "kind": "locale",
                "message": f"语言 {profile.get('locale')} 与出口国家 {ip_country} 不一致",
            }
        )
    return warnings
