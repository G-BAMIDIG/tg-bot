from telebot import types
from locales import t
from utils import traffic_label, format_toman, duration_label
from extra_config import RENEW_MAX_MONTHS, RENEW_MIN_GB, RENEW_MAX_GB
from config import SUPPORT_USER_ID, SUPPORT_USERNAME, HOWTO_PLATFORMS


def lang_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    )
    return kb


def main_menu_kb(lang):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(t("btn_buy", lang), callback_data="menu_buy"),
        types.InlineKeyboardButton(t("btn_howto", lang), callback_data="menu_howto"),
    )
    kb.add(
        types.InlineKeyboardButton(t("btn_support", lang), callback_data="menu_support"),
        types.InlineKeyboardButton(t("btn_mysubs", lang), callback_data="menu_mysubs"),
    )
    kb.add(
        types.InlineKeyboardButton(t("btn_myorders", lang), callback_data="menu_myorders"),
        types.InlineKeyboardButton(t("btn_faq", lang), callback_data="menu_faq"),
    )
    kb.add(types.InlineKeyboardButton(t("btn_share", lang), callback_data="menu_share"))
    return kb


def back_kb(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def support_kb(lang):
    # No button here on purpose - the @username in the message text itself
    # is what Telegram auto-links, no separate "open profile" button and no
    # phone number anywhere.
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def support_url():
    if SUPPORT_USER_ID:
        return f"tg://user?id={SUPPORT_USER_ID}"
    return f"https://t.me/{SUPPORT_USERNAME}"


# ---- Buy flow: category -> tier list -> plan detail ----
def buy_category_kb(lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(t("btn_custom_plan", lang), callback_data="buy_custom"))
    kb.add(types.InlineKeyboardButton(t("btn_1month", lang), callback_data="buy_duration_30"))
    kb.add(types.InlineKeyboardButton(t("btn_3months", lang), callback_data="buy_duration_90"))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def custom_plan_kb(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_ok", lang), url=support_url()))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_buy"))
    return kb


def best_value_plan_id(plans):
    """Plan with the lowest price per GB (only meaningful with 2+ plans)."""
    candidates = [p for p in plans if p["traffic_gb"]]
    if len(candidates) < 2:
        return None
    return min(candidates, key=lambda p: p["price"] / p["traffic_gb"])["id"]


def tier_kb(plans, lang):
    kb = types.InlineKeyboardMarkup()
    best_id = best_value_plan_id(plans)
    for p in plans:
        label = f"{traffic_label(p['traffic_gb'], lang)} — {format_toman(p['price'])}"
        if p["id"] == best_id:
            label = f"{t('badge_best_value', lang)} · {label}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"plan_{p['id']}"))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_buy"))
    return kb


def plan_selected_kb(lang, plan_id, duration_days):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(t("btn_back", lang), callback_data=f"buy_duration_{duration_days}"),
        types.InlineKeyboardButton(t("btn_finalize", lang), callback_data=f"finalize_{plan_id}"),
    )
    return kb


def discount_prompt_kb(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_skip_discount", lang), callback_data="discount_skip"))
    return kb


def order_payment_kb(lang, order_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            t("btn_sent_receipt", lang), callback_data=f"order_paid_{order_id}"
        )
    )
    return kb


def platforms_kb(lang):
    kb = types.InlineKeyboardMarkup()
    for key, info in HOWTO_PLATFORMS.items():
        kb.add(types.InlineKeyboardButton(info["label"][lang], callback_data=f"howto_{key}"))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def platform_detail_kb(lang, platform_key):
    info = HOWTO_PLATFORMS[platform_key]
    kb = types.InlineKeyboardMarkup()
    for d in info["downloads"]:
        kb.add(types.InlineKeyboardButton(d["label"][lang], url=d["url"]))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_howto"))
    return kb


def mysubs_kb(subs, lang):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for s in subs:
        raw_label = f"{t('btn_get_url', lang)} — {s['sub_name'] or s['plan_name']}"
        label = f"\u200f{raw_label}" if lang == "fa" else raw_label
        kb.add(types.InlineKeyboardButton(label, callback_data=f"getlink_{s['id']}"))
        kb.add(types.InlineKeyboardButton(t("btn_update_sub", lang), callback_data=f"renew_{s['id']}"))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def renew_months_kb(lang):
    kb = types.InlineKeyboardMarkup(row_width=3)
    options = [n for n in (1, 2, 3, 6, 12) if n <= RENEW_MAX_MONTHS]
    kb.add(*[
        types.InlineKeyboardButton(duration_label(30 * n, lang), callback_data=f"rmonths_{n}")
        for n in options
    ])
    kb.add(types.InlineKeyboardButton(t("btn_months_skip", lang), callback_data="rmonths_0"))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_mysubs"))
    return kb


