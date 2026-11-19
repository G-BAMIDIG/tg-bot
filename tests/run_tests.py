"""
Offline test-suite for the VPN bot. Runs without Telegram or internet:

    python tests/run_tests.py

It loads the real bot code against a small fake Telegram client, plays customer
and admin conversations through it, and checks what the bot sent and stored.
It uses a temporary database - your real vpnbot.db is never touched.
"""
import hashlib
import hmac
import http.client
import io
import json
import os
import sys
import tempfile
import time
import urllib.parse
import zipfile
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "fake_telebot"))
sys.path.insert(0, ROOT)

from cryptography.fernet import Fernet  # noqa: E402

TMP = tempfile.mkdtemp(prefix="vpnbot-test-")
os.environ.update({
    "DB_PATH": os.path.join(TMP, "test.db"),
    "ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "ALARM_MAX_PINGS": "1", "ALARM_INTERVAL_SECONDS": "1",
    "RATE_LIMIT_MAX": "100000",          # general tests send lots of messages
    "ORDER_FEE_PERCENT": "5",
})

import telebot.types as tt  # noqa: E402
import backup as backup_mod  # noqa: E402
import bot as B  # noqa: E402
import dashboard  # noqa: E402
import db  # noqa: E402
import guard as guard_mod  # noqa: E402
import keyboards as kbmod  # noqa: E402
import locales  # noqa: E402
import roadmap  # noqa: E402
import utils  # noqa: E402

ADMIN = B.ADMIN_ID
PASS, FAIL = [], []
_uid = [10000]


