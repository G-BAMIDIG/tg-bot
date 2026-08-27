from telebot import types
from locales import t
from utils import traffic_label, format_toman
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
    kb.add(types.InlineKeyboardButton(t("btn_faq", lang), callback_data="menu_faq"))
    kb.add(types.InlineKeyboardButton(t("btn_changelang", lang), callback_data="menu_changelang"))
    return kb


def home_reply_kb(lang):
    """Persistent keyboard (sits under the text box, not inline on a message)
    so there's always a working way back to the main menu, even on screens
    where the inline 'Back' button doesn't apply - no more needing to type
    /start by hand."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(t("btn_home", lang)))
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
    kb.add(types.InlineKeyboardButton(t("btn_1month", lang), callback_data="buy_duration_31"))
    kb.add(types.InlineKeyboardButton(t("btn_3months", lang), callback_data="buy_duration_90"))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
    return kb


def custom_plan_kb(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_ok", lang), url=support_url()))
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_buy"))
    return kb


def tier_kb(plans, lang):
    kb = types.InlineKeyboardMarkup()
    for p in plans:
        label = f"{traffic_label(p['traffic_gb'], lang)} — {format_toman(p['price'])}"
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
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data="menu_back"))
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
