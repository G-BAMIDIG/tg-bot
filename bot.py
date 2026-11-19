import html
import math
import os
import re
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import telebot
from telebot import types
from telebot.handler_backends import BaseMiddleware, CancelUpdate

import db
import keyboards as kb
import dashboard
import guard as guard_mod
import backup as backup_mod
from locales import t
from plan_parser import parse_admin_plan_lines
from utils import (
    format_toman,
    duration_label,
    traffic_label,
    format_jalali_date,
    parse_ban_duration,
    format_remaining,
)
from config import (
    BOT_TOKEN,
    ADMIN_ID,
    CARD_NUMBER,
    CARD_HOLDER_NAME,
    ALARM_INTERVAL_SECONDS,
    ALARM_MAX_PINGS,
    HOWTO_PLATFORMS,
    ORDER_FEE_PERCENT,
    FAQ_TEXT,
    SUPPORT_USERNAME,
    TIMEZONE,
    OPEN_HOUR,
    DB_PATH,
)
from extra_config import (
    ORDER_EXPIRY_MINUTES,
    DELIVERY_ETA_DEFAULT,
    RENEW_PRICE_PER_MONTH,
    RENEW_PRICE_PER_GB,
    RENEW_MIN_GB,
    RENEW_MAX_GB,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    FLOOD_STRIKES,
    FLOOD_BAN_MINUTES,
    FLAG_DECLINE_THRESHOLD,
    FLAG_WINDOW_DAYS,
    BACKUP_ENABLED,
    BACKUP_HOUR,
    DASHBOARD_ENABLED,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_PUBLIC_URL,
    BOT_USERNAME,
    REMINDER_DAYS,
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, use_class_middlewares=True)
db.init_db()

USERNAME_RE = re.compile(r"^[A-Za-z0-9]{5,15}$")


def _looks_like_command(text):
    """True if this text is a slash-command like /pending or /start.
    Every stateful 'waiting for the next message' handler below excludes
    these, so a leftover/abandoned conversation state can never swallow a
    real command - this was the actual bug behind admin commands going
    silent after an unfinished purchase flow."""
    return bool(text) and text.strip().startswith("/")

# in-memory conversation state: user_id -> dict
state = {}
# in-memory admin state
admin_state = {}
# stops repeating alarm threads when True: key is ("order", id)
alarm_stop_flags = {}

_guard = guard_mod.Guard(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW, FLOOD_STRIKES)


def _local_hhmm(dt_utc_naive):
    """Naive-UTC datetime -> 'HH:MM' in the bot's timezone."""
    return dt_utc_naive.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(TIMEZONE)).strftime("%H:%M")


def _not_admin(update):
    """True if the sender is NOT the admin - and (throttled to once per 5
    minutes per person) tells the admin someone tried an admin action."""
    uid = update.from_user.id
    if uid == ADMIN_ID:
        return False
    what = update.data if isinstance(update, types.CallbackQuery) else (update.text or "")
    if _guard.cooldown_ok("denied", uid, time.time(), 300):
        who = update.from_user.username or "-"
        try:
            bot.send_message(
                ADMIN_ID, f"🚨 Non-admin @{who} (id {uid}) tried an admin action: {str(what)[:80]}"
            )
        except Exception:
            pass
    return True


def get_lang(user_id):
    user = db.get_user(user_id)
    return user["lang"] if user and user["lang"] else "en"


def is_open_now():
    now = datetime.now(ZoneInfo(TIMEZONE))
    return now.hour >= OPEN_HOUR


def hours_restriction_enabled():
    return db.get_setting("hours_enabled", "1") == "1"


def send_ban_notice(user_id, ban_row):
    lang = get_lang(user_id)
    until_dt = datetime.fromisoformat(ban_row["until"])
    bot.send_message(
        user_id,
        t("banned_notice", lang, reason=ban_row["reason"], remaining=format_remaining(until_dt, lang)),
    )


class BanMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.update_types = ["message", "callback_query"]

    def pre_process(self, update, data):
        is_callback = isinstance(update, types.CallbackQuery)
        user_id = update.from_user.id
        if user_id == ADMIN_ID:
            return
        ban = db.get_active_ban(user_id)
        if ban:
            if is_callback:
                bot.answer_callback_query(update.id)
            # throttled so a banned person spamming can't make the bot spam back
            if _guard.cooldown_ok("bannotice", user_id, time.time(), 5):
                send_ban_notice(user_id, ban)
            return CancelUpdate()

    def post_process(self, update, data, exception=None):
        pass


class WorkingHoursMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.update_types = ["message", "callback_query"]

    def pre_process(self, update, data):
        is_callback = isinstance(update, types.CallbackQuery)
        chat_id = update.message.chat.id if is_callback else update.chat.id
        user_id = update.from_user.id

        if user_id == ADMIN_ID:
            return

        if hours_restriction_enabled() and not is_open_now():
            lang = get_lang(user_id)
            if is_callback:
                bot.answer_callback_query(update.id)
            bot.send_message(chat_id, t("bot_closed", lang, open_hour=OPEN_HOUR))
            return CancelUpdate()

    def post_process(self, update, data, exception=None):
        pass


def _auto_ban_flooder(user_id):
    until = datetime.utcnow() + timedelta(minutes=FLOOD_BAN_MINUTES)
    db.create_ban(user_id, "Automatic: sending too many requests (flood protection)", until.isoformat())
    ban = db.get_active_ban(user_id)
    try:
        if ban:
            send_ban_notice(user_id, ban)
    except Exception:
        pass
    who = (db.get_user(user_id) or {"username": None})["username"] or "-"
    try:
        bot.send_message(
            ADMIN_ID,
            f"🛡 Flood protection banned @{who} (id {user_id}) for {FLOOD_BAN_MINUTES} minutes.",
            reply_markup=kb.admin_unban_shortcut_kb(user_id),
        )
    except Exception:
        pass


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.update_types = ["message", "callback_query"]

    def pre_process(self, update, data):
        user_id = update.from_user.id
        if user_id == ADMIN_ID:
            return
        now = time.time()
        verdict = _guard.check(user_id, now)
        if verdict == "ok":
            return
        is_callback = isinstance(update, types.CallbackQuery)
        chat_id = update.message.chat.id if is_callback else update.chat.id
        if verdict == "flood":
            _auto_ban_flooder(user_id)
        elif _guard.cooldown_ok("slow", user_id, now, RATE_LIMIT_WINDOW):
            try:
                bot.send_message(chat_id, t("slow_down", get_lang(user_id)))
            except Exception:
                pass
        if is_callback:
            try:
                bot.answer_callback_query(update.id)
            except Exception:
                pass
        return CancelUpdate()

    def post_process(self, update, data, exception=None):
        pass


bot.setup_middleware(BanMiddleware())
bot.setup_middleware(RateLimitMiddleware())
bot.setup_middleware(WorkingHoursMiddleware())


