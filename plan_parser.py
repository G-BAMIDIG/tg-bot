"""
Shared logic for turning a raw plan-list message (copied from another bot)
into structured plan dicts, with your resale markup applied.

Used by:
- bot.py's /updateplans admin command (paste the text yourself, no login needed)
- scraper.py (optional fully-automated version, needs Telegram API credentials)
"""

import re


def parse_admin_plan_lines(text: str):
    """
    Parses plans YOU type yourself, one per line, already-final prices:

        1 - 20 - 98000        (1 month, 20GB, 98,000 Toman final price)
        3 - 150 - 564000      (3 months, 150GB, 564,000 Toman final price)

    No markup is applied - whatever price you type is exactly what the
    customer is charged. Returns a list of dicts:
    {duration_days, traffic_gb, price}
    """
    plans = []
    # Traffic field can be a plain number (GB) OR free text like
    # "نامحدود تک کاربر" (unlimited, single user) - so it's captured as
    # anything up to the next " - ", not just digits.
    pattern = re.compile(r"^\s*(\d+)\s*-\s*(.+?)\s*-\s*([\d,]+)\s*$")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if not m:
            continue
        months = int(m.group(1))
        traffic_raw = m.group(2).strip()
        price = int(m.group(3).replace(",", ""))
        duration_days = 31 if months == 1 else 90 if months == 3 else months * 30
        if traffic_raw.isdigit():
            traffic_gb = int(traffic_raw)
        else:
            # Unlimited plan (or any other non-numeric label) - store the
            # text as-is, e.g. "نامحدود تک کاربر" / "نامحدود دو کاربر".
            traffic_gb = traffic_raw
        plans.append({"duration_days": duration_days, "traffic_gb": traffic_gb, "price": price})
    return plans


def parse_plan_detail_message(text: str, markup_multiplier: float = 1.0):
    """
    Parses a single plan-detail message in the format you showed me:

        🛍 GVPNاسم محصول: 🚀 مولتی لوکیشن ویژه
        ⏳ مدت زمان: 1 ماهه
        ♾ مقدار ترافیک: 20 گیگابایت
        ...
        💳 قیمت نهایی: 250,000 تومان

    Returns a single dict {name, duration_label, duration_days, traffic, price}
    or None if the fields couldn't be found. price already has markup applied.
    """
    name_m = re.search(r"اسم محصول:\s*(.+)", text)
    duration_m = re.search(r"مدت زمان:\s*(.+)", text)
    traffic_m = re.search(r"مقدار ترافیک:\s*(.+)", text)
    price_m = re.search(r"قیمت نهایی:\s*([\d,]+)", text)

    if not (name_m and duration_m and price_m):
        return None

    duration_label = duration_m.group(1).strip()
    duration_days = 30
    if "3" in duration_label:
        duration_days = 90
    elif "6" in duration_label:
        duration_days = 180
    elif "12" in duration_label or "سال" in duration_label:
        duration_days = 365

    source_price = float(price_m.group(1).replace(",", ""))

    return {
        "name": f"{duration_label} - {traffic_m.group(1).strip() if traffic_m else ''}".strip(" -"),
        "duration_label": duration_label,
        "duration_days": duration_days,
        "traffic": traffic_m.group(1).strip() if traffic_m else "",
        "price": round(source_price * markup_multiplier, 2),
    }


def parse_plans_message(raw_text: str, markup_multiplier: float = 1.0):
    """
    Customize this regex to match the other bot's actual message format.
    Currently expects lines roughly like:

        1 Month - 30GB - 150000 Toman
        3 Months - 100GB - 400000 Toman

    Returns a list of dicts: {name, description, price, duration_days}
    price already has markup_multiplier applied.
    """
    plans = []
    pattern = re.compile(
        r"(?P<name>.+?)\s*-\s*(?P<desc>.+?)\s*-\s*(?P<price>[\d,]+)", re.UNICODE
    )
    for line in raw_text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        name = m.group("name").strip()
        desc = m.group("desc").strip()
        source_price = float(m.group("price").replace(",", ""))
        price = round(source_price * markup_multiplier, 2)

        # naive duration guess from the name - adjust as needed
        duration_days = 30
        if "3" in name:
            duration_days = 90
        elif "6" in name:
            duration_days = 180
        elif "year" in name.lower() or "12" in name:
            duration_days = 365

        plans.append(
            {
                "name": name,
                "description": desc,
                "price": price,
                "duration_days": duration_days,
            }
        )
    return plans
