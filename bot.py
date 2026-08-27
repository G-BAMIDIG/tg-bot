import html
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import telebot
from telebot import types
from telebot.handler_backends import BaseMiddleware, CancelUpdate

import db
import keyboards as kb
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


bot.setup_middleware(BanMiddleware())
bot.setup_middleware(WorkingHoursMiddleware())


# ---------------- /start ----------------
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    state.pop(user_id, None)  # /start always fully cancels any stuck flow
    db.upsert_user(user_id, message.from_user.username or "")
    user = db.get_user(user_id)
    if user and user["lang"]:
        lang = user["lang"]
        bot.send_message(user_id, t("main_menu", lang), reply_markup=kb.main_menu_kb(lang))
        _arm_home_button_once(user_id, lang)
    else:
        bot.send_message(user_id, t("choose_lang", "en"), reply_markup=kb.lang_kb())


def _arm_home_button_once(user_id, lang):
    """Attaches the persistent Home reply-keyboard the first time only -
    after this, the note never shows again, but the button stays put."""
    user = db.get_user(user_id)
    if user and user["home_kb_shown"]:
        return
    bot.send_message(
        user_id,
        t("home_kb_intro", lang),
        reply_markup=kb.home_reply_kb(lang),
    )
    db.mark_home_kb_shown(user_id)


@bot.message_handler(func=lambda m: m.text in (t("btn_home", "en"), t("btn_home", "fa")))
def home_button_pressed(message):
    """Catches taps on the persistent 🏠 Home button from anywhere in the
    chat and drops the user straight back to the main menu, same as /start
    but without needing to type anything."""
    start(message)


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
    _arm_home_button_once(call.from_user.id, lang)


@bot.callback_query_handler(func=lambda c: c.data == "menu_changelang")
def change_lang(call):
    bot.edit_message_text(
        t("choose_lang", "en"),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb.lang_kb(),
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
        lines.append(t("sub_line", lang, name=s["sub_name"] or s["plan_name"], end_date=end_date))
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
    order_id = db.create_order(user_id, plan_id, total, chosen_username=sub_name)

    bot.send_message(
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
        ),
        parse_mode="HTML",
        reply_markup=kb.order_payment_kb(lang, order_id),
    )


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
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
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
    file_id = message.photo[-1].file_id
    db.set_order_receipt(order_id, file_id)
    state.pop(user_id, None)

    bot.send_message(message.chat.id, t("order_placed", lang))
    bot.send_message(message.chat.id, t("admin_working", lang))
    notify_admin_new_order(order_id, file_id)


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


def notify_admin_new_order(order_id, receipt_file_id, repeat=True):
    order = db.get_order(order_id)
    plan = db.get_plan(order["plan_id"])
    user = db.get_user(order["user_id"])
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
    )

    def send():
        bot.send_photo(
            ADMIN_ID, receipt_file_id, caption=text, reply_markup=kb.admin_order_kb(order_id)
        )

    if repeat:
        run_alarm(("order", order_id), send)
    else:
        # one-time resend (e.g. from /pending) - don't stack another
        # repeating alarm loop on top of one that may already be running
        send()


