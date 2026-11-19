"""
Admin-only web dashboard (read-only), opened from Telegram.

Security model
- Listens on 127.0.0.1 by default (not reachable from the internet).
- Nothing is visible without a session. A session is created by:
    1. the one-time link the bot sends you with /dashboard (valid 10 minutes,
       works once), or
    2. Telegram Mini App login: the page sends Telegram's signed initData and
       the server verifies the signature with the bot token and checks the
       user id is the admin's.
- Pure standard library, no external scripts/styles are loaded by the page.
"""
import hashlib
import hmac
import json
import os
import platform
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import extra_config as xc
import roadmap

TOKEN_TTL = 600
SESSION_TTL = 12 * 3600

_lock = threading.Lock()
_tokens = {}      # one-time login token -> expiry
_sessions = {}    # session id -> expiry
_failures = {}    # client ip -> [timestamps]
_STARTED = time.time()


# ------------------------------------------------------------------ auth
def issue_login_token():
    token = secrets.token_urlsafe(24)
    with _lock:
        _tokens[token] = time.time() + TOKEN_TTL
    return token


def _consume_token(token):
    with _lock:
        exp = _tokens.pop(token, None)
    return exp is not None and exp > time.time()


def _new_session():
    sid = secrets.token_urlsafe(32)
    with _lock:
        _sessions[sid] = time.time() + SESSION_TTL
    return sid


def _valid_session(sid):
    if not sid:
        return False
    with _lock:
        exp = _sessions.get(sid)
        if exp is None:
            return False
        if exp < time.time():
            _sessions.pop(sid, None)
            return False
    return True


def _too_many_failures(ip, record=False, limit=10, window=60):
    now = time.time()
    with _lock:
        hits = [t for t in _failures.get(ip, []) if now - t < window]
        if record:
            hits.append(now)
        _failures[ip] = hits
        return len(hits) >= limit


def validate_init_data(init_data, bot_token, admin_id, max_age=3600, now=None):
    """Verifies Telegram Mini App initData (HMAC per Telegram's docs) and that
    it belongs to the admin."""
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data = dict(pairs)
        their_hash = data.pop("hash", "")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        mine = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not their_hash or not hmac.compare_digest(mine, their_hash):
            return False
        now = now if now is not None else time.time()
        if now - int(data.get("auth_date", "0")) > max_age:
            return False
        return int(json.loads(data["user"])["id"]) == int(admin_id)
    except Exception:
        return False


# ------------------------------------------------------------------ data helpers
def _q(sql, *args):
    conn = db.get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _one(sql, *args):
    rows = _q(sql, *args)
    return rows[0] if rows else {}


def _d(iso):
    return iso.replace("T", " ")[:16] if iso else "-"


def _order_cell(oid):
    return {"text": f"#{oid}", "go": {"view": "order", "params": {"id": oid}}}


def _user_cell(uid, username=None):
    return {"text": f"@{username}" if username else str(uid), "go": {"view": "user", "params": {"id": uid}}}


def _table(title, columns, rows, note=None):
    return {"title": title, "table": {"columns": columns, "rows": rows}, "note": note}


def _last_days(n):
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


_NET = "(price - COALESCE(refunded_amount,0))"
_ORDER_COLS = ["Order", "Customer", "Type", "Status", "Price", "Created", "Receipt"]


def _orders_table(title, where="1=1", args=(), limit=300, note=None):
    rows = _q(
        "SELECT o.id, o.user_id, o.kind, o.status, o.price, o.created_at, o.receipt_file_id, u.username "
        "FROM orders o LEFT JOIN users u ON u.user_id=o.user_id "
        f"WHERE {where} ORDER BY o.id DESC LIMIT {int(limit)}", *args)
    out = [[_order_cell(r["id"]), _user_cell(r["user_id"], r["username"]), r["kind"], r["status"], r["price"],
            _d(r["created_at"]), ({"text": "🖼 view", "img": f"/receipt/{r['id']}"} if r["receipt_file_id"] else "-")]
           for r in rows]
    return _table(title, _ORDER_COLS, out, note)