def renew_gb_kb(lang):
    kb = types.InlineKeyboardMarkup(row_width=3)
    options = [g for g in (20, 50, 100, 200, 400, 600) if RENEW_MIN_GB <= g <= RENEW_MAX_GB]
    kb.add(*[
        types.InlineKeyboardButton(traffic_label(g, lang), callback_data=f"rgb_{g}")
        for g in options
    ])
    kb.add(types.InlineKeyboardButton(t("btn_gb_skip", lang), callback_data="rgb_0"))
    return kb


def rating_kb(order_id):
    kb = types.InlineKeyboardMarkup(row_width=5)
    kb.add(*[
        types.InlineKeyboardButton("⭐" * n, callback_data=f"rate_{order_id}_{n}") for n in range(1, 6)
    ])
    return kb


def share_kb(lang, url):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_share_now", lang), url=url))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def admin_renewal_kb(order_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("👀 Seen", callback_data=f"seen_{order_id}"),
        types.InlineKeyboardButton("✅ Approve renewal", callback_data=f"rapprove_{order_id}"),
        types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_{order_id}"),
    )
    return kb


def admin_order_card_kb(order):
    """Buttons under /order <id>, depending on where the order is."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    oid = order["id"]
    if order["status"] == "awaiting_admin":
        if order["kind"] == "renewal":
            kb.add(types.InlineKeyboardButton("✅ Approve renewal", callback_data=f"rapprove_{oid}"))
        else:
            kb.add(types.InlineKeyboardButton("📦 Deliver subscription", callback_data=f"deliver_{oid}"))
        kb.add(types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_{oid}"))
    elif order["status"] in ("delivered",):
        kb.add(types.InlineKeyboardButton("💸 Record refund", callback_data=f"refund_{oid}"))
    kb.add(types.InlineKeyboardButton("👤 View user", callback_data=f"uview_{order['user_id']}"))
    return kb


def reminder_kb(lang, sub_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_update_sub", lang), callback_data=f"renew_{sub_id}"))
    return kb


def admin_user_kb(user_id, banned, flagged, subs=()):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✉️ Message", callback_data=f"umsg_{user_id}"),
        types.InlineKeyboardButton("➕ Add subscription", callback_data=f"uadd_{user_id}"),
    )
    for sub in subs:
        kb.add(types.InlineKeyboardButton(
            f"📶 Usage notice — #{sub['id']} {sub['sub_name'] or ''}".strip(),
            callback_data=f"usub_{sub['id']}",
        ))
    if banned:
        kb.add(types.InlineKeyboardButton("🔓 Unban", callback_data=f"unban_{user_id}"))
    else:
        kb.add(types.InlineKeyboardButton("🚫 Ban", callback_data=f"uban_{user_id}"))
    if flagged:
        kb.add(types.InlineKeyboardButton("🏳️ Clear flag", callback_data=f"unflag_{user_id}"))
    return kb


def admin_flag_alert_kb(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🚫 Ban", callback_data=f"uban_{user_id}"),
        types.InlineKeyboardButton("🏳️ Dismiss", callback_data=f"unflag_{user_id}"),
    )
    return kb


def admin_panel_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📋 Pending", callback_data="adm_pending"),
        types.InlineKeyboardButton("📊 Stats", callback_data="adm_stats"),
        types.InlineKeyboardButton("🖥 Dashboard", callback_data="adm_dashboard"),
        types.InlineKeyboardButton("💾 Backup now", callback_data="adm_backup"),
        types.InlineKeyboardButton("🕙 Toggle hours", callback_data="adm_hours"),
        types.InlineKeyboardButton("🎟 Discounts", callback_data="adm_discounts"),
        types.InlineKeyboardButton("➕ New discount", callback_data="adm_adddiscount"),
        types.InlineKeyboardButton("💲 Update prices", callback_data="adm_renewprices"),
        types.InlineKeyboardButton("📦 Update plans", callback_data="adm_updateplans"),
        types.InlineKeyboardButton("✉️ Message a user", callback_data="adm_message"),
        types.InlineKeyboardButton("👤 Find a user", callback_data="adm_user"),
        types.InlineKeyboardButton("🧾 Find an order", callback_data="adm_order"),
        types.InlineKeyboardButton("🚫 Ban", callback_data="adm_ban"),
        types.InlineKeyboardButton("🔓 Unban", callback_data="adm_unban"),
        types.InlineKeyboardButton("💸 Refund", callback_data="adm_refund"),
        types.InlineKeyboardButton("➕ Add subscription", callback_data="adm_addsub"),
        types.InlineKeyboardButton("📶 Usage notice", callback_data="adm_usage"),
        types.InlineKeyboardButton("❓ All commands", callback_data="adm_help"),
    )
    return kb


def admin_order_kb(order_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("👀 Seen", callback_data=f"seen_{order_id}"),
        types.InlineKeyboardButton("📦 Deliver subscription", callback_data=f"deliver_{order_id}"),
        types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_{order_id}"),
    )
    return kb


def admin_unban_shortcut_kb(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔓 Unban now", callback_data=f"unban_{user_id}"))
    return kb