@bot.callback_query_handler(func=lambda c: c.data.startswith("seen_"))
def admin_seen(call):
    if call.from_user.id != ADMIN_ID:
        return
    order_id = int(call.data.split("_")[1])
    alarm_stop_flags[("order", order_id)] = True
    bot.answer_callback_query(call.id, "Marked as seen, alarm stopped.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("deliver_"))
def admin_deliver(call):
    if call.from_user.id != ADMIN_ID:
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
    if call.from_user.id != ADMIN_ID:
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


@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID
    and admin_state.get(ADMIN_ID, {}).get("awaiting_config_for") is not None
    and not _looks_like_command(m.text)
)
def admin_send_config(message):
    order_id = admin_state[ADMIN_ID]["awaiting_config_for"]
    admin_state[ADMIN_ID] = {}
    order = db.get_order(order_id)
    plan = db.get_plan(order["plan_id"])
    user_id = order["user_id"]
    lang = get_lang(user_id)
    plan_desc = f"{traffic_label(plan['traffic_gb'], lang)} — {duration_label(plan['duration_days'], lang)}"
    sub_name = order["chosen_username"] or "-"

    end_date = db.create_subscription(
        user_id, order_id, plan_desc, sub_name, message.text, plan["duration_days"]
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


# ---------------- Admin: look up a previously-delivered config ----------------
@bot.message_handler(commands=["getconfig"])
def admin_get_config(message):
    if message.from_user.id != ADMIN_ID:
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
@bot.message_handler(commands=["pending"])
def admin_pending(message):
    if message.from_user.id != ADMIN_ID:
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    orders = db.get_pending_orders()
    if not orders:
        bot.reply_to(message, t("admin_pending_none", "en"))
        return
    lines = [t("admin_pending_header", "en")]
    for o in orders:
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
    bot.reply_to(message, "".join(lines))

    # Also resend each one as a full actionable card (photo + Seen/Deliver/
    # Decline buttons) - if the original alert's buttons got lost, scrolled
    # away, or the repeating alarm already hit its time cap, this is the
    # actual way to recover and act on it right now.
    for o in orders:
        if o["receipt_file_id"]:
            notify_admin_new_order(o["order_id"], o["receipt_file_id"], repeat=False)


# ---------------- Admin: quick business stats ----------------
@bot.message_handler(commands=["stats"])
def admin_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    admin_state[ADMIN_ID] = {}  # cancel any stuck multi-step flow
    s = db.get_stats()
    bot.reply_to(
        message,
        t(
            "admin_stats",
            "en",
            users=s["users"],
            total_orders=s["total_orders"],
            delivered_orders=s["delivered_orders"],
            revenue=s["revenue"],
            pending_orders=s["pending_orders"],
            active_subscriptions=s["active_subscriptions"],
        ),
    )


# ---------------- Admin: broadcast a message to every user ----------------
@bot.message_handler(commands=["broadcast"])
def admin_broadcast(message):
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
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
    if call.from_user.id != ADMIN_ID:
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


# ---------------- Admin: discount codes ----------------
@bot.message_handler(commands=["adddiscount"])
def admin_adddiscount_start(message):
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
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


def _run_expiry_reminder_loop():
    """Checks every hour for subscriptions crossing the 7/3/1-day-left
    marks and DMs the user once per threshold (tracked in the DB so a
    restart never re-sends a reminder that already went out)."""
    def loop():
        while True:
            for threshold in (7, 3, 1):
                for sub in db.get_subscriptions_needing_reminder(threshold):
                    lang = get_lang(sub["user_id"])
                    try:
                        bot.send_message(
                            sub["user_id"],
                            t(
                                "reminder_expiring",
                                lang,
                                name=sub["sub_name"] or sub["plan_name"],
                                days=threshold,
                            ),
                        )
                    except Exception:
                        pass  # user may have blocked the bot - skip, don't crash the loop
                    db.mark_reminder_sent(sub["id"], threshold)
            time.sleep(3600)

    threading.Thread(target=loop, daemon=True).start()


def _setup_command_menu():
    """The '/' grid-menu icon next to the text box. Regular users only ever
    see /start there; the full admin command list is scoped to ADMIN_ID
    only, via Telegram's per-chat command scope - nobody else can see it."""
    from telebot import types as _types

    bot.set_my_commands(
        [_types.BotCommand("start", "Open the main menu")]
    )
    bot.set_my_commands(
        [
            _types.BotCommand("start", "Open the main menu"),
            _types.BotCommand("pending", "List pending orders"),
            _types.BotCommand("getconfig", "Get config for an order"),
            _types.BotCommand("stats", "Bot statistics"),
            _types.BotCommand("broadcast", "Message every user"),
            _types.BotCommand("togglehours", "Toggle working-hours restriction"),
            _types.BotCommand("ban", "Ban a user"),
            _types.BotCommand("unban", "Unban a user"),
            _types.BotCommand("adddiscount", "Create a discount code"),
            _types.BotCommand("discounts", "List discount codes"),
            _types.BotCommand("removediscount", "Deactivate a discount code"),
            _types.BotCommand("updateplans", "Bulk-update plan pricing"),
        ],
        scope=_types.BotCommandScopeChat(ADMIN_ID),
    )


def _run_keepalive_server():
    """Render's free web service plan requires something listening on
    $PORT, or the deploy is considered failed / gets marked unhealthy.
    The bot itself runs in polling mode (no HTTP server needed for
    Telegram), so this just answers health checks / keeps the service
    classified as a web service. It has nothing to do with the bot logic."""
    import os
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")

        def log_message(self, format, *args):
            pass  # silence default request logging

    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    print("Bot is running...")
    resume_pending_alarms()
    _setup_command_menu()
    _run_expiry_reminder_loop()
    threading.Thread(target=_run_keepalive_server, daemon=True).start()
    bot.infinity_polling()