# ------------------------------------------------------------------ views
def v_summary(p):
    s = db.get_stats()
    today = datetime.now(timezone.utc).date().isoformat()
    week = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rev_today = _one(f"SELECT COALESCE(SUM{_NET},0) r FROM orders WHERE status IN ('delivered','refunded') "
                     "AND substr(delivered_at,1,10)=?", today)["r"]
    rev_week = _one(f"SELECT COALESCE(SUM{_NET},0) r FROM orders WHERE status IN ('delivered','refunded') "
                    "AND delivered_at>=?", week)["r"]
    return {"title": "Summary", "cards": [
        {"label": "Customers", "value": s["users"]},
        {"label": "Orders", "value": s["total_orders"]},
        {"label": "Delivered", "value": s["delivered_orders"]},
        {"label": "Waiting on you", "value": s["pending_orders"]},
        {"label": "Revenue (net)", "value": f"{s['revenue']} T"},
        {"label": "Revenue today", "value": f"{rev_today} T"},
        {"label": "Revenue 7 days", "value": f"{rev_week} T"},
        {"label": "Refunded", "value": f"{s['refunded_total']} T"},
        {"label": "Active subscriptions", "value": s["active_subscriptions"]},
        {"label": "Average rating", "value": s["avg_rating"] if s["avg_rating"] is not None else "-"},
    ]}


def v_revenue_daily(p):
    days = _last_days(30)
    rows = _q(f"SELECT substr(delivered_at,1,10) d, SUM{_NET} r FROM orders "
              "WHERE status IN ('delivered','refunded') AND delivered_at>=? GROUP BY d", days[0])
    m = {r["d"]: r["r"] for r in rows}
    return {"title": "Revenue — last 30 days (Toman, UTC days)",
            "chart": {"labels": [d[5:] for d in days], "values": [m.get(d, 0) for d in days]}}


def v_signups(p):
    days = _last_days(30)
    rows = _q("SELECT substr(created_at,1,10) d, COUNT(*) n FROM users WHERE created_at>=? GROUP BY d", days[0])
    m = {r["d"]: r["n"] for r in rows}
    return {"title": "New customers — last 30 days",
            "chart": {"labels": [d[5:] for d in days], "values": [m.get(d, 0) for d in days]}}


def v_orders_status(p):
    rows = _q("SELECT status, COUNT(*) n FROM orders GROUP BY status ORDER BY n DESC")
    return {"title": "Orders by status",
            "chart": {"labels": [r["status"] for r in rows], "values": [r["n"] for r in rows]},
            "table": {"columns": ["Status", "Orders"], "rows": [[r["status"], r["n"]] for r in rows]}}


def v_orders_all(p):
    q = (p.get("q") or "").strip()
    if q.lstrip("#").isdigit():
        return _orders_table(f"Order #{q.lstrip('#')}", "o.id=?", (int(q.lstrip("#")),))
    return _orders_table("All orders (latest 300)")


def v_orders_pending(p):
    return _orders_table("Waiting on you", "o.status='awaiting_admin'")


def v_orders_unpaid(p):
    return _orders_table("Unpaid invoices (waiting for the customer's receipt)", "o.status='awaiting_receipt'")


def v_orders_delivered(p):
    return _orders_table("Delivered", "o.status='delivered'")


def v_orders_declined(p):
    return _orders_table("Declined / expired", "o.status IN ('declined','expired')")


def v_orders_renewals(p):
    return _orders_table("Renewals / data top-ups", "o.kind='renewal'")


def v_orders_refunded(p):
    return _orders_table("Refunded orders", "COALESCE(o.refunded_amount,0)>0")


