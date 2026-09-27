import re
import time
import requests

from config import (
    DOLLAR_RATE_URL,
    DOLLAR_RATE_CACHE_SECONDS,
    DOLLAR_RATE_FALLBACK,
)

_cache = {"rate": None, "ts": 0}


def get_usd_to_toman_rate():
    """
    Scrapes tgju.org for the current USD price (shown in Rial) and converts
    to Toman (Rial / 10). Cached for DOLLAR_RATE_CACHE_SECONDS so we don't
    hit the site on every message. Falls back to the last known value, or
    DOLLAR_RATE_FALLBACK if we've never fetched successfully.
    """
    now = time.time()
    if _cache["rate"] and now - _cache["ts"] < DOLLAR_RATE_CACHE_SECONDS:
        return _cache["rate"]
    try:
        resp = requests.get(
            DOLLAR_RATE_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
        html = resp.text
        # Looks for "نرخ فعلی:" followed by a number (site shows the value in Rial)
        m = re.search(r"نرخ فعلی[^\d]{0,30}([\d,]{4,})", html)
        if not m:
            raise ValueError("rate not found on page - site layout may have changed")
        raw_rial = int(m.group(1).replace(",", ""))
        toman_rate = raw_rial / 10
        _cache["rate"] = toman_rate
        _cache["ts"] = now
        return toman_rate
    except Exception:
        return _cache["rate"] or DOLLAR_RATE_FALLBACK


def toman_to_usd_approx(toman_amount):
    """Returns a string like '~$12.34', or '' if no rate is available."""
    rate = get_usd_to_toman_rate()
    if not rate:
        return ""
    usd = toman_amount / rate
    return f"~${usd:,.2f}"


def format_toman(amount):
    """1000000 -> RLM + '1000000 تومان (T)' - no thousands separator.
    The leading RLM (Right-to-Left Mark, U+200F) is a zero-width character
    that tells the renderer 'this whole run is RTL' - without it, a string
    that starts with a plain number followed by Persian text can get its
    pieces reordered unpredictably when embedded next to other text (this
    is what caused the Persian plan listings to look scrambled)."""
    return f"\u200f{int(amount)} تومان (T)"


def duration_label(duration_days, lang):
    months = 1 if duration_days == 31 else 3 if duration_days == 90 else max(1, round(duration_days / 30))
    if lang == "fa":
        return f"\u200f{months} ماهه"
    return f"{months} Month" + ("" if months == 1 else "s")


def traffic_label(traffic_gb, lang):
    # Unlimited plans store free text (e.g. "نامحدود تک کاربر") instead of
    # a number - show it as-is rather than appending "GB"/"گیگابایت" to it.
    if isinstance(traffic_gb, str) and not traffic_gb.isdigit():
        if lang == "fa":
            return f"\u200f{traffic_gb}"
        return traffic_gb
    if lang == "fa":
        return f"\u200f{traffic_gb} گیگابایت"
    return f"{traffic_gb}GB"


def gregorian_to_jalali(gy, gm, gd):
    """Standard Gregorian -> Jalali (Persian) calendar conversion algorithm.
    Pure Python, no dependency - avoids relying on a pip package that might
    fail to install. Returns (jalali_year, jalali_month, jalali_day)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def format_jalali_date(dt):
    """datetime -> 'YYYY/MM/DD' Jalali date string."""
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy}/{jm:02d}/{jd:02d}"


def parse_ban_duration(text):
    """Accepts '24', '24h', '3d', '1.5d' etc, returns hours as a float, or
    None if it couldn't be parsed."""
    text = text.strip().lower().replace(" ", "")
    try:
        if text.endswith("d"):
            return float(text[:-1]) * 24
        if text.endswith("h"):
            return float(text[:-1])
        return float(text)
    except ValueError:
        return None


def format_remaining(until_dt, lang="en"):
    """datetime -> human countdown string, e.g. '2d 4h' / '۲ روز و ۴ ساعت'."""
    from datetime import datetime as _dt, timezone as _tz

    now = _dt.now(_tz.utc)
    if until_dt.tzinfo is None:
        until_dt = until_dt.replace(tzinfo=_tz.utc)
    delta = until_dt - now
    total_seconds = max(0, int(delta.total_seconds()))
    # Round UP to the nearest minute so a subscription bought for "31 days"
    # reads as "31d" right away instead of "30d 23h 59m" (the couple of
    # seconds it took to process the order shouldn't visibly shrink it).
    import math

    total_minutes = math.ceil(total_seconds / 60)
    days, rem = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem, 60)
    if lang == "fa":
        parts = []
        if days:
            parts.append(f"{days} روز")
        if hours:
            parts.append(f"{hours} ساعت")
        if not days and minutes:
            parts.append(f"{minutes} دقیقه")
        return " و ".join(parts) if parts else "کمتر از یک دقیقه"
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if not days and minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "less than a minute"