def check(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")


def section(name):
    print(f"\n== {name}")


# ----------------------------------------------------------------- helpers
def msg(uid, text=None, photo=False):
    return tt.Message(tt.Chat(uid), tt.User(uid, f"u{uid}" if uid != ADMIN else "admin"),
                      text=text, photo=[tt.Photo(f"RECEIPT_{uid}")] if photo else None)


def cb(uid, data):
    return tt.CallbackQuery(tt.User(uid, f"u{uid}"), tt.Message(tt.Chat(uid), tt.User(uid, f"u{uid}")), data)


def say(uid, text):
    B.bot.dispatch_message(msg(uid, text))


def tap(uid, data):
    B.bot.dispatch_callback(cb(uid, data))


def settle():
    time.sleep(0.15)  # alarm threads run in the background


def to(chat):
    return [s for s in B.bot.sent if s.get("chat_id") == chat and s["type"] in ("message", "photo", "edit", "reply", "document", "video")]


def txt(s):
    return (s.get("text") or s.get("caption") or "")


def last(chat):
    return to(chat)[-1]


def all_text(chat):
    return "\n".join(txt(s) for s in to(chat))


def mark():
    B.bot.sent.clear()


def mkuser(lang="en"):
    _uid[0] += 1
    db.upsert_user(_uid[0], f"u{_uid[0]}")
    db.set_lang(_uid[0], lang)
    return _uid[0]


def buttons(s):
    return s["reply_markup"].all_buttons() if s and s.get("reply_markup") else []


def cbdata(s):
    return [b.callback_data for b in buttons(s) if b.callback_data]


def sql(q, *a):
    if len(a) == 1 and isinstance(a[0], tuple):
        a = a[0]
    conn = db.get_conn()
    conn.execute(q, a)
    conn.commit()
    conn.close()


def past(minutes=5):
    return (db._now() - timedelta(minutes=minutes)).isoformat()


def latest_order(uid):
    conn = db.get_conn()
    r = conn.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    conn.close()
    return r


def make_invoice(uid, plan, name="mysub123"):
    tap(uid, f"plan_{plan['id']}")
    tap(uid, f"finalize_{plan['id']}")
    say(uid, name)
    tap(uid, "discount_skip")
    return last(uid), latest_order(uid)["id"]


def pay(uid, oid):
    tap(uid, f"order_paid_{oid}")
    B.bot.dispatch_message(msg(uid, photo=True))
    settle()


def deliver(oid, config="vless://deliver-test@1.1.1.1:443#x"):
    tap(ADMIN, f"deliver_{oid}")
    say(ADMIN, config)


def delivered_sub(uid, plan, name="subname1", config="vless://deliver-test@1.1.1.1:443#x"):
    """Full purchase through to delivery. Returns (order_id, sub_row)."""
    inv, oid = make_invoice(uid, plan, name)
    pay(uid, oid)
    deliver(oid, config)
    sub = [s for s in db.get_active_subscriptions(uid) if s["order_id"] == oid][0]
    return oid, sub


# =================================================================== setup
db.init_db()
db.set_setting("hours_enabled", "0")
say(ADMIN, "/updateplans")
say(ADMIN, "1 - 20 - 100000\n1 - 60 - 210000\n3 - 150 - 564000")
PLAN20 = [p for p in db.get_active_plans(30) if p["traffic_gb"] == 20][0]
PLAN60 = [p for p in db.get_active_plans(30) if p["traffic_gb"] == 60][0]

# =================================================================== 1
section("1. Main menu, language, My Orders, share, best-value badge")
u1 = mkuser("en")
mark()
say(u1, "/start")
labels = [b.text for b in buttons(last(u1))]
check(len(labels) == 7, f"main menu has the 7 expected buttons -> {len(labels)}")
check(any("My Orders" in l for l in labels) and any("Share" in l for l in labels), "My Orders and Share buttons present")
tap(u1, "menu_myorders")
check("don't have any orders" in txt(last(u1)), "My Orders is friendly when empty")
tap(u1, "menu_share")
share_btn = [b for b in buttons(last(u1)) if b.url]
check(share_btn and "t.me/share/url" in share_btn[0].url and "testbot" in share_btn[0].url, "Share opens Telegram's share sheet with the bot link")
tap(u1, "buy_duration_30")
tier_labels = [b.text for b in buttons(last(u1)) if b.callback_data and b.callback_data.startswith("plan_")]
check(sum("Best value" in l for l in tier_labels) == 1 and "Best value" in [l for l in tier_labels if "60GB" in l][0],
      "exactly one plan carries the Best-value badge, the cheapest per GB (60GB)")

# =================================================================== 2
section("2. Invoice timer: expiry, stale buttons, background expiry")
u2 = mkuser("en")
inv, oid = make_invoice(u2, PLAN20)
o = db.get_order(oid)
mins = (__import__("datetime").datetime.fromisoformat(o["expires_at"]) - db._now()).total_seconds() / 60
check(58 < mins <= 60.1, f"new invoice is valid for ~60 minutes -> {mins:.1f}")
check("valid for 60 minutes" in txt(inv), "invoice text tells the customer the time limit")
check(o["invoice_msg_id"] is not None, "invoice message id stored (so the button can be removed later)")

# an old invoice from months ago must not be payable
sql("UPDATE orders SET created_at=%s, expires_at=%s WHERE id=%s",
    ((db._now() - timedelta(days=90)).isoformat(), past(60 * 24 * 90), oid))
mark()
tap(u2, f"order_paid_{oid}")
check("expired" in all_text(u2).lower(), "clicking Send Receipt on a 3-month-old invoice is refused")
check(db.get_order(oid)["status"] == "expired", "that order is now marked expired")
B.bot.dispatch_message(msg(u2, photo=True))
check(not any(s["type"] == "photo" and s["chat_id"] == ADMIN for s in B.bot.sent), "no receipt reached the admin for the expired order")

# background expiry
inv, oid = make_invoice(u2, PLAN20, "second1abc")
sql("UPDATE orders SET expires_at=%s WHERE id=%s", (past(), oid))
mark()
B.expire_stale_orders()
check(db.get_order(oid)["status"] == "expired", "background job expires an unpaid invoice")
check("expired because no receipt" in all_text(u2), "customer is notified")
check(any(m[0] == u2 and m[2] is None for m in B.bot.markup_edits), "the old Send Receipt button was removed")

# expires while the customer is mid-way sending the receipt
inv, oid = make_invoice(u2, PLAN20, "third1abcd")
tap(u2, f"order_paid_{oid}")
sql("UPDATE orders SET expires_at=%s WHERE id=%s", (past(), oid))
mark()
B.bot.dispatch_message(msg(u2, photo=True))
check("expired" in all_text(u2).lower() and db.get_order(oid)["status"] == "expired", "a receipt sent after the deadline is rejected")
check(B.state.get(u2, {}).get("step") != "awaiting_receipt", "conversation state cleaned up")

# =================================================================== 3
section("3. Receipt -> alarm -> delivery -> rating, with safety checks")
u3 = mkuser("en")
inv, oid = make_invoice(u3, PLAN20, "buyer3name")
mark()
pay(u3, oid)
check("Usually delivered in about 10-30 minutes" in all_text(u3), "delivery estimate shown (default until real data exists)")
alert = [s for s in B.bot.sent if s["type"] == "photo" and s["chat_id"] == ADMIN][-1]
check("ORDER! ORDER!" in txt(alert) and "buyer3name" in txt(alert), "admin alarm has the order details")
check({"seen_%d" % oid, "deliver_%d" % oid, "decline_%d" % oid} <= set(cbdata(alert)), "alarm has Seen / Deliver / Decline")
check(db.get_order(oid)["receipt_at"] is not None, "receipt time recorded")
deliver(oid)
sub = db.get_active_subscriptions(u3)[0]
check(sub["total_gb"] == 20 and sub["remaining_gb"] is None, "delivered subscription remembers its 20 GB")
prompt = [s for s in to(u3) if "How was your experience" in txt(s)]
check(prompt and len([d for d in cbdata(prompt[-1]) if d.startswith("rate_")]) == 5, "customer is asked for a 1-5 star rating")
tap(u3, f"rate_{oid}_4")
check(db.get_order(oid)["rating"] == 4, "rating saved")
mark()
tap(u3, f"rate_{oid}_1")
check(db.get_order(oid)["rating"] == 4, "a second rating can't overwrite the first")
tap(u3, f"rate_{oid}_9")
check(db.get_order(oid)["rating"] == 4, "an out-of-range rating is ignored")
other = mkuser()
tap(other, f"rate_{oid}_5")
check(db.get_order(oid)["rating"] == 4, "someone else can't rate your order")
mark()
tap(ADMIN, f"deliver_{oid}")
say(ADMIN, "vless://second-delivery")
check(len(db.get_active_subscriptions(u3)) == 1 and "isn't waiting for delivery" in all_text(ADMIN), "delivering twice is blocked")
tap(u3, "menu_myorders")
check(f"#{oid}" in txt(last(u3)) and "Delivered" in txt(last(u3)), "My Orders shows the order and its status")

# =================================================================== 4
section("3b. Persian customer sees Persian status/ETA")
u3f = mkuser("fa")
inv, oid_f = make_invoice(u3f, PLAN20, "farsiuser1")
check("اعتبار دارد" in txt(inv), "Persian invoice shows the validity line")
pay(u3f, oid_f)
check("معمولاً حدود" in all_text(u3f), "Persian delivery estimate")
tap(u3f, "menu_myorders")
check("در حال بررسی" in txt(last(u3f)), "Persian 'under review' status")

# =================================================================== 5
section("4. Update subscription (renewal / extra data)")
ur = mkuser("en")
oid_base, sub = delivered_sub(ur, PLAN20, "renewme123")
end_before = __import__("datetime").datetime.fromisoformat(sub["end_date"])
tap(ur, "menu_mysubs")
cds = cbdata(last(ur))
check(f"renew_{sub['id']}" in cds and f"getlink_{sub['id']}" in cds, "My Subscriptions has Get URL and Update buttons")
tap(ur, f"renew_{sub['id']}")
check("minimum 1 month" in txt(last(ur)) and "20 GB" in txt(last(ur)) and "600 GB" in txt(last(ur)), "intro states the 1-month / 20-600 GB rules")
check({"rmonths_1", "rmonths_12", "rmonths_0"} <= set(cbdata(last(ur))), "month choices offered, with a skip")
tap(ur, "rmonths_1")
for bad in ("15", "700", "abc", "19.5"):
    mark()
    say(ur, bad)
    check("between 20 and 600" in all_text(ur), f"'{bad}' rejected")
mark()
say(ur, "20")
inv = last(ur)
check("110000" in txt(inv) and "5500" in txt(inv) and "115500" in txt(inv), "price = 1 month (50000) + 20 GB (60000) + 5% fee = 115500")
check(f"#{oid_base}" in txt(inv), "customer sees which order this updates")
ren = latest_order(ur)
check(ren["kind"] == "renewal" and ren["extra_days"] == 30 and ren["extra_gb"] == 20 and ren["price"] == 115500
      and ren["expires_at"] is not None and ren["renew_sub_id"] == sub["id"], "renewal order stored correctly (with an invoice timer)")
mark()
pay(ur, ren["id"])
alert = [s for s in B.bot.sent if s["type"] == "photo" and s["chat_id"] == ADMIN][-1]
check("RENEWAL REQUEST" in txt(alert) and f"update of order #{oid_base}" in txt(alert), "admin alert names the original order number")
check("1 month(s) (30 days)" in txt(alert) and "20 GB" in txt(alert) and f"rapprove_{ren['id']}" in cbdata(alert), "alert shows what was requested and an Approve button")
mark()
tap(ADMIN, f"rapprove_{ren['id']}")
sub2 = db.get_subscription(sub["id"])
new_end = __import__("datetime").datetime.fromisoformat(sub2["end_date"])
check(new_end - end_before == timedelta(days=30), "expiry extended by exactly 30 days")
check(sub2["total_gb"] == 40, "capacity increased by 20 GB")
check("updated" in all_text(ur) and "New expiry" in all_text(ur), "customer told it was applied")
check(db.get_order(ren["id"])["status"] == "delivered", "renewal order marked delivered")
mark()
tap(ADMIN, f"rapprove_{ren['id']}")
check("can't be approved" in all_text(ADMIN) and db.get_subscription(sub["id"])["end_date"] == sub2["end_date"], "approving twice doesn't extend twice")

mark(); tap(ur, f"renew_{sub['id']}"); tap(ur, "rmonths_0"); tap(ur, "rgb_0")
check("skipped both" in all_text(ur), "skipping both time and data is refused")
tap(ur, "rmonths_3"); tap(ur, "rgb_0")
check("157500" in txt(last(ur)), "time only: 3 months -> 150000 + 5% = 157500")
tap(ur, f"renew_{sub['id']}"); tap(ur, "rmonths_0"); tap(ur, "rgb_50")
check("157500" in txt(last(ur)), "data only: 50 GB -> 150000 + 5% = 157500")
stranger = mkuser()
mark(); tap(stranger, f"renew_{sub['id']}")
check(B.state.get(stranger, {}).get("step") is None, "someone else's subscription can't be renewed")
say(ADMIN, "/setrenew 60000 4000")
tap(ur, f"renew_{sub['id']}"); tap(ur, "rmonths_1"); say(ur, "20")
check("147000" in txt(last(ur)), "/setrenew changes prices instantly (60000 + 20x4000, +5% = 147000)")
say(ADMIN, "/setrenew 50000 3000")

# =================================================================== 6
section("5. Subscriptions added by hand, data-left notices, expiry reminders")
um = mkuser("en")
mark()
say(ADMIN, f"/addsub {um} handsub1 30 40 vless://manual-link@9.9.9.9:443")
msub = [s for s in db.get_active_subscriptions(um)][0]
check(msub["manual"] == 1 and msub["total_gb"] == 40 and msub["remaining_gb"] == 40 and msub["order_id"] is None, "manual subscription stored")
check("handsub1" in all_text(um) and "<code>vless://manual-link@9.9.9.9:443</code>" in all_text(um), "customer is notified with a copyable link")
check("added" in all_text(ADMIN) and f"#{msub['id']}" in all_text(ADMIN), "admin gets a confirmation with the subscription number")
tap(um, "menu_mysubs")
tap(um, f"getlink_{msub['id']}")
check("vless://manual-link" in txt(last(um)), "Get URL works for it")
# guided + no link + date
mark()
say(ADMIN, "/addsub")
say(ADMIN, f"@u{um}")
say(ADMIN, "a")
check("3–30" in all_text(ADMIN), "name validation")
say(ADMIN, "guided-sub"); say(ADMIN, "0"); say(ADMIN, "10"); say(ADMIN, "abc"); say(ADMIN, "-"); say(ADMIN, "-")
subs = db.get_active_subscriptions(um)
gs = [s for s in subs if s["sub_name"] == "guided-sub"][0]
check(gs["total_gb"] is None and not db.get_subscription(gs["id"])["config_text"], "guided flow created it with no link and unknown data")
mark(); tap(um, f"getlink_{gs['id']}")
check("No link" in "".join(txt(s) for s in B.bot.sent), "Get URL says there's no link yet instead of sending an empty message")
say(ADMIN, f"/addsub {um} datesub 2099-12-31 -")
check(any(s["sub_name"] == "datesub" and s["end_date"].startswith("2099-12-31") for s in db.get_active_subscriptions(um)), "end date given as a calendar date works")
mark(); say(ADMIN, f"/addsub {um} pastsub 2001-01-01 -")
check("Couldn't read" in all_text(ADMIN), "a past date is refused")
# unknown id + blocked user
B.bot.fail_for.add(424242)
mark(); say(ADMIN, "/addsub 424242 ghostsub 5 10")
check(db.get_user(424242) is not None, "a never-seen numeric ID gets a placeholder")
check("couldn't message them" in all_text(ADMIN) or "couldn't message" in all_text(ADMIN).lower(), "admin is warned they can't be reached yet")
B.bot.fail_for.discard(424242)

mark()
say(ADMIN, f"/usage {msub['id']} 12.5")
check("12.5 GB of data left (of 40 GB)" in all_text(um), "customer is told how much data is left")
check(db.get_subscription(msub["id"])["remaining_gb"] == 12.5, "remaining data stored")
tap(um, "menu_mysubs")
check("12.5 GB left" in txt(last(um)), "My Subscriptions shows the remaining data")
umf = mkuser("fa")
say(ADMIN, f"/addsub {umf} farsisub 30 100 vless://fa")
fsub = db.get_active_subscriptions(umf)[0]
mark(); say(ADMIN, f"/usage {fsub['id']} 7")
check("گیگابایت" in all_text(umf) and "7" in all_text(umf), "Persian customers get the notice in Persian")
mark(); say(ADMIN, "/usage 999999 5"); check("No active subscription" in all_text(ADMIN), "unknown subscription number")
mark(); say(ADMIN, f"/usage {fsub['id']} -3"); check("number" in all_text(ADMIN), "negative value refused")
# guided usage with several subscriptions
mark(); say(ADMIN, "/usage"); say(ADMIN, f"@u{um}")
pick = [d for d in cbdata(last(ADMIN)) if d.startswith("usub_")]
check(len(pick) >= 2, "several subscriptions -> admin picks one with buttons")
tap(ADMIN, pick[0]); say(ADMIN, "3.5")
check("3.5 GB" in all_text(um), "guided flow sends the notice")

# reminders
mark()
sql("UPDATE subscriptions SET end_date=%s, reminded=0 WHERE id=%s", ((db._now() + timedelta(days=2)).isoformat(), msub["id"]))
sql("UPDATE subscriptions SET end_date=%s, reminded=0 WHERE id=%s", ((db._now() + timedelta(days=10)).isoformat(), gs["id"]))
sql("UPDATE subscriptions SET end_date=%s, reminded=0 WHERE id=%s", ((db._now() + timedelta(days=2)).isoformat(), fsub["id"]))
B.check_expiring_subscriptions()
check("expires in" in all_text(um) and f"renew_{msub['id']}" in [d for s in to(um) for d in cbdata(s)], "customer gets an expiry reminder with an Update button")
check("روز" in all_text(umf), "Persian reminder")
check(db.get_subscription(msub["id"])["reminded"] == 1 and db.get_subscription(gs["id"])["reminded"] == 0, "only subscriptions inside the 3-day window are reminded")
n = len(to(um)); B.check_expiring_subscriptions()
check(len(to(um)) == n, "no repeat reminders")
sql("UPDATE subscriptions SET end_date=%s WHERE id=%s", (past(60), gs["id"]))
B.check_expiring_subscriptions()
check(db.get_subscription(gs["id"])["reminded"] == 0, "already-expired subscriptions aren't reminded")

# =================================================================== 7
section("6. Admin tools: /order /user /refund /message /backup /dashboard /admin")
mark(); say(ADMIN, f"/order {oid_base}")
card = last(ADMIN)
check(card["type"] == "photo" and f"Order #{oid_base}" in txt(card) and "delivered" in txt(card), "/order shows the order with its receipt photo")
check(f"refund_{oid_base}" in cbdata(card) and f"uview_{ur}" in cbdata(card), "order card has Refund and View-user buttons")
mark(); say(ADMIN, "/order 999999"); check("not found" in all_text(ADMIN), "/order for a missing number")
mark(); say(ADMIN, f"/user {ur}")
prof = last(ADMIN)
check("Spent" in txt(prof) and "renewme123" in txt(prof), "/user shows spend and subscriptions")
check(any(d.startswith("usub_") for d in cbdata(prof)) and f"uadd_{ur}" in cbdata(prof) and f"umsg_{ur}" in cbdata(prof), "profile has message / add-subscription / usage buttons")
mark(); say(ADMIN, f"/user @u{ur}"); check("Spent" in all_text(ADMIN), "/user works with @username")
mark(); say(ADMIN, "/user @nobody_here"); check("don't recognize" in all_text(ADMIN), "unknown user")

# refunds
ur2 = mkuser("fa")
oid_r, _ = delivered_sub(ur2, PLAN20, "refundme12")
price_r = db.get_order(oid_r)["price"]
before = db.get_stats()
mark(); say(ADMIN, f"/refund {oid_r} 1000 partial test")
o = db.get_order(oid_r)
check(o["refunded_amount"] == 1000 and o["status"] == "delivered", "partial refund keeps the order delivered")
check("بازگشت وجه" in all_text(ur2), "customer notified in Persian")
mark(); say(ADMIN, f"/refund {oid_r} {price_r} too much")
check("Amount must be between" in all_text(ADMIN), "can't refund more than what's left")
mark(); say(ADMIN, f"/refund {oid_r} full whole rest")
check(db.get_order(oid_r)["status"] == "refunded" and db.get_order(oid_r)["refunded_amount"] == price_r, "full refund marks it refunded")
after = db.get_stats()
check(after["refunded_total"] - before["refunded_total"] == price_r, "stats count the refund")
check(before["revenue"] - after["revenue"] == price_r, "net revenue drops by exactly the refunded amount")
mark(); say(ADMIN, f"/refund {oid_r} 5 again"); check("Amount must be between" in all_text(ADMIN), "nothing left to refund")
mark(); say(ADMIN, "/refund"); say(ADMIN, "999999")
check("not found" in all_text(ADMIN), "guided refund: unknown order")
mark(); say(ADMIN, "/refund"); say(ADMIN, str(oid_base)); say(ADMIN, "abc"); say(ADMIN, "500"); say(ADMIN, "goodwill")
check(db.get_order(oid_base)["refunded_amount"] == 500, "guided refund works end to end")
mark(); tap(ADMIN, f"refund_{oid_base}"); check("How much" in all_text(ADMIN), "Refund button on the order card starts the flow")
say(ADMIN, "/stats")
check("Refunded so far" in last(ADMIN)["text"] and "Average rating" in last(ADMIN)["text"], "/stats shows refunds and ratings")

# message
mark(); say(ADMIN, f"/message {um} Hello from admin")
check("Hello from admin" in all_text(um), "/message still works")


# admin panel: every button must work
mark(); say(ADMIN, "/admin")
panel = last(ADMIN)
panel_actions = [d for d in cbdata(panel) if d.startswith("adm_")]
check(len(panel_actions) >= 18, f"panel offers {len(panel_actions)} actions")
broken = []
for d in panel_actions:
    mark()
    try:
        tap(ADMIN, d)
        if not to(ADMIN):
            broken.append(d + " (no reply)")
    except Exception as e:  # noqa: BLE001
        broken.append(f"{d} ({type(e).__name__}: {e})")
    B.admin_state[ADMIN] = {}
check(not broken, f"every admin-panel button responds -> {broken or 'ok'}")
db.set_setting("hours_enabled", "0")  # the panel's Toggle-hours button just flipped it
mark(); say(ADMIN, "/help"); check("Admin commands" in all_text(ADMIN) and "/addsub" in all_text(ADMIN), "/help lists the commands")
mark(); say(um, "/help"); check(not to(um), "/help stays silent for customers")

# =================================================================== 8
section("7. Security: non-admin alerts, flagging, rate limit, flood protection")
bad = mkuser("en")
mark(); say(bad, "/ban")
check(not to(bad), "a customer using an admin command gets nothing back")
check("Non-admin" in all_text(ADMIN) and f"id {bad}" in all_text(ADMIN), "…but the admin is alerted")
mark(); say(bad, "/stats"); say(bad, "/pending")
check("Non-admin" not in all_text(ADMIN), "alerts are throttled (no spam)")
mark(); tap(bad, f"deliver_{oid}")
check(db.get_order(oid)["status"] == "delivered", "a non-admin can't press admin buttons")

fl = mkuser("en")
for i in range(3):
    inv, o_id = make_invoice(fl, PLAN20, f"flagged{i}abc")
    pay(fl, o_id)
    tap(ADMIN, f"decline_{o_id}")
    say(ADMIN, "fake receipt")
check(db.get_user(fl)["flagged"] == 1, "3 declined receipts flag the customer")
check("Flagged" in all_text(ADMIN) and any(d.startswith("uban_") for s in to(ADMIN) for d in cbdata(s)), "admin alerted with Ban / Dismiss buttons")
inv, o_id = make_invoice(fl, PLAN20, "flagged9abc")
mark(); pay(fl, o_id)
check("FLAGGED" in all_text(ADMIN), "the flagged customer's next order carries a warning")
tap(ADMIN, f"unflag_{fl}")
check(db.get_user(fl)["flagged"] == 0, "Dismiss clears the flag")

g = guard_mod.Guard(3, 5, 2)
res = [g.check(1, t) for t in (0, 0.1, 0.2, 0.3, 0.4)]
check(res == ["ok", "ok", "ok", "limited", "limited"], f"guard: burst gets limited -> {res}")
res = [g.check(1, t) for t in (6, 6.1, 6.2, 6.3)]
check(res == ["ok", "ok", "ok", "flood"], f"guard: a second burst escalates to flood -> {res}")
check(g.cooldown_ok("k", 1, 100, 10) and not g.cooldown_ok("k", 1, 105, 10) and g.cooldown_ok("k", 1, 111, 10), "cooldown helper")

B._guard = guard_mod.Guard(3, 0.3, 2)
spam = mkuser("en")
mark()
for _ in range(5):
    say(spam, "/start")
check(sum("slow down" in txt(s).lower() for s in to(spam)) == 1, "customer is told to slow down once, not spammed")
time.sleep(0.4)
for _ in range(5):
    say(spam, "/start")
settle()
check(db.get_active_ban(spam) is not None, "continued flooding gets an automatic temporary ban")
check("flood protection" in all_text(ADMIN).lower() and any(d.startswith("unban_") for s in to(ADMIN) for d in cbdata(s)), "admin alerted with an Unban button")
mark(); say(spam, "/start"); say(spam, "/start")
check(len(to(spam)) <= 1, "banned flooder gets at most one notice per few seconds")
mark()
for _ in range(30):
    say(ADMIN, "/stats")
check(sum("Stats" in txt(s) for s in to(ADMIN)) == 30, "the admin is never rate-limited")
B._guard = guard_mod.Guard(100000, 5, 3)

# =================================================================== 9
section("8. Regression: earlier features still work")
st = mkuser("en")
tap(st, "buy_duration_30"); tap(st, f"plan_{PLAN20['id']}"); tap(st, f"finalize_{PLAN20['id']}")
say(st, "/start")
check(B.state.get(st) is None, "/start in the middle of a purchase clears the unfinished step")
tap(st, f"finalize_{PLAN20['id']}")
say(ADMIN, "/pending")  # admin stuck%s make sure commands escape stuck states
B.state[ADMIN] = {"step": "awaiting_sub_name", "plan_id": PLAN20["id"]}
mark(); say(ADMIN, "/pending"); check("Orders awaiting" in all_text(ADMIN) or "No orders" in all_text(ADMIN), "a stuck state can't swallow /pending")
B.state.pop(ADMIN, None)
say(ADMIN, "/adddiscount"); say(ADMIN, "tenoff"); say(ADMIN, "10")
dq = mkuser("en")
tap(dq, f"plan_{PLAN20['id']}"); tap(dq, f"finalize_{PLAN20['id']}"); say(dq, "disc1name"); say(dq, "tenoff")
check("-10000" in txt(last(dq)) and "94500" in txt(last(dq)), "discount code: 100000 - 10% + 5% fee = 94500")
bb = mkuser("en")
say(ADMIN, "/ban"); say(ADMIN, str(bb)); say(ADMIN, "2h"); say(ADMIN, "testing")
mark(); say(bb, "/start"); check("banned" in all_text(bb).lower(), "ban still blocks and explains")
tap(ADMIN, f"unban_{bb}"); mark(); say(bb, "/start"); check("Main menu" in all_text(bb), "unban restores access")
for plat in ("android", "ios", "windows"):
    mark(); tap(st, f"howto_{plat}")
    check(any(b.url for b in buttons(last(st))), f"How to Connect: {plat}")
db.set_setting("hours_enabled", "0")
say(ADMIN, "/togglehours")
check(db.get_setting("hours_enabled") == "1", "/togglehours turns the restriction on")
say(ADMIN, "/togglehours")
check(db.get_setting("hours_enabled") == "0", "…and off again")
db.set_setting("hours_enabled", "0")

# =================================================================== 10
section("9. Dashboard: login security, every page, receipts")
srv = dashboard.start_server("127.0.0.1", 0, B.BOT_TOKEN, ADMIN, B._fetch_receipt)
PORT = srv.server_address[1]


def web(path, cookie=None, method="GET", body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    out = (r.status, dict(r.getheaders()), data)
    c.close()
    return out


check(web("/")[0] == 200 and b"Admin only" in web("/")[2], "the home page is locked without a session")
check(web("/api/summary")[0] == 401, "API refuses requests without a session")
check(web("/receipt/1")[0] == 401, "receipts are protected too")
check(web("/login%st=guess")[0] == 403, "a wrong login token is refused")
mark(); say(ADMIN, "/dashboard")
link = [w for w in all_text(ADMIN).split() if "/login%st=" in w][0]
token = link.split("t=")[1]
code, hdr, _ = web(f"/login%st={token}")
cookie = hdr["Set-Cookie"].split(";")[0]
check(code == 302 and "HttpOnly" in hdr["Set-Cookie"], "one-time link logs you in with an HttpOnly cookie")
check(web(f"/login%st={token}")[0] == 403, "the one-time link can't be reused")
sid_only = cookie
check(web("/", sid_only)[0] == 200 and b"Admin dashboard" in web("/", sid_only)[2], "dashboard page loads once logged in")
page = open(os.path.join(ROOT, "dashboard.html"), encoding="utf-8").read()
check(page.count("innerHTML") == 1 and "textContent" in page and "http://" not in page.replace("http://www.w3.org/2000/svg", ""),
      "page builds content with textContent only and loads nothing external")

evil = mkuser("en")
db.upsert_user(evil, "<img src=x onerror=alert(1)>")
bad_views = []
params = {"order": f"%sid={oid_base}", "user": f"%sid={ur}"}
for view in dashboard.VIEWS:
    code, hdr, data = web(f"/api/{view}{params.get(view, '')}", sid_only)
    try:
        j = json.loads(data)
    except Exception:  # noqa: BLE001
        j = {"error": "not json"}
    if code != 200 or "error" in j:
        bad_views.append((view, code, j.get("error")))
check(not bad_views, f"all {len(dashboard.VIEWS)} dashboard pages return data -> {bad_views or 'ok'}")
j = json.loads(web("/api/summary", sid_only)[2])
rev = [c["value"] for c in j["cards"] if c["label"] == "Revenue (net)"][0]
check(rev == f"{db.get_stats()['revenue']} T", "dashboard revenue equals the bot's own /stats number")
j = json.loads(web("/api/users_all", sid_only)[2])
check(any("<img src=x" in str(r[0]) for r in j["table"]["rows"]), "hostile usernames are returned as plain data (the page renders them as text)")
j = json.loads(web("/api/roadmap", sid_only)[2])
check(len(j["roadmap"]) == 25 and sum(len(c["items"]) for c in j["roadmap"]) == 500, "roadmap notebook: 25 categories, 500 items")
code, hdr, data = web(f"/receipt/{oid_base}", sid_only)
check(code == 200 and hdr["Content-Type"] == "image/jpeg" and data.startswith(b"\xff\xd8"), "receipt image is served")
check(web("/receipt/99999999", sid_only)[0] == 404, "missing receipt -> 404")
check(web("/nope", sid_only)[0] == 404, "unknown page -> 404")

# Telegram Mini App login
def init_data(user_id, token=B.BOT_TOKEN, age=0, tamper=False):
    d = {"auth_date": str(int(time.time()) - age), "query_id": "AAH", "user": json.dumps({"id": user_id, "first_name": "A"})}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    d["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if tamper:
        d["user"] = json.dumps({"id": ADMIN + 1})
    return urllib.parse.urlencode(d)


V = dashboard.validate_init_data
check(V(init_data(ADMIN), B.BOT_TOKEN, ADMIN), "Mini App login: genuine admin accepted")
check(not V(init_data(ADMIN + 1), B.BOT_TOKEN, ADMIN), "Mini App login: another Telegram user rejected")
check(not V(init_data(ADMIN, tamper=True), B.BOT_TOKEN, ADMIN), "Mini App login: tampered data rejected")
check(not V(init_data(ADMIN, token="1:wrong"), B.BOT_TOKEN, ADMIN), "Mini App login: signed with a different token rejected")
check(not V(init_data(ADMIN, age=7200), B.BOT_TOKEN, ADMIN), "Mini App login: stale data rejected")
code, hdr, _ = web("/api/tgauth", method="POST", body=json.dumps({"initData": init_data(ADMIN)}), headers={"Content-Type": "application/json"})
check(code == 200 and "sid=" in hdr.get("Set-Cookie", ""), "Mini App endpoint issues a session for the admin")
code, _, _ = web("/api/tgauth", method="POST", body=json.dumps({"initData": init_data(ADMIN + 5)}), headers={"Content-Type": "application/json"})
check(code == 403, "…and refuses everyone else")
for _ in range(12):
    web("/login%st=bad")
check(web("/login%st=bad")[0] == 429, "repeated bad logins get locked out")
srv.shutdown()

# =================================================================== 11
section("10. Database migration from an older version, locales, keyboards")
old = os.path.join(TMP, "old.db")
oc = sqlite3.connect(old)
oc.executescript("""
CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, lang TEXT, balance INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, duration_days INTEGER, traffic_gb INTEGER, price INTEGER);
CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER, price INTEGER, status TEXT, created_at TEXT);
CREATE TABLE subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, order_id INTEGER, plan_name TEXT, config_text TEXT, start_date TEXT, end_date TEXT, active INTEGER DEFAULT 1);
INSERT INTO users VALUES (1,'old','fa',5000,'2025-01-01');
INSERT INTO orders (user_id,plan_id,price,status,created_at) VALUES (1,1,98000,'delivered','2025-01-02');
INSERT INTO subscriptions (user_id,order_id,plan_name,config_text,start_date,end_date) VALUES (1,1,'x','c','2025-01-02','2025-02-01');
""")
oc.commit(); oc.close()
keep = db.DB_PATH
db.DB_PATH = old
try:
    db.init_db(); db.init_db()  # twice: must be idempotent
    prof = db.get_user_profile(1)
    check(prof and prof["spent"] == 98000 and prof["orders_delivered"] == 1, "an old database upgrades in place and keeps its data")
    check(db.get_stats()["delivered_orders"] == 1, "stats work on the upgraded database")
finally:
    db.DB_PATH = keep

missing = [k for k, v in locales.TEXT.items() if not k.startswith("admin_") and not (("en" in v and "fa" in v) or set(v) == {"en"})]
check(not missing, f"every customer-facing text has English and Persian -> {missing or 'ok'}")
check(len(roadmap.parsed()) == 25 and all(len(i) == 20 for _, i in roadmap.parsed()), "roadmap has 25 sections of 20")
too_long = []
for s in B.bot.sent:
    for b in buttons(s):
        if b.callback_data and len(b.callback_data.encode()) > 64:
            too_long.append(b.callback_data)
check(not too_long, "all button payloads fit Telegram's 64-byte limit")
unhandled = set()
for s in B.bot.sent:
    for b in buttons(s):
        if b.callback_data and not any(h["func"](cb(1, b.callback_data)) for h in B.bot._c):
            unhandled.add(b.callback_data.split("_")[0])
check(not unhandled, f"every button the bot ever showed has a handler -> {sorted(unhandled) or 'ok'}")

# =================================================================== result
print("\n" + "=" * 60)
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