def v_order(p):
    c = db.get_order_card(int(p.get("id", 0)))
    if not c:
        return {"title": "Order not found"}
    rows = [["Order", f"#{c['id']}"], ["Type", c["kind"]], ["Status", c["status"]],
            ["Customer", _user_cell(c["user_id"], c["username"])], ["Price", f"{c['price']} Toman"],
            ["Refunded", c["refunded_amount"] or 0], ["Subscription name", c.get("chosen_username") or c.get("sub_name") or "-"],
            ["Extra time / data", f"{(c['extra_days'] or 0)} days / {(c['extra_gb'] or 0)} GB" if c["kind"] == "renewal" else "-"],
            ["Created (UTC)", _d(c["created_at"])], ["Invoice valid until", _d(c["expires_at"])],
            ["Receipt sent", _d(c["receipt_at"])], ["Delivered", _d(c["delivered_at"])],
            ["Rating", c["rating"] or "-"]]
    if c["receipt_file_id"]:
        rows.append(["Receipt", {"text": "🖼 open receipt", "img": f"/receipt/{c['id']}"}])
    out = {"title": f"Order #{c['id']}", "table": {"columns": ["Field", "Value"], "rows": rows}}
    if c["refunds"]:
        out["table2"] = {"columns": ["Refund", "When", "Reason"],
                         "rows": [[r["amount"], _d(r["created_at"]), r["reason"]] for r in c["refunds"]]}
    return out


_USER_COLS = ["Customer", "Orders", "Spent", "Active subs", "Joined"]


def _users_table(title, where="1=1", order="u.created_at DESC", limit=300, note=None):
    rows = _q(
        "SELECT u.user_id, u.username, u.created_at, "
        "(SELECT COUNT(*) FROM orders o WHERE o.user_id=u.user_id) orders, "
        "(SELECT COALESCE(SUM(price - COALESCE(refunded_amount,0)),0) FROM orders o WHERE o.user_id=u.user_id "
        "  AND o.status IN ('delivered','refunded')) spent, "
        "(SELECT COUNT(*) FROM subscriptions s WHERE s.user_id=u.user_id AND s.active=1) subs "
        f"FROM users u WHERE {where} ORDER BY {order} LIMIT {int(limit)}")
    return _table(title, _USER_COLS, [[_user_cell(r["user_id"], r["username"]), r["orders"], r["spent"],
                                       r["subs"], _d(r["created_at"])] for r in rows], note)


def v_users_all(p):
    return _users_table("All customers (latest 300)")


def v_users_new(p):
    return _users_table("Newest customers", limit=50)


def v_users_top(p):
    return _users_table("Top spenders", order="spent DESC", where="1=1", limit=50)


def v_users_flagged(p):
    return _users_table("Flagged customers", "u.flagged=1")


def v_users_banned(p):
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    return _users_table("Currently banned", f"u.user_id IN (SELECT user_id FROM bans WHERE active=1 AND until>'{now}')")


def v_users_inactive(p):
    return _users_table("Never bought anything",
                        "NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id=u.user_id AND o.status IN ('delivered','refunded'))")


def v_user(p):
    prof = db.get_user_profile(int(p.get("id", 0)))
    if not prof:
        return {"title": "Customer not found"}
    ban = prof["active_ban"]
    rows = [["Telegram ID", prof["user_id"]], ["Username", f"@{prof['username']}" if prof["username"] else "-"],
            ["Language", prof["lang"] or "-"], ["Joined (UTC)", _d(prof["created_at"])],
            ["Orders", f"{prof['orders_total']} ({prof['orders_delivered']} delivered, {prof['orders_declined']} declined, "
                       f"{prof['orders_expired']} expired, {prof['orders_refunded']} refunded)"],
            ["Spent (net)", f"{prof['spent']} Toman"], ["Times banned", prof["ban_count"]],
            ["Banned now", f"until {_d(ban['until'])} — {ban['reason']}" if ban else "no"],
            ["Flagged", prof["flag_reason"] if prof["flagged"] else "no"],
            ["Rating given (avg)", round(prof["avg_rating"], 1) if prof["avg_rating"] else "-"]]
    out = {"title": f"Customer {prof['user_id']}", "table": {"columns": ["Field", "Value"], "rows": rows}}
    orders = _q("SELECT id, kind, status, price, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50", prof["user_id"])
    out["table2"] = {"columns": ["Order", "Type", "Status", "Price", "Created"],
                     "rows": [[_order_cell(o["id"]), o["kind"], o["status"], o["price"], _d(o["created_at"])] for o in orders]}
    return out