# ---------------- /start ----------------
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    state.pop(user_id, None)  # /start always fully cancels any stuck flow
    db.upsert_user(user_id, message.from_user.username or "")
    user = db.get_user(user_id)
    if user and user["lang"]:
        bot.send_message(
            user_id, t("main_menu", user["lang"]), reply_markup=kb.main_menu_kb(user["lang"])
        )
    else:
        bot.send_message(user_id, t("choose_lang", "en"), reply_markup=kb.lang_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def set_lang(call):
    lang = call.data.split("_")[1]
    db.set_lang(call.from_user.id, lang)
    bot.edit_message_text(
        t("main_menu", lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.main_menu_kb(lang),
    )


@bot.callback_query_handler(func=lambda c: c.data == "menu_back")
def back_to_menu(call):
    lang = get_lang(call.from_user.id)
    state.pop(call.from_user.id, None)
    bot.edit_message_text(
        t("main_menu", lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.main_menu_kb(lang),
    )


# ---------------- Support (no button, no phone - just a tappable @mention) ----------------
@bot.callback_query_handler(func=lambda c: c.data == "menu_support")
def support(call):
    lang = get_lang(call.from_user.id)
    bot.edit_message_text(
        t("support_msg", lang, support_username=SUPPORT_USERNAME),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.support_kb(lang),
    )


# ---------------- FAQ ----------------
@bot.callback_query_handler(func=lambda c: c.data == "menu_faq")
def faq(call):
    lang = get_lang(call.from_user.id)
    bot.edit_message_text(
        FAQ_TEXT[lang],
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.back_kb(lang),
    )


# ---------------- How to connect ----------------
@bot.callback_query_handler(func=lambda c: c.data == "menu_howto")
def howto(call):
    lang = get_lang(call.from_user.id)
    bot.edit_message_text(
        t("choose_platform", lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.platforms_kb(lang),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("howto_"))
def howto_platform(call):
    lang = get_lang(call.from_user.id)
    platform_key = call.data.split("_", 1)[1]
    info = HOWTO_PLATFORMS[platform_key]
    chat_id = call.message.chat.id

    caption = info["update_note"][lang] + "\n\n" + info["text"][lang]

    if info["video_file_id"]:
        bot.send_video(
            chat_id,
            info["video_file_id"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb.platform_detail_kb(lang, platform_key),
        )
    else:
        bot.send_message(
            chat_id,
            caption,
            parse_mode="HTML",
            reply_markup=kb.platform_detail_kb(lang, platform_key),
        )


# ---------------- My subscriptions ----------------
@bot.callback_query_handler(func=lambda c: c.data == "menu_mysubs")
def mysubs(call):
    lang = get_lang(call.from_user.id)
    subs = db.get_active_subscriptions(call.from_user.id)
    if not subs:
        bot.edit_message_text(
            t("no_subs", lang), call.message.chat.id, call.message.message_id, reply_markup=kb.back_kb(lang)
        )
        return
    lines = [t("subs_header", lang)]
    for s in subs:
        end_date = s["end_date"].split("T")[0]
        line = t("sub_line", lang, name=s["sub_name"] or s["plan_name"], end_date=end_date)
        if s["remaining_gb"] is not None:
            line += t("sub_remaining", lang, gb=f"{s['remaining_gb']:g}")
        lines.append(line)
    bot.edit_message_text(
        "\n".join(lines),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.mysubs_kb(subs, lang),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("getlink_"))
def get_link(call):
    lang = get_lang(call.from_user.id)
    sub_id = int(call.data.split("_")[1])
    sub = db.get_subscription(sub_id)
    if not sub or sub["user_id"] != call.from_user.id:
        bot.answer_callback_query(call.id, "Not found.")
        return
    if not sub["config_text"]:
        bot.answer_callback_query(call.id, t("no_link_yet", lang))
        return
    bot.send_message(
        call.message.chat.id,
        f"<code>{html.escape(sub['config_text'])}</code>",
        parse_mode="HTML",
    )


# ---------------- Buy flow: category -> tier list -> plan detail -> name -> pay ----------------
@bot.callback_query_handler(func=lambda c: c.data == "menu_buy")
def buy(call):
    lang = get_lang(call.from_user.id)
    bot.edit_message_text(
        t("choose_category", lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.buy_category_kb(lang),
    )


@bot.callback_query_handler(func=lambda c: c.data == "buy_custom")
def buy_custom(call):
    lang = get_lang(call.from_user.id)
    bot.edit_message_text(
        t("custom_plan_msg", lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.custom_plan_kb(lang),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_duration_"))
def buy_duration(call):
    lang = get_lang(call.from_user.id)
    duration_days = int(call.data.split("_")[2])
    plans = db.get_active_plans(duration_days=duration_days)
    if not plans:
        bot.edit_message_text(
            t("no_plans", lang),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb.buy_category_kb(lang),
        )
        return
    bot.edit_message_text(
        t("choose_plan", lang),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.tier_kb(plans, lang),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("plan_"))
def choose_plan(call):
    lang = get_lang(call.from_user.id)
    plan_id = int(call.data.split("_")[1])
    plan = db.get_plan(plan_id)

    bot.edit_message_text(
        t(
            "plan_selected",
            lang,
            product_name=t("product_brand_name", lang),
            duration_label=duration_label(plan["duration_days"], lang),
            traffic=traffic_label(plan["traffic_gb"], lang),
            price=format_toman(plan["price"]),
        ),
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=kb.plan_selected_kb(lang, plan_id, plan["duration_days"]),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("finalize_"))
def finalize_purchase(call):
    lang = get_lang(call.from_user.id)
    plan_id = int(call.data.split("_")[1])
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    state[call.from_user.id] = {"step": "awaiting_sub_name", "plan_id": plan_id}
    bot.send_message(call.message.chat.id, t("ask_username", lang))


@bot.message_handler(
    func=lambda m: state.get(m.from_user.id, {}).get("step") == "awaiting_sub_name"
    and not _looks_like_command(m.text)
)
def receive_sub_name(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    name = (message.text or "").strip()

    if not USERNAME_RE.match(name):
        bot.send_message(message.chat.id, t("ask_username_invalid", lang))
        return

    plan_id = state[user_id]["plan_id"]
    state[user_id] = {"step": "awaiting_discount", "plan_id": plan_id, "sub_name": name}
    bot.send_message(message.chat.id, t("ask_discount", lang), reply_markup=kb.discount_prompt_kb(lang))


def _valid_line(lang, expires_at):
    return t(
        "invoice_valid_line", lang, minutes=ORDER_EXPIRY_MINUTES, until=_local_hhmm(expires_at)
    )


def send_order_invoice(chat_id, user_id, lang, plan_id, sub_name, discount_percent=None):
    plan = db.get_plan(plan_id)
    plan_price = plan["price"]

    discount_line = ""
    effective_price = plan_price
    if discount_percent:
        discount_amount = round(plan_price * discount_percent / 100)
        effective_price = plan_price - discount_amount
        discount_line = t("discount_line_fragment", lang, percent=discount_percent, amount=discount_amount)

    fee = round(effective_price * ORDER_FEE_PERCENT / 100)
    total = effective_price + fee
    expires_at = db._now() + timedelta(minutes=ORDER_EXPIRY_MINUTES)
    order_id = db.create_order(
        user_id, plan_id, total, chosen_username=sub_name, expires_at=expires_at.isoformat()
    )

    sent = bot.send_message(
        chat_id,
        t(
            "order_invoice",
            lang,
            product_name=t("product_brand_name", lang),
            duration_label=duration_label(plan["duration_days"], lang),
            traffic=traffic_label(plan["traffic_gb"], lang),
            sub_name=sub_name,
            plan_price=plan_price,
            discount_line=discount_line,
            fee_percent=ORDER_FEE_PERCENT,
            fee=fee,
            total=total,
            card_number=CARD_NUMBER,
            card_holder=CARD_HOLDER_NAME,
            valid_line=_valid_line(lang, expires_at),
        ),
        parse_mode="HTML",
        reply_markup=kb.order_payment_kb(lang, order_id),
    )
    db.set_invoice_message(order_id, chat_id, sent.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "discount_skip")
def discount_skip(call):
    user_id = call.from_user.id
    lang = get_lang(user_id)
    st = state.get(user_id, {})
    if st.get("step") != "awaiting_discount":
        return
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    plan_id, sub_name = st["plan_id"], st["sub_name"]
    state.pop(user_id, None)
    send_order_invoice(call.message.chat.id, user_id, lang, plan_id, sub_name)


@bot.message_handler(
    func=lambda m: state.get(m.from_user.id, {}).get("step") == "awaiting_discount"
    and not _looks_like_command(m.text)
)
def receive_discount_code(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    code = (message.text or "").strip()

    discount = db.get_discount(code)
    if not discount:
        bot.send_message(
            message.chat.id, t("discount_invalid", lang), reply_markup=kb.discount_prompt_kb(lang)
        )
        return

    st = state[user_id]
    plan_id, sub_name = st["plan_id"], st["sub_name"]
    state.pop(user_id, None)
    send_order_invoice(message.chat.id, user_id, lang, plan_id, sub_name, discount_percent=discount["percent"])


@bot.callback_query_handler(func=lambda c: c.data.startswith("order_paid_"))
def order_paid(call):
    lang = get_lang(call.from_user.id)
    order_id = int(call.data.split("_")[2])
    order = db.get_order(order_id)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    if not order or order["user_id"] != call.from_user.id:
        bot.answer_callback_query(call.id, "Not found.")
        return
    # an old invoice (even one from months ago) must never be payable
    if order["status"] == "awaiting_receipt" and db.order_is_expired(order):
        db.mark_order_expired(order_id)
        bot.send_message(call.message.chat.id, t("invoice_expired", lang))
        return
    if order["status"] != "awaiting_receipt":
        key = "invoice_expired" if order["status"] == "expired" else "order_not_payable"
        bot.send_message(call.message.chat.id, t(key, lang))
        return
    state[call.from_user.id] = {"step": "awaiting_receipt", "order_id": order_id}
    bot.send_message(call.message.chat.id, t("ask_send_receipt", lang))


@bot.message_handler(
    content_types=["photo"],
    func=lambda m: state.get(m.from_user.id, {}).get("step") == "awaiting_receipt",
)
def receive_receipt(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    order_id = state[user_id]["order_id"]
    order = db.get_order(order_id)
    if not order or order["status"] != "awaiting_receipt":
        state.pop(user_id, None)
        key = "invoice_expired" if order and order["status"] == "expired" else "order_not_payable"
        bot.send_message(message.chat.id, t(key, lang))
        return
    if db.order_is_expired(order):
        db.mark_order_expired(order_id)
        state.pop(user_id, None)
        bot.send_message(message.chat.id, t("invoice_expired", lang))
        return
    file_id = message.photo[-1].file_id
    db.set_order_receipt(order_id, file_id)
    state.pop(user_id, None)

    eta = db.get_avg_delivery_minutes()
    bot.send_message(message.chat.id, t("order_placed", lang))
    bot.send_message(
        message.chat.id,
        t("admin_working", lang) + "\n" + t("delivery_eta", lang, eta=eta or DELIVERY_ETA_DEFAULT),
    )
    notify_admin_new_order(order_id, file_id)


# ---------------- Invoice timer: expire unpaid invoices ----------------
def expire_stale_orders():
    for o in db.get_expired_unpaid_orders():
        if not db.mark_order_expired(o["id"]):
            continue
        uid = o["user_id"]
        st = state.get(uid, {})
        if st.get("step") == "awaiting_receipt" and st.get("order_id") == o["id"]:
            state.pop(uid, None)
        if o["invoice_chat_id"] and o["invoice_msg_id"]:
            try:
                bot.edit_message_reply_markup(o["invoice_chat_id"], o["invoice_msg_id"], reply_markup=None)
            except Exception:
                pass
        try:
            bot.send_message(
                uid, t("invoice_expired_notify", get_lang(uid), order_id=o["id"], minutes=ORDER_EXPIRY_MINUTES)
            )
        except Exception:
            pass


def _expiry_loop():
    while True:
        try:
            expire_stale_orders()
        except Exception as e:
            print("expiry loop error:", e)
        time.sleep(30)


# ---------------- My Orders / Share ----------------
@bot.callback_query_handler(func=lambda c: c.data == "menu_myorders")
def myorders(call):
    lang = get_lang(call.from_user.id)
    orders = db.get_user_orders(call.from_user.id, 10)
    if not orders:
        bot.edit_message_text(
            t("myorders_none", lang), call.message.chat.id, call.message.message_id,
            reply_markup=kb.back_kb(lang),
        )
        return
    parts = [t("myorders_header", lang)]
    for o in orders:
        if o["kind"] == "renewal":
            what = t("order_kind_renewal", lang, sub_name=o["sub_name"] or "-")
        elif o["duration_days"]:
            what = f"{traffic_label(o['traffic_gb'], lang)} — {duration_label(o['duration_days'], lang)}"
        else:
            what = "-"
        try:
            status = t(f"status_{o['status']}", lang)
        except KeyError:
            status = o["status"]
        parts.append(t("myorders_line", lang, id=o["id"], what=what, price=o["price"], status=status))
    bot.edit_message_text(
        "".join(parts), call.message.chat.id, call.message.message_id, reply_markup=kb.back_kb(lang)
    )


_bot_username_cache = {"v": None}


def _bot_username():
    if BOT_USERNAME:
        return BOT_USERNAME
    if not _bot_username_cache["v"]:
        try:
            _bot_username_cache["v"] = bot.get_me().username
        except Exception:
            return None
    return _bot_username_cache["v"]


@bot.callback_query_handler(func=lambda c: c.data == "menu_share")
def share(call):
    lang = get_lang(call.from_user.id)
    uname = _bot_username()
    if not uname:
        bot.edit_message_text(
            t("share_msg", lang), call.message.chat.id, call.message.message_id,
            reply_markup=kb.back_kb(lang),
        )
        return
    url = (
        "https://t.me/share/url?url=" + quote(f"https://t.me/{uname}")
        + "&text=" + quote(t("share_text", lang))
    )
    bot.edit_message_text(
        t("share_msg", lang), call.message.chat.id, call.message.message_id,
        reply_markup=kb.share_kb(lang, url),
    )


# ---------------- Rating ----------------
def send_rating_prompt(user_id, order_id):
    try:
        bot.send_message(
            user_id, t("rating_prompt", get_lang(user_id), order_id=order_id),
            reply_markup=kb.rating_kb(order_id),
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
def rate_order(call):
    lang = get_lang(call.from_user.id)
    try:
        _, oid, n = call.data.split("_")
        oid, n = int(oid), int(n)
    except ValueError:
        return
    if not 1 <= n <= 5:
        return
    if db.set_order_rating(oid, call.from_user.id, n):
        bot.edit_message_text(
            t("rating_thanks", lang, stars="⭐" * n), call.message.chat.id, call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, t("rating_already", lang))


# ---------------- Update subscription (renewal / extra data) ----------------
def renew_prices():
    per_month = int(db.get_setting("renew_per_month", RENEW_PRICE_PER_MONTH))
    per_gb = int(db.get_setting("renew_per_gb", RENEW_PRICE_PER_GB))
    return per_month, per_gb


@bot.callback_query_handler(func=lambda c: c.data.startswith("renew_"))
def renew_start(call):
    uid = call.from_user.id
    lang = get_lang(uid)
    sub_id = int(call.data.split("_")[1])
    sub = db.get_subscription(sub_id)
    if not sub or sub["user_id"] != uid:
        bot.answer_callback_query(call.id, "Not found.")
        return
    state[uid] = {"step": "renew_months", "sub_id": sub_id}
    bot.edit_message_text(
        t("renew_intro", lang, sub_name=sub["sub_name"] or sub["plan_name"],
          min_gb=RENEW_MIN_GB, max_gb=RENEW_MAX_GB),
        call.message.chat.id, call.message.message_id,
        reply_markup=kb.renew_months_kb(lang),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("rmonths_"))
def renew_months(call):
    uid = call.from_user.id
    lang = get_lang(uid)
    st = state.get(uid, {})
    if st.get("step") != "renew_months":
        bot.answer_callback_query(call.id)
        return
    st["months"] = int(call.data.split("_")[1])
    st["step"] = "renew_gb"
    bot.edit_message_text(
        t("renew_ask_gb", lang, min_gb=RENEW_MIN_GB, max_gb=RENEW_MAX_GB),
        call.message.chat.id, call.message.message_id,
        reply_markup=kb.renew_gb_kb(lang),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("rgb_"))
def renew_gb_button(call):
    uid = call.from_user.id
    if state.get(uid, {}).get("step") != "renew_gb":
        bot.answer_callback_query(call.id)
        return
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    _finish_renew_choice(call.message.chat.id, uid, int(call.data.split("_")[1]))


@bot.message_handler(
    func=lambda m: state.get(m.from_user.id, {}).get("step") == "renew_gb"
    and not _looks_like_command(m.text)
)
def renew_gb_text(message):
    uid = message.from_user.id
    lang = get_lang(uid)
    text = (message.text or "").strip()
    if not text.isdigit() or not (RENEW_MIN_GB <= int(text) <= RENEW_MAX_GB):
        bot.send_message(
            message.chat.id, t("renew_gb_invalid", lang, min_gb=RENEW_MIN_GB, max_gb=RENEW_MAX_GB)
        )
        return
    _finish_renew_choice(message.chat.id, uid, int(text))


def _finish_renew_choice(chat_id, user_id, gb):
    lang = get_lang(user_id)
    st = state.get(user_id, {})
    months, sub_id = st.get("months", 0), st.get("sub_id")
    sub = db.get_subscription(sub_id) if sub_id else None
    if not sub or sub["user_id"] != user_id:
        state.pop(user_id, None)
        return
    if months == 0 and gb == 0:
        state[user_id] = {"step": "renew_months", "sub_id": sub_id}
        bot.send_message(chat_id, t("renew_nothing", lang))
        bot.send_message(
            chat_id,
            t("renew_intro", lang, sub_name=sub["sub_name"] or sub["plan_name"],
              min_gb=RENEW_MIN_GB, max_gb=RENEW_MAX_GB),
            reply_markup=kb.renew_months_kb(lang),
        )
        return
    state.pop(user_id, None)

    per_month, per_gb = renew_prices()
    price = months * per_month + gb * per_gb
    fee = round(price * ORDER_FEE_PERCENT / 100)
    total = price + fee
    expires_at = db._now() + timedelta(minutes=ORDER_EXPIRY_MINUTES)
    order_id = db.create_renewal_order(user_id, sub_id, months * 30, gb, total, expires_at.isoformat())

    extra = ""
    if months:
        extra += t("renew_line_time", lang, value=duration_label(months * 30, lang))
    if gb:
        extra += t("renew_line_data", lang, value=traffic_label(gb, lang))
    sent = bot.send_message(
        chat_id,
        t(
            "renew_invoice", lang,
            sub_name=html.escape(sub["sub_name"] or sub["plan_name"]),
            orig_order=sub["order_id"],
            extra_lines=extra,
            plan_price=price, fee_percent=ORDER_FEE_PERCENT, fee=fee, total=total,
            card_number=CARD_NUMBER, card_holder=CARD_HOLDER_NAME,
            valid_line=_valid_line(lang, expires_at),
        ),
        parse_mode="HTML",
        reply_markup=kb.order_payment_kb(lang, order_id),
    )
    db.set_invoice_message(order_id, chat_id, sent.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("rapprove_"))
def admin_renewal_approve(call):
    if _not_admin(call):
        return
    order_id = int(call.data.split("_")[1])
    alarm_stop_flags[("order", order_id)] = True
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    new_end = db.apply_renewal(order_id)
    if not new_end:
        bot.send_message(ADMIN_ID, f"Renewal #{order_id} can't be approved (already handled, or the subscription is gone).")
        return
    card = db.get_order_card(order_id)
    user_id = card["user_id"]
    lang = get_lang(user_id)
    lines = ""
    if card["extra_days"]:
        lines += t("renew_line_time", lang, value=duration_label(card["extra_days"], lang))
    if card["extra_gb"]:
        lines += t("renew_line_data", lang, value=traffic_label(card["extra_gb"], lang))
    try:
        bot.send_message(
            user_id,
            t("renew_done", lang, sub_name=html.escape(card.get("sub_name") or "-"), lines=lines,
              end_date=new_end.strftime("%Y-%m-%d"), jalali_date=format_jalali_date(new_end),
              order_id=order_id),
            parse_mode="HTML",
        )
        send_rating_prompt(user_id, order_id)
    except Exception:
        pass
    bot.send_message(
        ADMIN_ID, f"✅ Renewal #{order_id} approved — new expiry {new_end.strftime('%Y-%m-%d')}. Customer notified."
    )


# ---------------- Generic repeating alarm ----------------
def run_alarm(key, send_fn):
    alarm_stop_flags[key] = False

    def loop():
        pings = 0
        while not alarm_stop_flags.get(key) and pings < ALARM_MAX_PINGS:
            send_fn()
            pings += 1
            time.sleep(ALARM_INTERVAL_SECONDS)

    threading.Thread(target=loop, daemon=True).start()


def _flag_line(user):
    if user["flagged"]:
        return f"⚠️ FLAGGED user: {user['flag_reason'] or 'see /user'}\n"
    return ""


def notify_admin_new_order(order_id, receipt_file_id, repeat=True):
    order = db.get_order(order_id)
    user = db.get_user(order["user_id"])
    if order["kind"] == "renewal":
        card = db.get_order_card(order_id)
        days = order["extra_days"] or 0
        gb = order["extra_gb"] or 0
        text = t(
            "admin_new_renewal",
            "en",
            order_id=order_id,
            orig_order=card.get("original_order_id") or "?",
            username=user["username"] or "-",
            user_id=user["user_id"],
            sub_name=card.get("sub_name") or "-",
            time_value=f"{days // 30} month(s) ({days} days)" if days else "none",
            gb_value=f"{gb} GB" if gb else "none",
            price=order["price"],
            flag_line=_flag_line(user),
        )
        markup = kb.admin_renewal_kb(order_id)
    else:
        plan = db.get_plan(order["plan_id"])
        plan_desc = f"{traffic_label(plan['traffic_gb'], 'en')} — {duration_label(plan['duration_days'], 'en')}"
        text = t(
            "admin_new_order",
            "en",
            order_id=order_id,
            username=user["username"] or "-",
            user_id=user["user_id"],
            plan_name=plan_desc,
            sub_name=order["chosen_username"] or "-",
            price=order["price"],
            flag_line=_flag_line(user),
        )
        markup = kb.admin_order_kb(order_id)

    def send():
        bot.send_photo(ADMIN_ID, receipt_file_id, caption=text, reply_markup=markup)

    if repeat:
        run_alarm(("order", order_id), send)
    else:
        # one-time resend (e.g. from /pending) - don't stack another
        # repeating alarm loop on top of one that may already be running
        send()


@bot.callback_query_handler(func=lambda c: c.data.startswith("seen_"))
def admin_seen(call):
    if _not_admin(call):
        return
    order_id = int(call.data.split("_")[1])
    alarm_stop_flags[("order", order_id)] = True
    bot.answer_callback_query(call.id, "Marked as seen, alarm stopped.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("deliver_"))
def admin_deliver(call):
    if _not_admin(call):
        return
    order_id = int(call.data.split("_")[1])
    alarm_stop_flags[("order", order_id)] = True
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    admin_state[ADMIN_ID] = {"awaiting_config_for": order_id}
    bot.send_message(ADMIN_ID, t("admin_ask_config", "en", order_id=order_id))


@bot.callback_query_handler(func=lambda c: c.data.startswith("decline_"))
def admin_decline(call):
    if _not_admin(call):
        return
    order_id = int(call.data.split("_")[1])
    alarm_stop_flags[("order", order_id)] = True
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    admin_state[ADMIN_ID] = {"awaiting_decline_reason_for": order_id}
    bot.send_message(ADMIN_ID, t("admin_ask_decline_reason", "en", order_id=order_id))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("awaiting_decline_reason_for") is not None
    and not _looks_like_command(m.text)
)
def admin_receive_decline_reason(message):
    order_id = admin_state[ADMIN_ID]["awaiting_decline_reason_for"]
    admin_state[ADMIN_ID] = {}
    reason = (message.text or "").strip()
    if not reason:
        bot.reply_to(message, "Please send a non-empty reason.")
        admin_state[ADMIN_ID] = {"awaiting_decline_reason_for": order_id}
        return

    order = db.get_order(order_id)
    if not order or order["status"] != "awaiting_admin":
        bot.send_message(ADMIN_ID, f"Order #{order_id} is no longer pending — nothing to decline.")
        return

    db.decline_order(order_id)
    user_id = order["user_id"]
    lang = get_lang(user_id)
    try:
        bot.send_message(user_id, t("order_declined", lang, reason=reason))
    except Exception:
        pass  # user may have blocked the bot
    bot.send_message(ADMIN_ID, t("admin_declined", "en", order_id=order_id, reason=reason))
    _maybe_flag_user(user_id)


def _maybe_flag_user(user_id):
    """Repeated declined receipts -> flag the user and tell the admin."""
    n = db.count_recent_declines(user_id, FLAG_WINDOW_DAYS)
    user = db.get_user(user_id)
    if n >= FLAG_DECLINE_THRESHOLD and user and not user["flagged"]:
        reason = f"{n} declined receipts in the last {FLAG_WINDOW_DAYS} days"
        db.set_user_flag(user_id, reason)
        bot.send_message(
            ADMIN_ID,
            f"⚠️ Flagged @{user['username'] or '-'} (id {user_id}): {reason}.\n"
            f"Their future orders will carry a warning.",
            reply_markup=kb.admin_flag_alert_kb(user_id),
        )


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("awaiting_config_for") is not None
    and not _looks_like_command(m.text)
)
def admin_send_config(message):
    order_id = admin_state[ADMIN_ID]["awaiting_config_for"]
    admin_state[ADMIN_ID] = {}
    order = db.get_order(order_id)
    if not order or order["status"] != "awaiting_admin" or order["kind"] == "renewal":
        bot.send_message(ADMIN_ID, f"Order #{order_id} isn't waiting for delivery — nothing was sent.")
        return
    plan = db.get_plan(order["plan_id"])
    user_id = order["user_id"]
    lang = get_lang(user_id)
    plan_desc = f"{traffic_label(plan['traffic_gb'], lang)} — {duration_label(plan['duration_days'], lang)}"
    sub_name = order["chosen_username"] or "-"

    end_date = db.create_subscription(
        user_id, order_id, plan_desc, sub_name, message.text, plan["duration_days"],
        total_gb=plan["traffic_gb"],
    )
    db.mark_order_delivered(order_id)
    state.pop(user_id, None)

    bot.send_message(
        user_id,
        t(
            "subscription_ready",
            lang,
            sub_name=sub_name,
            plan_name=plan_desc,
            end_date=end_date.strftime("%Y-%m-%d"),
            jalali_date=format_jalali_date(end_date),
            config=f"<code>{html.escape(message.text)}</code>",
        ),
        parse_mode="HTML",
    )
    bot.send_message(user_id, t("main_menu", lang), reply_markup=kb.main_menu_kb(lang))
    bot.send_message(ADMIN_ID, t("admin_delivered", "en", order_id=order_id))
    send_rating_prompt(user_id, order_id)


# ---------------- Admin: look up a previously-delivered config ----------------
@bot.message_handler(commands=["getconfig"])
def admin_get_config(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "Usage: /getconfig <order_id>")
        return
    order_id = int(parts[1].strip())
    sub = db.get_subscription_by_order(order_id)
    if not sub:
        bot.reply_to(message, f"No subscription found for order #{order_id}.")
        return
    bot.send_message(
        message.chat.id,
        f"Order #{order_id} — {sub['plan_name']} ({sub['sub_name'] or '-'})\n"
        f"Expires: {sub['end_date'].split('T')[0]}\n\n"
        f"<code>{html.escape(sub['config_text'])}</code>",
        parse_mode="HTML",
    )


# ---------------- Admin: see everything still waiting on you ----------------
def _do_pending(chat_id):
    orders = db.get_pending_orders()
    if not orders:
        bot.send_message(chat_id, t("admin_pending_none", "en"))
        return
    lines = [t("admin_pending_header", "en")]
    for o in orders:
        if o["kind"] == "renewal":
            plan_desc = f"🔄 renewal +{(o['extra_days'] or 0) // 30}mo +{o['extra_gb'] or 0}GB"
        else:
            plan_desc = f"{traffic_label(o['traffic_gb'], 'en')} — {duration_label(o['duration_days'], 'en')}"
        lines.append(
            t(
                "admin_pending_line",
                "en",
                order_id=o["order_id"],
                username=o["username"] or "-",
                user_id=o["user_id"],
                plan_name=plan_desc,
                price=o["price"],
                created_at=o["created_at"].split("T")[0],
            )
        )
    bot.send_message(chat_id, "".join(lines))
    # Also resend each one as a full actionable card (photo + buttons) - if the
    # original alert's buttons got lost, scrolled away, or the repeating alarm
    # already hit its time cap, this is the way to act on it right now.
    for o in orders:
        if o["receipt_file_id"]:
            notify_admin_new_order(o["order_id"], o["receipt_file_id"], repeat=False)


@bot.message_handler(commands=["pending"])
def admin_pending(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    _do_pending(ADMIN_ID)


# ---------------- Admin: quick business stats ----------------
def _do_stats(chat_id):
    s = db.get_stats()
    rating_text = (
        f"{s['avg_rating']} / 5 ({s['rating_count']} ratings)" if s["avg_rating"] is not None else "no ratings yet"
    )
    bot.send_message(
        chat_id,
        t(
            "admin_stats",
            "en",
            users=s["users"],
            total_orders=s["total_orders"],
            delivered_orders=s["delivered_orders"],
            revenue=s["revenue"],
            pending_orders=s["pending_orders"],
            active_subscriptions=s["active_subscriptions"],
            refunded_total=s["refunded_total"],
            rating_text=rating_text,
        ),
    )


@bot.message_handler(commands=["stats"])
def admin_stats(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    _do_stats(ADMIN_ID)


# ---------------- Admin: broadcast a message to every user ----------------
@bot.message_handler(commands=["broadcast"])
def admin_broadcast(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        bot.reply_to(message, t("admin_broadcast_usage", "en"))
        return
    text = parts[1].strip()
    sent, failed = 0, 0
    for user_id in db.get_all_user_ids():
        try:
            bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1
    bot.reply_to(message, t("admin_broadcast_done", "en", sent=sent, failed=failed))


# ---------------- Admin: toggle the working-hours restriction ----------------
@bot.message_handler(commands=["togglehours"])
def admin_toggle_hours(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    now_enabled = not hours_restriction_enabled()
    db.set_setting("hours_enabled", "1" if now_enabled else "0")
    if now_enabled:
        bot.reply_to(
            message,
            f"✅ Working hours restriction is ON — bot only replies to customers "
            f"{OPEN_HOUR}:00–23:59 ({TIMEZONE}).",
        )
    else:
        bot.reply_to(message, "✅ Working hours restriction is OFF — bot now replies to customers 24/7.")


# ---------------- Admin: ban / unban ----------------
def _resolve_target(text):
    """Accepts a numeric user id or an @username, returns the user row or None."""
    text = text.strip()
    if text.startswith("@"):
        return db.get_user_by_username(text[1:])
    if text.isdigit():
        return db.get_user(int(text))
    return None


@bot.message_handler(commands=["ban"])
def admin_ban_start(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {"ban_step": "awaiting_target"}
    bot.send_message(ADMIN_ID, t("admin_ban_ask_target", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("ban_step") == "awaiting_target"
    and not _looks_like_command(m.text)
)
def admin_ban_receive_target(message):
    target = _resolve_target(message.text)
    if not target:
        bot.reply_to(message, t("admin_ban_target_not_found", "en"))
        admin_state[ADMIN_ID] = {}
        return
    count = db.get_ban_count(target["user_id"])
    bot.send_message(ADMIN_ID, t("admin_ban_prior_record", "en", count=count))
    admin_state[ADMIN_ID] = {"ban_step": "awaiting_duration", "target_user_id": target["user_id"]}
    bot.send_message(ADMIN_ID, t("admin_ban_ask_duration", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("ban_step") == "awaiting_duration"
    and not _looks_like_command(m.text)
)
def admin_ban_receive_duration(message):
    hours = parse_ban_duration(message.text)
    if hours is None or hours <= 0:
        bot.reply_to(message, t("admin_ban_invalid_duration", "en"))
        return
    admin_state[ADMIN_ID]["duration_hours"] = hours
    admin_state[ADMIN_ID]["ban_step"] = "awaiting_reason"
    bot.send_message(ADMIN_ID, t("admin_ban_ask_reason", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("ban_step") == "awaiting_reason"
    and not _looks_like_command(m.text)
)
def admin_ban_receive_reason(message):
    st = admin_state[ADMIN_ID]
    admin_state[ADMIN_ID] = {}
    target_user_id = st["target_user_id"]
    hours = st["duration_hours"]
    reason = message.text.strip()

    until_dt = datetime.utcnow() + timedelta(hours=hours)
    db.create_ban(target_user_id, reason, until_dt.isoformat())

    duration_str = f"{hours:g}h"
    bot.send_message(
        ADMIN_ID,
        t(
            "admin_ban_done",
            "en",
            user_id=target_user_id,
            duration=duration_str,
            reason=reason,
            until=until_dt.strftime("%Y-%m-%d %H:%M"),
        ),
        reply_markup=kb.admin_unban_shortcut_kb(target_user_id),
    )

    ban_row = db.get_active_ban(target_user_id)
    if ban_row:
        try:
            send_ban_notice(target_user_id, ban_row)
        except Exception:
            pass  # they may have blocked the bot - the admin message above still went through


@bot.message_handler(commands=["unban"])
def admin_unban_start(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {"unban_step": "awaiting_target"}
    bot.send_message(ADMIN_ID, t("admin_unban_ask_target", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("unban_step") == "awaiting_target"
    and not _looks_like_command(m.text)
)
def admin_unban_receive_target(message):
    admin_state[ADMIN_ID] = {}
    target = _resolve_target(message.text)
    if not target:
        bot.reply_to(message, t("admin_ban_target_not_found", "en"))
        return
    _do_unban(target["user_id"], message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("unban_"))
def admin_unban_button(call):
    if _not_admin(call):
        return
    target_user_id = int(call.data.split("_")[1])
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    _do_unban(target_user_id, call.message.chat.id)


def _do_unban(target_user_id, admin_chat_id):
    if not db.unban_user(target_user_id):
        bot.send_message(admin_chat_id, t("admin_unban_not_banned", "en"))
        return
    bot.send_message(admin_chat_id, t("admin_unban_done", "en", user_id=target_user_id))
    lang = get_lang(target_user_id)
    try:
        bot.send_message(target_user_id, t("unbanned_notice", lang))
    except Exception:
        pass


# ---------------- Admin: message a specific user ----------------
def _deliver_admin_message(target, text, reply_to_msg):
    lang = get_lang(target["user_id"])
    try:
        bot.send_message(target["user_id"], t("admin_message_to_user", lang, text=text))
        bot.reply_to(
            reply_to_msg,
            t("admin_msg_sent", "en", user_id=target["user_id"], username=target["username"] or "-"),
        )
    except Exception:
        bot.reply_to(reply_to_msg, t("admin_msg_failed", "en", user_id=target["user_id"]))


@bot.message_handler(commands=["message"])
def admin_message_start(message):
    if _not_admin(message):
        return
    # one-liner form: /message <id|@username> <text>
    parts = message.text.split(maxsplit=2)
    if len(parts) == 3 and parts[2].strip():
        admin_state[ADMIN_ID] = {}
        target = _resolve_target(parts[1])
        if not target:
            bot.reply_to(message, t("admin_msg_target_not_found", "en"))
            return
        _deliver_admin_message(target, parts[2].strip(), message)
        return
    admin_state[ADMIN_ID] = {"msg_step": "awaiting_target"}
    bot.send_message(ADMIN_ID, t("admin_msg_ask_target", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("msg_step") == "awaiting_target"
    and not _looks_like_command(m.text)
)
def admin_message_receive_target(message):
    target = _resolve_target(message.text or "")
    if not target:
        bot.reply_to(message, t("admin_msg_target_not_found", "en"))
        admin_state[ADMIN_ID] = {}
        return
    admin_state[ADMIN_ID] = {"msg_step": "awaiting_text", "target_user_id": target["user_id"]}
    bot.send_message(ADMIN_ID, t("admin_msg_ask_text", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("msg_step") == "awaiting_text"
    and not _looks_like_command(m.text)
)
def admin_message_receive_text(message):
    text = (message.text or "").strip()
    if not text:
        bot.reply_to(message, t("admin_msg_empty", "en"))
        return
    target = db.get_user(admin_state[ADMIN_ID]["target_user_id"])
    admin_state[ADMIN_ID] = {}
    _deliver_admin_message(target, text, message)


# ---------------- Admin: discount codes ----------------
@bot.message_handler(commands=["adddiscount"])
def admin_adddiscount_start(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {"discount_step": "awaiting_code"}
    bot.send_message(ADMIN_ID, t("admin_discount_ask_code", "en"))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("discount_step") == "awaiting_code"
    and not _looks_like_command(m.text)
)
def admin_adddiscount_receive_code(message):
    code = (message.text or "").strip().upper()
    admin_state[ADMIN_ID] = {"discount_step": "awaiting_percent", "code": code}
    bot.send_message(ADMIN_ID, t("admin_discount_ask_percent", "en", code=code))


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("discount_step") == "awaiting_percent"
    and not _looks_like_command(m.text)
)
def admin_adddiscount_receive_percent(message):
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 100):
        bot.reply_to(message, t("admin_discount_invalid_percent", "en"))
        return
    code = admin_state[ADMIN_ID]["code"]
    percent = int(text)
    admin_state[ADMIN_ID] = {}
    db.create_discount(code, percent)
    bot.reply_to(message, t("admin_discount_created", "en", code=code, percent=percent))


@bot.message_handler(commands=["discounts"])
def admin_list_discounts(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    active = db.get_active_discounts()
    if not active:
        bot.reply_to(message, t("admin_discounts_list_empty", "en"))
        return
    lines = [t("admin_discounts_list_header", "en")]
    for d in active:
        lines.append(t("admin_discounts_list_line", "en", code=d["code"], percent=d["percent"]))
    bot.reply_to(message, "".join(lines))


@bot.message_handler(commands=["removediscount"])
def admin_remove_discount(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        bot.reply_to(message, t("admin_removediscount_usage", "en"))
        return
    code = parts[1].strip().upper()
    if db.deactivate_discount(code):
        bot.reply_to(message, t("admin_discount_removed", "en", code=code))
    else:
        bot.reply_to(message, t("admin_discount_not_found", "en", code=code))


# ---------------- Admin: manual plan update (final prices, no markup) ----------------
@bot.message_handler(commands=["updateplans"])
def updateplans_start(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {"awaiting_plans_text": True}
    bot.send_message(
        ADMIN_ID,
        "Paste your plans now, one per line, format: months - GB - final_price\n"
        "Example:\n1 - 20 - 98000\n3 - 150 - 564000\n\n"
        "These are the EXACT final prices before the gateway fee - no markup is added.",
    )


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("awaiting_plans_text")
    and not _looks_like_command(m.text)
)
def updateplans_receive(message):
    admin_state[ADMIN_ID] = {}
    plans = parse_admin_plan_lines(message.text)
    if not plans:
        bot.reply_to(
            message,
            "Couldn't parse any plans from that text. Each line must look like: "
            "1 - 20 - 98000 (months - GB - price).",
        )
        return

    seen_keys = set()
    lines = ["✅ Synced plans:"]
    for p in plans:
        db.upsert_plan(p["duration_days"], p["traffic_gb"], p["price"])
        seen_keys.add((p["duration_days"], p["traffic_gb"]))
        lines.append(f"• {duration_label(p['duration_days'], 'en')} — {p['traffic_gb']}GB — {p['price']}")
    db.deactivate_missing_plans(seen_keys)
    bot.reply_to(message, "\n".join(lines))


# =====================================================================
#                      ADMIN TOOLS (newer features)
# =====================================================================
def _fmt_dt(iso):
    return iso.replace("T", " ")[:16] if iso else "-"


def _order_card_text(c):
    if c["kind"] == "renewal":
        orig = c.get("original_order_id")
        ref = f"order #{orig}" if orig else f"manual sub #{c['renew_sub_id']}"
        what = (
            f"🔄 Update of '{c.get('sub_name') or '-'}' ({ref}): "
            f"+{(c['extra_days'] or 0) // 30} month(s), +{c['extra_gb'] or 0} GB"
        )
    elif c.get("duration_days"):
        what = (
            f"{traffic_label(c['traffic_gb'], 'en')} — {duration_label(c['duration_days'], 'en')} "
            f"(name: {c['chosen_username'] or '-'})"
        )
    else:
        what = "-"
    refunded = c["refunded_amount"] or 0
    lines = [
        f"🧾 Order #{c['id']} — {c['kind']}",
        f"Status: {c['status']}",
        f"User: @{c['username'] or '-'} (id {c['user_id']})" + ("  ⚠️ FLAGGED" if c.get("flagged") else ""),
        f"What: {what}",
        f"Price: {c['price']} Toman" + (f"  (refunded {refunded})" if refunded else ""),
        f"Created: {_fmt_dt(c['created_at'])} UTC",
        f"Invoice valid until: {_fmt_dt(c['expires_at'])} UTC",
        f"Receipt sent: {_fmt_dt(c['receipt_at'])}",
        f"Delivered: {_fmt_dt(c['delivered_at'])}",
        f"Rating: {'⭐' * c['rating'] if c['rating'] else '-'}",
    ]
    for r in c["refunds"]:
        lines.append(f"💸 Refund {r['amount']} on {_fmt_dt(r['created_at'])} — {r['reason']}")
    return "\n".join(lines)


def _send_order_card(chat_id, order_id):
    c = db.get_order_card(order_id)
    if not c:
        bot.send_message(chat_id, f"Order #{order_id} not found.")
        return
    text, markup = _order_card_text(c), kb.admin_order_card_kb(c)
    if c["receipt_file_id"]:
        bot.send_photo(chat_id, c["receipt_file_id"], caption=text, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)


def _user_profile_text(p):
    ban = p["active_ban"]
    lines = [
        f"👤 @{p['username'] or '-'} (id {p['user_id']})",
        f"Language: {p['lang'] or '-'} · Joined: {_fmt_dt(p['created_at'])}",
        f"Orders: {p['orders_total']} total · {p['orders_delivered']} delivered · "
        f"{p['orders_declined']} declined · {p['orders_expired']} expired · {p['orders_refunded']} refunded",
        f"Spent (net of refunds): {p['spent']} Toman",
        f"Last order: {_fmt_dt(p['last_order_at'])}",
        f"Rating given (avg): {round(p['avg_rating'], 1) if p['avg_rating'] else '-'}",
        f"Times banned: {p['ban_count']}" + (f" — BANNED until {_fmt_dt(ban['until'])} UTC ({ban['reason']})" if ban else ""),
    ]
    if p["flagged"]:
        lines.append(f"⚠️ FLAGGED: {p['flag_reason']}")
    if p["subs"]:
        lines.append("\n📦 Active subscriptions:")
        for sub in p["subs"]:
            cap = ""
            if sub["remaining_gb"] is not None:
                cap = f" · {sub['remaining_gb']:g}" + (f"/{sub['total_gb']:g}" if sub["total_gb"] is not None else "") + " GB left"
            src = "manual" if sub["manual"] else f"order #{sub['order_id']}"
            lines.append(f"  #{sub['id']} {sub['sub_name'] or '-'} — ends {sub['end_date'][:10]}{cap} ({src})")
    return "\n".join(lines)


def _send_user_profile(chat_id, user_id):
    p = db.get_user_profile(user_id)
    if not p:
        bot.send_message(chat_id, "I don't know that user.")
        return
    bot.send_message(
        chat_id,
        _user_profile_text(p),
        reply_markup=kb.admin_user_kb(user_id, bool(p["active_ban"]), bool(p["flagged"]), p["subs"]),
    )


@bot.message_handler(commands=["order"])
def admin_order_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].strip().lstrip("#").isdigit():
        _send_order_card(ADMIN_ID, int(parts[1].strip().lstrip("#")))
        return
    admin_state[ADMIN_ID] = {"lookup": "order"}
    bot.send_message(ADMIN_ID, "Send the order number:")


@bot.message_handler(commands=["user"])
def admin_user_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        target = _resolve_target(parts[1])
        if target:
            _send_user_profile(ADMIN_ID, target["user_id"])
        else:
            bot.send_message(ADMIN_ID, "I don't recognize that user (they must have started the bot).")
        return
    admin_state[ADMIN_ID] = {"lookup": "user"}
    bot.send_message(ADMIN_ID, "Send the user's numeric ID or @username:")


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("lookup")
    and not _looks_like_command(m.text)
)
def admin_lookup_receive(message):
    kind = admin_state[ADMIN_ID]["lookup"]
    admin_state[ADMIN_ID] = {}
    text = (message.text or "").strip()
    if kind == "order":
        if text.lstrip("#").isdigit():
            _send_order_card(ADMIN_ID, int(text.lstrip("#")))
        else:
            bot.send_message(ADMIN_ID, "That isn't an order number.")
    else:
        target = _resolve_target(text)
        if target:
            _send_user_profile(ADMIN_ID, target["user_id"])
        else:
            bot.send_message(ADMIN_ID, "I don't recognize that user (they must have started the bot).")


# ---------------- Admin: refunds ----------------
def _refund_ask_amount(order_id):
    c = db.get_order_card(order_id)
    if not c:
        bot.send_message(ADMIN_ID, f"Order #{order_id} not found.")
        admin_state[ADMIN_ID] = {}
        return
    if c["status"] not in ("delivered", "refunded"):
        bot.send_message(ADMIN_ID, f"Order #{order_id} is '{c['status']}' — only delivered orders can be refunded.")
        admin_state[ADMIN_ID] = {}
        return
    remaining = c["price"] - (c["refunded_amount"] or 0)
    if remaining <= 0:
        bot.send_message(ADMIN_ID, f"Order #{order_id} is already fully refunded.")
        admin_state[ADMIN_ID] = {}
        return
    admin_state[ADMIN_ID] = {"refund_step": "amount", "order_id": order_id, "remaining": remaining}
    bot.send_message(
        ADMIN_ID,
        f"Order #{order_id}: paid {c['price']}, already refunded {c['refunded_amount'] or 0}.\n"
        f"How much are you refunding? Send an amount (max {remaining}) or 'full'.",
    )


def _finalize_refund(order_id, amount, reason):
    ok, res = db.create_refund(order_id, amount, reason)
    if not ok:
        bot.send_message(ADMIN_ID, f"❌ {res}")
        return
    lang = get_lang(res["user_id"])
    try:
        bot.send_message(
            res["user_id"], t("refund_notice", lang, amount=amount, order_id=order_id, reason=reason)
        )
        notified = "Customer notified."
    except Exception:
        notified = "Couldn't notify the customer."
    bot.send_message(
        ADMIN_ID,
        f"✅ Recorded a refund of {amount} on order #{order_id} (total refunded {res['total_refunded']}, "
        f"{res['remaining']} left, status: {res['status']}). {notified}\n"
        f"Note: this only records it — send the money yourself.",
    )


@bot.message_handler(commands=["refund"])
def admin_refund_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    parts = message.text.split(maxsplit=3)  # /refund <id> <amount|full> <reason>
    if len(parts) == 4 and parts[1].lstrip("#").isdigit():
        oid = int(parts[1].lstrip("#"))
        c = db.get_order_card(oid)
        if not c:
            bot.send_message(ADMIN_ID, f"Order #{oid} not found.")
            return
        remaining = c["price"] - (c["refunded_amount"] or 0)
        amt = remaining if parts[2].lower() == "full" else (int(parts[2]) if parts[2].isdigit() else 0)
        _finalize_refund(oid, amt, parts[3].strip())
        return
    admin_state[ADMIN_ID] = {"refund_step": "order"}
    bot.send_message(ADMIN_ID, "Which order number do you want to refund?")


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("refund_step")
    and not _looks_like_command(m.text)
)
def admin_refund_flow(message):
    st = admin_state[ADMIN_ID]
    step = st["refund_step"]
    text = (message.text or "").strip()
    if step == "order":
        if not text.lstrip("#").isdigit():
            bot.send_message(ADMIN_ID, "Send the order number (digits only):")
            return
        _refund_ask_amount(int(text.lstrip("#")))
    elif step == "amount":
        amount = st["remaining"] if text.lower() == "full" else (int(text) if text.isdigit() else 0)
        if not 1 <= amount <= st["remaining"]:
            bot.send_message(ADMIN_ID, f"Send a number between 1 and {st['remaining']}, or 'full':")
            return
        st.update({"refund_step": "reason", "amount": amount})
        bot.send_message(ADMIN_ID, "What's the reason? (the customer will see it)")
    elif step == "reason":
        order_id, amount = st["order_id"], st["amount"]
        admin_state[ADMIN_ID] = {}
        _finalize_refund(order_id, amount, text or "-")


# ---------------- Admin: backups ----------------
def _send_backup(chat_id, automatic=False):
    path = backup_mod.make_backup_zip(DB_PATH)
    try:
        with open(path, "rb") as f:
            bot.send_document(
                chat_id,
                f,
                caption=("🗄 Automatic daily backup" if automatic else "🗄 Database backup")
                + "\nSubscription configs inside are encrypted — also keep secret.key safe "
                "(it is NOT included here); without it they can't be decrypted.",
            )
    finally:
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


@bot.message_handler(commands=["backup"])
def admin_backup_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    try:
        _send_backup(ADMIN_ID)
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Backup failed: {e}")


def _backup_loop():
    while True:
        wait = 60
        try:
            now_local = datetime.now(ZoneInfo(TIMEZONE))
            if backup_mod.backup_due(now_local, BACKUP_HOUR, db.get_setting("last_backup_date")):
                _send_backup(ADMIN_ID, automatic=True)
                db.set_setting("last_backup_date", now_local.strftime("%Y-%m-%d"))
        except Exception as e:
            print("backup loop error:", e)
            wait = 600
        time.sleep(wait)


# ---------------- Admin: dashboard link ----------------
def _send_dashboard_link(chat_id):
    if not DASHBOARD_ENABLED:
        bot.send_message(chat_id, "The dashboard is turned off (DASHBOARD_ENABLED=0 in .env).")
        return
    token = dashboard.issue_login_token()
    base = DASHBOARD_PUBLIC_URL or f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}"
    url = f"{base}/login?t={token}"
    if DASHBOARD_PUBLIC_URL.startswith("https://"):
        markup = types.InlineKeyboardMarkup()
        try:
            markup.add(types.InlineKeyboardButton("🖥 Open dashboard", web_app=types.WebAppInfo(url=f"{base}/webapp")))
        except Exception:
            pass
        markup.add(types.InlineKeyboardButton("🔗 Open in browser (one-time link)", url=url))
        bot.send_message(chat_id, "🖥 Admin dashboard — the link works once and expires in 10 minutes.", reply_markup=markup)
    else:
        bot.send_message(
            chat_id,
            "🖥 Admin dashboard (one-time link, valid 10 minutes):\n" + url +
            "\n\nIt only works on the machine/network the bot runs on. To open it from your phone, "
            "set DASHBOARD_PUBLIC_URL to an https address (see README).",
        )


@bot.message_handler(commands=["dashboard"])
def admin_dashboard_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    _send_dashboard_link(ADMIN_ID)


# ---------------- Admin: renewal prices ----------------
def _do_renewprices(chat_id):
    pm, pg = renew_prices()
    bot.send_message(
        chat_id,
        f"💲 Subscription-update prices (before the {ORDER_FEE_PERCENT}% fee):\n"
        f"• per month: {pm} Toman\n• per GB: {pg} Toman\n"
        f"Example: 1 month + 100 GB = {pm + 100 * pg} Toman\n\n"
        f"Change them with: /setrenew <per_month> <per_gb>",
    )


@bot.message_handler(commands=["setrenew"])
def admin_setrenew(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    parts = message.text.split()
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        db.set_setting("renew_per_month", parts[1])
        db.set_setting("renew_per_gb", parts[2])
        bot.send_message(ADMIN_ID, "✅ Updated.")
    _do_renewprices(ADMIN_ID)


# ---------------- Admin: add a subscription by hand ----------------
SUBNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")


def _parse_end_date(text):
    """'30' -> 30 days from now; '2026-12-31' -> that date. None if invalid."""
    text = text.strip()
    if text.isdigit() and 1 <= int(text) <= 3650:
        return db._now() + timedelta(days=int(text))
    try:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(hour=23, minute=59)
    except ValueError:
        return None
    return dt if dt > db._now() else None


def _parse_gb(text):
    """Returns (ok, value). '-' means unknown/unlimited -> (True, None)."""
    text = text.strip().replace(",", ".")
    if text == "-":
        return True, None
    try:
        v = float(text)
    except ValueError:
        return False, None
    return (v >= 0), (v if v >= 0 else None)


def _target_or_placeholder(text):
    """id/@username -> (user_row, created_placeholder). A numeric id nobody
    has seen yet gets a placeholder row (they must open the bot to be reachable)."""
    row = _resolve_target(text)
    if row:
        return row, False
    text = text.strip()
    if text.isdigit():
        db.upsert_user(int(text), None)
        return db.get_user(int(text)), True
    return None, False


def _finish_addsub(user_row, created, name, end_dt, gb, config):
    uid = user_row["user_id"]
    sub_id = db.create_manual_subscription(uid, name, config, end_dt, gb)
    lang = get_lang(uid)
    notified = True
    try:
        bot.send_message(
            uid,
            t(
                "subscription_ready", lang, sub_name=html.escape(name),
                plan_name=traffic_label(f"{gb:g}", lang) if gb is not None else "—",
                end_date=end_dt.strftime("%Y-%m-%d"), jalali_date=format_jalali_date(end_dt),
                config=f"<code>{html.escape(config)}</code>" if config else "",
            ),
            parse_mode="HTML",
        )
        bot.send_message(uid, t("main_menu", lang), reply_markup=kb.main_menu_kb(lang))
    except Exception:
        notified = False
    msg = (
        f"✅ Subscription #{sub_id} '{name}' added for @{user_row['username'] or '-'} (id {uid}) — "
        f"ends {end_dt.strftime('%Y-%m-%d')}"
        + (f", {gb:g} GB" if gb is not None else "")
        + ". "
        + ("The customer was notified." if notified else "⚠️ I couldn't message them — they must open the bot once (/start).")
        + "\nYou'll see it as #" + str(sub_id) + " in /user, and expiry reminders will go out automatically."
    )
    if created:
        msg += "\n(This ID wasn't known yet, so I created a placeholder for them.)"
    bot.send_message(ADMIN_ID, msg)


def _begin_addsub(user_row=None, created=False):
    if user_row:
        admin_state[ADMIN_ID] = {"addsub_step": "name", "uid": user_row["user_id"], "created": created}
        bot.send_message(ADMIN_ID, f"Adding a subscription for @{user_row['username'] or '-'} (id {user_row['user_id']}).\nWhat's the subscription name? (3–30 letters/numbers/_/-)")
    else:
        admin_state[ADMIN_ID] = {"addsub_step": "target"}
        bot.send_message(
            ADMIN_ID,
            "Who is the subscription for? Send their numeric user ID or @username.\n"
            "(They need to open this bot once, otherwise it can't message them.)",
        )


@bot.message_handler(commands=["addsub"])
def admin_addsub_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    parts = message.text.split(maxsplit=5)  # /addsub <who> <name> <days|date> <gb|-> [config]
    if len(parts) >= 5:
        row, created = _target_or_placeholder(parts[1])
        end_dt, (gb_ok, gb) = _parse_end_date(parts[3]), _parse_gb(parts[4])
        if not row or not SUBNAME_RE.match(parts[2]) or not end_dt or not gb_ok:
            bot.send_message(
                ADMIN_ID,
                "Couldn't read that. Format: /addsub <id or @user> <name> <days or YYYY-MM-DD> <GB or -> [link]",
            )
            return
        _finish_addsub(row, created, parts[2], end_dt, gb, parts[5].strip() if len(parts) == 6 else "")
        return
    _begin_addsub()


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("addsub_step")
    and not _looks_like_command(m.text)
)
def admin_addsub_flow(message):
    st = admin_state[ADMIN_ID]
    step = st["addsub_step"]
    text = (message.text or "").strip()
    if step == "target":
        row, created = _target_or_placeholder(text)
        if not row:
            bot.send_message(ADMIN_ID, "I don't recognize that. Send a numeric ID, or an @username of someone who has used the bot:")
            return
        _begin_addsub(row, created)
    elif step == "name":
        if not SUBNAME_RE.match(text):
            bot.send_message(ADMIN_ID, "Use 3–30 letters, numbers, _ or -. Try again:")
            return
        st.update({"name": text, "addsub_step": "days"})
        bot.send_message(ADMIN_ID, "How long is it valid? Send a number of days from today (e.g. 30) or an end date like 2026-12-31:")
    elif step == "days":
        end_dt = _parse_end_date(text)
        if not end_dt:
            bot.send_message(ADMIN_ID, "Send days (e.g. 30) or a future date like 2026-12-31:")
            return
        st.update({"end": end_dt.isoformat(), "addsub_step": "gb"})
        bot.send_message(ADMIN_ID, "Total data in GB? (a number, or - if unlimited/unknown)")
    elif step == "gb":
        ok, gb = _parse_gb(text)
        if not ok:
            bot.send_message(ADMIN_ID, "Send a number like 40 or 12.5, or -")
            return
        st.update({"gb": gb, "addsub_step": "config"})
        bot.send_message(ADMIN_ID, "Send the link/config the customer should get (or - to skip it):")
    elif step == "config":
        admin_state[ADMIN_ID] = {}
        row = db.get_user(st["uid"])
        _finish_addsub(row, st.get("created", False), st["name"], datetime.fromisoformat(st["end"]),
                       st["gb"], "" if text == "-" else text)


# ---------------- Admin: send a "data left" notice ----------------
def _apply_usage(sub_id, text):
    text = text.strip().replace(",", ".")
    try:
        remaining = float(text)
    except ValueError:
        remaining = -1
    if remaining < 0:
        bot.send_message(ADMIN_ID, "Send the remaining GB as a number, e.g. 12 or 7.5")
        return False
    row = db.set_subscription_usage(sub_id, remaining)
    if not row:
        bot.send_message(ADMIN_ID, f"No active subscription #{sub_id}.")
        return True
    uid = row["user_id"]
    lang = get_lang(uid)
    total = row["total_gb"]
    of_total = ""
    if total is not None:
        of_total = f" (از {total:g} گیگابایت)" if lang == "fa" else f" (of {total:g} GB)"
    try:
        bot.send_message(
            uid,
            t("usage_notice", lang, sub_name=row["sub_name"] or row["plan_name"],
              remaining=f"{remaining:g}", of_total=of_total),
        )
        note = "The customer was notified."
    except Exception:
        note = "⚠️ Couldn't message them (they may have blocked the bot or never opened it)."
    bot.send_message(ADMIN_ID, f"✅ Saved: #{sub_id} has {remaining:g} GB left. {note}")
    return True


@bot.message_handler(commands=["usage"])
def admin_usage_cmd(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    parts = message.text.split()  # /usage <sub_id> <gb_left>
    if len(parts) == 3 and parts[1].lstrip("#").isdigit():
        _apply_usage(int(parts[1].lstrip("#")), parts[2])
        return
    admin_state[ADMIN_ID] = {"usage_step": "target"}
    bot.send_message(ADMIN_ID, "Whose subscription? Send their user ID / @username (or a subscription number like #12):")


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("usage_step")
    and not _looks_like_command(m.text)
)
def admin_usage_flow(message):
    st = admin_state[ADMIN_ID]
    text = (message.text or "").strip()
    if st["usage_step"] == "target":
        if text.startswith("#") and text[1:].isdigit():
            st.update({"usage_step": "gb", "sub_id": int(text[1:])})
            bot.send_message(ADMIN_ID, f"How many GB are left on #{text[1:]}?")
            return
        row = _resolve_target(text)
        if not row:
            bot.send_message(ADMIN_ID, "I don't recognize that user. Try again, or send a subscription number like #12:")
            return
        subs = db.conn_subs(row["user_id"])
        if not subs:
            admin_state[ADMIN_ID] = {}
            bot.send_message(ADMIN_ID, "That user has no active subscriptions.")
            return
        if len(subs) == 1:
            st.update({"usage_step": "gb", "sub_id": subs[0]["id"]})
            bot.send_message(ADMIN_ID, f"How many GB are left on #{subs[0]['id']} ({subs[0]['sub_name']})?")
            return
        markup = types.InlineKeyboardMarkup()
        for sub in subs:
            markup.add(types.InlineKeyboardButton(f"#{sub['id']} {sub['sub_name'] or ''}", callback_data=f"usub_{sub['id']}"))
        bot.send_message(ADMIN_ID, "Which subscription?", reply_markup=markup)
    elif st["usage_step"] == "gb":
        sub_id = st["sub_id"]
        if _apply_usage(sub_id, text):
            admin_state[ADMIN_ID] = {}


# ---------------- Admin: buttons that start things ----------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("usub_"))
def admin_usub_button(call):
    if _not_admin(call):
        return
    sub_id = int(call.data.split("_")[1])
    admin_state[ADMIN_ID] = {"usage_step": "gb", "sub_id": sub_id}
    bot.answer_callback_query(call.id)
    bot.send_message(ADMIN_ID, f"How many GB are left on #{sub_id}?")


@bot.callback_query_handler(func=lambda c: c.data.startswith("uview_"))
def admin_uview_button(call):
    if _not_admin(call):
        return
    bot.answer_callback_query(call.id)
    _send_user_profile(ADMIN_ID, int(call.data.split("_")[1]))


@bot.callback_query_handler(func=lambda c: c.data.startswith("umsg_"))
def admin_umsg_button(call):
    if _not_admin(call):
        return
    bot.answer_callback_query(call.id)
    admin_state[ADMIN_ID] = {"msg_step": "awaiting_text", "target_user_id": int(call.data.split("_")[1])}
    bot.send_message(ADMIN_ID, t("admin_msg_ask_text", "en"))


@bot.callback_query_handler(func=lambda c: c.data.startswith("uban_"))
def admin_uban_button(call):
    if _not_admin(call):
        return
    uid = int(call.data.split("_")[1])
    bot.answer_callback_query(call.id)
    bot.send_message(ADMIN_ID, t("admin_ban_prior_record", "en", count=db.get_ban_count(uid)))
    admin_state[ADMIN_ID] = {"ban_step": "awaiting_duration", "target_user_id": uid}
    bot.send_message(ADMIN_ID, t("admin_ban_ask_duration", "en"))


@bot.callback_query_handler(func=lambda c: c.data.startswith("unflag_"))
def admin_unflag_button(call):
    if _not_admin(call):
        return
    uid = int(call.data.split("_")[1])
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    bot.send_message(ADMIN_ID, "🏳️ Flag cleared." if db.clear_user_flag(uid) else "That user wasn't flagged.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("uadd_"))
def admin_uadd_button(call):
    if _not_admin(call):
        return
    bot.answer_callback_query(call.id)
    row = db.get_user(int(call.data.split("_")[1]))
    if row:
        _begin_addsub(row)


@bot.callback_query_handler(func=lambda c: c.data.startswith("refund_"))
def admin_refund_button(call):
    if _not_admin(call):
        return
    bot.answer_callback_query(call.id)
    _refund_ask_amount(int(call.data.split("_")[1]))


# ---------------- Admin: the /admin button panel ----------------
ADMIN_HELP = (
    "📖 Admin commands\n\n"
    "/admin – button panel\n"
    "/pending – orders waiting on you (with buttons)\n"
    "/order <id> – one order, with its receipt\n"
    "/user <id|@name> – a customer's full profile\n"
    "/addsub – add a subscription by hand (they get notified)\n"
    "/usage – tell a customer how much data they have left\n"
    "/message – message one customer\n"
    "/broadcast <text> – message everyone\n"
    "/refund – record a refund\n"
    "/ban  /unban – manage bans\n"
    "/adddiscount  /discounts  /removediscount – discount codes\n"
    "/updateplans – set plans and prices\n"
    "/setrenew – prices for subscription updates\n"
    "/stats – numbers\n"
    "/dashboard – web dashboard link\n"
    "/backup – send the database now\n"
    "/getconfig <order_id> – re-fetch a delivered config\n"
    "/togglehours – working-hours on/off"
)


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if _not_admin(message):
        return
    admin_state[ADMIN_ID] = {}
    bot.send_message(ADMIN_ID, "🛠 Admin panel — tap what you need:", reply_markup=kb.admin_panel_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def admin_panel_action(call):
    if _not_admin(call):
        return
    action = call.data[4:]
    bot.answer_callback_query(call.id)
    admin_state[ADMIN_ID] = {}
    if action == "pending":
        _do_pending(ADMIN_ID)
    elif action == "stats":
        _do_stats(ADMIN_ID)
    elif action == "dashboard":
        _send_dashboard_link(ADMIN_ID)
    elif action == "backup":
        try:
            _send_backup(ADMIN_ID)
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Backup failed: {e}")
    elif action == "hours":
        now_enabled = not hours_restriction_enabled()
        db.set_setting("hours_enabled", "1" if now_enabled else "0")
        bot.send_message(ADMIN_ID, "✅ Working hours: ON" if now_enabled else "✅ Working hours: OFF (24/7)")
    elif action == "discounts":
        active = db.get_active_discounts()
        if not active:
            bot.send_message(ADMIN_ID, t("admin_discounts_list_empty", "en"))
        else:
            bot.send_message(ADMIN_ID, t("admin_discounts_list_header", "en") + "".join(
                t("admin_discounts_list_line", "en", code=d["code"], percent=d["percent"]) for d in active))
    elif action == "adddiscount":
        admin_state[ADMIN_ID] = {"discount_step": "awaiting_code"}
        bot.send_message(ADMIN_ID, t("admin_discount_ask_code", "en"))
    elif action == "renewprices":
        _do_renewprices(ADMIN_ID)
    elif action == "updateplans":
        admin_state[ADMIN_ID] = {"awaiting_plans_text": True}
        bot.send_message(ADMIN_ID, "Paste your plans, one per line: months - GB - final_price\nExample:\n1 - 20 - 98000")
    elif action == "message":
        admin_state[ADMIN_ID] = {"msg_step": "awaiting_target"}
        bot.send_message(ADMIN_ID, t("admin_msg_ask_target", "en"))
    elif action == "user":
        admin_state[ADMIN_ID] = {"lookup": "user"}
        bot.send_message(ADMIN_ID, "Send the user's numeric ID or @username:")
    elif action == "order":
        admin_state[ADMIN_ID] = {"lookup": "order"}
        bot.send_message(ADMIN_ID, "Send the order number:")
    elif action == "ban":
        admin_state[ADMIN_ID] = {"ban_step": "awaiting_target"}
        bot.send_message(ADMIN_ID, t("admin_ban_ask_target", "en"))
    elif action == "unban":
        admin_state[ADMIN_ID] = {"unban_step": "awaiting_target"}
        bot.send_message(ADMIN_ID, t("admin_unban_ask_target", "en"))
    elif action == "refund":
        admin_state[ADMIN_ID] = {"refund_step": "order"}
        bot.send_message(ADMIN_ID, "Which order number do you want to refund?")
    elif action == "addsub":
        _begin_addsub()
    elif action == "usage":
        admin_state[ADMIN_ID] = {"usage_step": "target"}
        bot.send_message(ADMIN_ID, "Whose subscription? Send their user ID / @username (or a subscription number like #12):")
    elif action == "help":
        bot.send_message(ADMIN_ID, ADMIN_HELP)


@bot.message_handler(commands=["help"])
def admin_help_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return  # customers just use the menu; /help stays silent for them
    bot.send_message(ADMIN_ID, ADMIN_HELP)


# ---------------- Reminders: subscription about to expire ----------------
def check_expiring_subscriptions():
    for sub in db.get_subscriptions_expiring(REMINDER_DAYS):
        uid = sub["user_id"]
        lang = get_lang(uid)
        end = datetime.fromisoformat(sub["end_date"])
        days_left = max(1, math.ceil((end - db._now()).total_seconds() / 86400))
        when = f"{days_left} روز" if lang == "fa" else f"{days_left} day(s)"
        try:
            bot.send_message(
                uid,
                t("reminder_expiring", lang, sub_name=sub["sub_name"] or sub["plan_name"], when=when,
                  end_date=end.strftime("%Y-%m-%d"), jalali_date=format_jalali_date(end)),
                reply_markup=kb.reminder_kb(lang, sub["id"]),
            )
        except Exception:
            pass  # blocked the bot / never opened it - don't retry forever
        db.mark_subscription_reminded(sub["id"])


def _reminder_loop():
    while True:
        try:
            check_expiring_subscriptions()
        except Exception as e:
            print("reminder loop error:", e)
        time.sleep(600)


# ---------------- helper: print file_id for videos sent to the bot ----------------
@bot.message_handler(content_types=["video"])
def print_video_file_id(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(
            message,
            f"file_id:\n{message.video.file_id}\n\nPaste this into .env under the "
            f"matching HOWTO_VIDEO_* variable.",
        )


def resume_pending_alarms():
    for o in db.get_pending_orders():
        if o["receipt_file_id"]:
            notify_admin_new_order(o["order_id"], o["receipt_file_id"])


def _fetch_receipt(order_id):
    """Receipt photo bytes for the dashboard (None if there isn't one)."""
    order = db.get_order(order_id)
    if not order or not order["receipt_file_id"]:
        return None
    info = bot.get_file(order["receipt_file_id"])
    return bot.download_file(info.file_path)


def _start_background_jobs():
    threading.Thread(target=_expiry_loop, daemon=True).start()
    threading.Thread(target=_reminder_loop, daemon=True).start()
    if BACKUP_ENABLED:
        threading.Thread(target=_backup_loop, daemon=True).start()
    if DASHBOARD_ENABLED:
        try:
            dashboard.start_server(
                DASHBOARD_HOST, DASHBOARD_PORT, BOT_TOKEN, ADMIN_ID, _fetch_receipt
            )
            print(f"Dashboard listening on http://{DASHBOARD_HOST}:{DASHBOARD_PORT} (use /dashboard in Telegram)")
        except OSError as e:
            print(f"Dashboard could not start ({e}) - the bot keeps running without it.")


if __name__ == "__main__":
    print("Bot is running...")
    resume_pending_alarms()
    _start_background_jobs()
    bot.infinity_polling()