_SUB_COLS = ["Sub", "Customer", "Name", "Ends (UTC)", "Data left", "Source"]


def _subs_table(title, where="1=1", args=(), note=None, order="s.end_date"):
    rows = _q("SELECT s.id, s.user_id, s.sub_name, s.end_date, s.total_gb, s.remaining_gb, s.manual, s.order_id, u.username "
              "FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id "
              f"WHERE {where} ORDER BY {order} LIMIT 300", *args)
    out = []
    for r in rows:
        left = "-"
        if r["remaining_gb"] is not None:
            left = f"{r['remaining_gb']:g}" + (f" / {r['total_gb']:g}" if r["total_gb"] is not None else "") + " GB"
        out.append([f"#{r['id']}", _user_cell(r["user_id"], r["username"]), r["sub_name"] or "-", _d(r["end_date"]), left,
                    "manual" if r["manual"] else (_order_cell(r["order_id"]) if r["order_id"] else "-")])
    return _table(title, _SUB_COLS, out, note)


def _now_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def v_subs_active(p):
    return _subs_table("Active subscriptions", "s.active=1 AND s.end_date>?", (_now_iso(),))


def v_subs_expiring(p):
    soon = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)).isoformat()
    return _subs_table("Expiring in the next 7 days", "s.active=1 AND s.end_date>? AND s.end_date<=?", (_now_iso(), soon))


def v_subs_expired(p):
    return _subs_table("Expired", "s.end_date<=?", (_now_iso(),), order="s.end_date DESC")


def v_subs_manual(p):
    return _subs_table("Added by hand", "s.manual=1")


def v_subs_lowdata(p):
    return _subs_table("Low data (20% or less left, or under 5 GB)",
                       "s.active=1 AND s.remaining_gb IS NOT NULL AND (s.remaining_gb<5 OR "
                       "(s.total_gb>0 AND s.remaining_gb*1.0/s.total_gb<=0.2))")


def v_fin_month(p):
    rows = _q(f"SELECT substr(delivered_at,1,7) m, COUNT(*) n, SUM{_NET} r FROM orders "
              "WHERE status IN ('delivered','refunded') AND delivered_at IS NOT NULL GROUP BY m ORDER BY m DESC LIMIT 12")
    rows.reverse()
    return {"title": "Revenue by month (Toman)",
            "chart": {"labels": [r["m"] for r in rows], "values": [r["r"] for r in rows]},
            "table": {"columns": ["Month", "Orders", "Revenue"], "rows": [[r["m"], r["n"], r["r"]] for r in rows]}}


def v_fin_plan(p):
    rows = _q("SELECT p.traffic_gb tg, p.duration_days dd, COUNT(*) n, SUM(o.price - COALESCE(o.refunded_amount,0)) r "
              "FROM orders o JOIN plans p ON p.id=o.plan_id WHERE o.status IN ('delivered','refunded') "
              "GROUP BY p.traffic_gb, p.duration_days ORDER BY r DESC")
    ren = _one(f"SELECT COUNT(*) n, COALESCE(SUM{_NET},0) r FROM orders WHERE kind='renewal' AND status IN ('delivered','refunded')")
    out = [[f"{r['tg']} GB / {r['dd']} days", r["n"], r["r"]] for r in rows]
    out.append(["Renewals & top-ups", ren["n"], ren["r"]])
    return _table("Revenue by plan", ["Plan", "Orders", "Revenue"], out)


def v_best_plans(p):
    rows = _q("SELECT p.traffic_gb tg, p.duration_days dd, p.price pr, COUNT(o.id) n FROM plans p "
              "LEFT JOIN orders o ON o.plan_id=p.id AND o.status IN ('delivered','refunded') WHERE p.active=1 "
              "GROUP BY p.id ORDER BY n DESC")
    return _table("Plans by number of sales", ["Plan", "List price", "Sold"],
                  [[f"{r['tg']} GB / {r['dd']} days", r["pr"], r["n"]] for r in rows])


def v_fin_refunds(p):
    rows = _q("SELECT r.order_id, r.amount, r.reason, r.created_at FROM refunds r ORDER BY r.id DESC LIMIT 300")
    return _table("Refund log", ["Order", "Amount", "When", "Reason"],
                  [[_order_cell(r["order_id"]), r["amount"], _d(r["created_at"]), r["reason"]] for r in rows])


def v_fin_fees(p):
    import config
    pct = config.ORDER_FEE_PERCENT
    row = _one(f"SELECT COALESCE(SUM{_NET},0) r FROM orders WHERE status IN ('delivered','refunded')")
    fee = round(row["r"] * pct / (100 + pct))
    return {"title": "Gateway fees collected (estimate)",
            "cards": [{"label": f"Fee rate", "value": f"{pct}%"}, {"label": "Net revenue", "value": f"{row['r']} T"},
                      {"label": "≈ fees inside revenue", "value": f"{fee} T"}],
            "note": "Estimate: assumes every order paid the current fee rate."}


def v_discounts(p):
    rows = _q("SELECT code, percent, active, created_at FROM discounts ORDER BY active DESC, code")
    return _table("Discount codes", ["Code", "Percent off", "Active", "Created"],
                  [[r["code"], f"{r['percent']}%", "yes" if r["active"] else "no", _d(r["created_at"])] for r in rows])


def v_ratings(p):
    rows = _q("SELECT rating, COUNT(*) n FROM orders WHERE rating IS NOT NULL GROUP BY rating ORDER BY rating")
    m = {r["rating"]: r["n"] for r in rows}
    return {"title": "Ratings",
            "chart": {"labels": [f"{i}⭐" for i in range(1, 6)], "values": [m.get(i, 0) for i in range(1, 6)]}}


def v_ratings_low(p):
    return _orders_table("Low ratings (1–2 stars)", "o.rating IS NOT NULL AND o.rating<=2")


def v_plans(p):
    rows = _q("SELECT traffic_gb, duration_days, price, active FROM plans ORDER BY duration_days, traffic_gb")
    return _table("Plans & prices (before the gateway fee)", ["GB", "Days", "Price", "Active"],
                  [[r["traffic_gb"], r["duration_days"], r["price"], "yes" if r["active"] else "no"] for r in rows])


def v_settings(p):
    import config
    pm = db.get_setting("renew_per_month", xc.RENEW_PRICE_PER_MONTH)
    pg = db.get_setting("renew_per_gb", xc.RENEW_PRICE_PER_GB)
    rows = [["Working hours restriction", "ON" if db.get_setting("hours_enabled", "1") == "1" else "OFF"],
            ["Opens at", f"{config.OPEN_HOUR}:00 ({config.TIMEZONE})"], ["Gateway fee", f"{config.ORDER_FEE_PERCENT}%"],
            ["Invoice valid for", f"{xc.ORDER_EXPIRY_MINUTES} minutes"],
            ["Update price per month / per GB", f"{pm} / {pg} Toman"],
            ["Expiry reminder", f"{xc.REMINDER_DAYS} days before"],
            ["Rate limit", f"{xc.RATE_LIMIT_MAX} actions / {xc.RATE_LIMIT_WINDOW}s; {xc.FLOOD_STRIKES} strikes = {xc.FLOOD_BAN_MINUTES} min ban"],
            ["Flag after", f"{xc.FLAG_DECLINE_THRESHOLD} declines in {xc.FLAG_WINDOW_DAYS} days"],
            ["Daily backup", f"{'ON' if xc.BACKUP_ENABLED else 'OFF'} at {xc.BACKUP_HOUR}:00; last: {db.get_setting('last_backup_date', 'never')}"]]
    return _table("Settings (change them with the bot's commands or .env)", ["Setting", "Value"], rows)


def v_health(p):
    size = None
    counts = {t: _one(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("users", "orders", "subscriptions", "refunds", "bans")}
    rows = [["Database", "Supabase PostgreSQL"], ["Python", platform.python_version()],
            ["Dashboard uptime", f"{int(time.time() - _STARTED) // 60} minutes"]] + [[k, v] for k, v in counts.items()]
    return _table("Health", ["Item", "Value"], rows)


def v_roadmap(p):
    return {"title": f"Needs & ideas — {roadmap.built_count()} of {roadmap.total_count()} built",
            "roadmap": [{"category": c, "items": [{"text": t, "built": b} for t, b in items]}
                        for c, items in roadmap.parsed()]}


VIEWS = {
    "summary": v_summary, "revenue_daily": v_revenue_daily, "orders_status": v_orders_status, "signups": v_signups,
    "orders_all": v_orders_all, "orders_pending": v_orders_pending, "orders_unpaid": v_orders_unpaid,
    "orders_delivered": v_orders_delivered, "orders_declined": v_orders_declined,
    "orders_renewals": v_orders_renewals, "orders_refunded": v_orders_refunded, "order": v_order,
    "users_all": v_users_all, "users_new": v_users_new, "users_top": v_users_top, "users_flagged": v_users_flagged,
    "users_banned": v_users_banned, "users_inactive": v_users_inactive, "user": v_user,
    "subs_active": v_subs_active, "subs_expiring": v_subs_expiring, "subs_expired": v_subs_expired,
    "subs_manual": v_subs_manual, "subs_lowdata": v_subs_lowdata,
    "fin_month": v_fin_month, "fin_plan": v_fin_plan, "fin_refunds": v_fin_refunds, "fin_fees": v_fin_fees,
    "discounts": v_discounts, "best_plans": v_best_plans, "ratings": v_ratings, "ratings_low": v_ratings_low,
    "plans": v_plans, "settings": v_settings, "health": v_health, "roadmap": v_roadmap,
}

MENU = [
    ["📊 Overview", [["summary", "Summary"], ["revenue_daily", "Revenue — 30 days"], ["orders_status", "Orders by status"], ["signups", "New customers"]]],
    ["🧾 Orders", [["orders_all", "All orders"], ["orders_pending", "Waiting on you"], ["orders_unpaid", "Unpaid invoices"], ["orders_delivered", "Delivered"], ["orders_declined", "Declined / expired"], ["orders_renewals", "Renewals"], ["orders_refunded", "Refunded"]]],
    ["👥 Customers", [["users_all", "All customers"], ["users_new", "Newest"], ["users_top", "Top spenders"], ["users_flagged", "Flagged"], ["users_banned", "Banned"], ["users_inactive", "Never bought"]]],
    ["📦 Subscriptions", [["subs_active", "Active"], ["subs_expiring", "Expiring in 7 days"], ["subs_expired", "Expired"], ["subs_manual", "Added by hand"], ["subs_lowdata", "Low data"]]],
    ["💰 Finance", [["fin_month", "By month"], ["fin_plan", "By plan"], ["fin_refunds", "Refund log"], ["fin_fees", "Gateway fees"]]],
    ["🎟 Marketing", [["discounts", "Discount codes"], ["best_plans", "Plans by sales"]]],
    ["⭐ Feedback", [["ratings", "Ratings"], ["ratings_low", "Low ratings"]]],
    ["⚙️ System", [["plans", "Plans & prices"], ["settings", "Settings"], ["health", "Health"]]],
    ["🗒 Roadmap", [["roadmap", "Needs & ideas"]]],
]


# ------------------------------------------------------------------ pages
PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html"), encoding="utf-8").read()

LOCKED = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Locked</title><body style="font-family:system-ui;max-width:30rem;margin:4rem auto;padding:0 1rem">
<h2>🔒 Admin only</h2><p>Open this dashboard from Telegram: send <b>/dashboard</b> to the bot.</p></body>"""

WEBAPP = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Dashboard</title><body style="font-family:system-ui;max-width:30rem;margin:4rem auto;padding:0 1rem">
<p id=m>Signing in…</p><script>
(function(){var h=location.hash.slice(1),p=new URLSearchParams(h),d=p.get('tgWebAppData');
if(!d){document.getElementById('m').textContent='Open this page from the bot (/dashboard).';return}
fetch('/api/tgauth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({initData:d})})
.then(function(r){if(r.ok){location.replace('/')}else{document.getElementById('m').textContent='Not allowed.'}})})();
</script></body>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "AdminDash"
    sys_version = ""

    def log_message(self, *a):  # keep the terminal quiet
        pass

    # -- helpers
    def _ip(self):
        return self.client_address[0]

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200, extra=()):
        self._send(code, json.dumps(obj, default=str), "application/json; charset=utf-8", extra)

    def _sid(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sid":
                return v
        return None

    def _authed(self):
        return _valid_session(self._sid())

    def _cookie(self, sid):
        secure = self.headers.get("X-Forwarded-Proto", "") == "https"
        flags = "; SameSite=None; Secure" if secure else "; SameSite=Lax"
        return ("Set-Cookie", f"sid={sid}; HttpOnly; Path=/; Max-Age={SESSION_TTL}{flags}")

    # -- routes
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        path = url.path

        if path == "/login":
            if _too_many_failures(self._ip()):
                return self._send(429, "Too many attempts.")
            if _consume_token(q.get("t", "")):
                return self._send(302, "", extra=[("Location", "/"), self._cookie(_new_session())])
            _too_many_failures(self._ip(), record=True)
            return self._send(403, LOCKED)
        if path == "/webapp":
            return self._send(200, WEBAPP)
        if path == "/":
            return self._send(200, PAGE if self._authed() else LOCKED, extra=[] if self._authed() else [])
        if not self._authed():
            return self._json({"error": "locked"}, 401)

        if path == "/api/menu":
            return self._json(MENU)
        if path.startswith("/api/"):
            fn = VIEWS.get(path[5:])
            if not fn:
                return self._json({"error": "unknown view"}, 404)
            try:
                return self._json(fn(q))
            except Exception as e:  # never leak a stack trace
                return self._json({"error": f"{type(e).__name__}"}, 500)
        if path.startswith("/receipt/"):
            try:
                oid = int(path.rsplit("/", 1)[1])
                img = self.server.receipt_fetcher(oid)
            except Exception:
                img = None
            if not img:
                return self._send(404, "No receipt.")
            return self._send(200, img, "image/jpeg")
        return self._send(404, "Not found.")

    def do_POST(self):
        if self.path != "/api/tgauth":
            return self._send(404, "Not found.")
        if _too_many_failures(self._ip()):
            return self._json({"error": "slow down"}, 429)
        try:
            n = min(int(self.headers.get("Content-Length", "0")), 8192)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        if validate_init_data(body.get("initData", ""), self.server.bot_token, self.server.admin_id):
            return self._json({"ok": True}, extra=[self._cookie(_new_session())])
        _too_many_failures(self._ip(), record=True)
        return self._json({"error": "not allowed"}, 403)


def start_server(host, port, bot_token, admin_id, receipt_fetcher):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.bot_token, srv.admin_id, srv.receipt_fetcher = bot_token, admin_id, receipt_fetcher
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
