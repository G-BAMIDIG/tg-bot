import sqlite3
from datetime import datetime, timedelta, timezone
from config import DB_PATH
import crypto


def _now():
    """Naive UTC 'now' (same convention as the rest of this file)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            lang TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            duration_days INTEGER,
            traffic_gb INTEGER,
            price INTEGER,
            active INTEGER DEFAULT 1,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_id INTEGER,
            price INTEGER,
            receipt_file_id TEXT,
            status TEXT DEFAULT 'awaiting_receipt',
            created_at TEXT,
            delivered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id INTEGER,
            plan_name TEXT,
            config_text TEXT,
            start_date TEXT,
            end_date TEXT,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            banned_at TEXT,
            until TEXT,
            active INTEGER DEFAULT 1,
            lifted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS refunds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            amount INTEGER,
            reason TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS discounts (
            code TEXT PRIMARY KEY,
            percent INTEGER,
            active INTEGER DEFAULT 1,
            created_at TEXT
        );
        """
    )
    conn.commit()

    # Migration safety net: add any columns that don't exist yet on an
    # already-created table, so old vpnbot.db files don't break on updates.
    # NOTE: this deliberately does NOT drop old columns/tables from earlier
    # versions (e.g. users.balance, wallet_topups) - they're just left
    # unused rather than risking a destructive migration.
    required_columns = {
        "plans": [
            ("duration_days", "INTEGER"),
            ("traffic_gb", "INTEGER"),
            ("price", "INTEGER"),
            ("active", "INTEGER DEFAULT 1"),
            ("updated_at", "TEXT"),
        ],
        "orders": [
            ("status", "TEXT DEFAULT 'awaiting_receipt'"),
            ("receipt_file_id", "TEXT"),
            ("chosen_username", "TEXT"),
            ("kind", "TEXT DEFAULT 'new'"),
            ("renew_sub_id", "INTEGER"),
            ("extra_days", "INTEGER DEFAULT 0"),
            ("extra_gb", "INTEGER DEFAULT 0"),
            ("expires_at", "TEXT"),
            ("receipt_at", "TEXT"),
            ("rating", "INTEGER"),
            ("refunded_amount", "INTEGER DEFAULT 0"),
            ("invoice_chat_id", "INTEGER"),
            ("invoice_msg_id", "INTEGER"),
            ("declined_at", "TEXT"),
        ],
        "subscriptions": [
            ("sub_name", "TEXT"),
            ("extra_gb", "INTEGER DEFAULT 0"),
            ("total_gb", "REAL"),
            ("remaining_gb", "REAL"),
            ("remaining_updated_at", "TEXT"),
            ("reminded", "INTEGER DEFAULT 0"),
            ("manual", "INTEGER DEFAULT 0"),
        ],
        "users": [
            ("flagged", "INTEGER DEFAULT 0"),
            ("flag_reason", "TEXT"),
        ],
    }
    for table, columns in required_columns.items():
        existing = {row["name"] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_def in columns:
            if col_name not in existing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
    conn.commit()
    conn.close()


# ---------- users ----------
def upsert_user(user_id, username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (user_id, username, created_at) VALUES (?,?,?)",
            (user_id, username, datetime.utcnow().isoformat()),
        )
    else:
        c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
    conn.commit()
    conn.close()


def set_lang(user_id, lang):
    conn = get_conn()
    conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row


def get_all_user_ids():
    conn = get_conn()
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_user_by_username(username):
    """Case-insensitive lookup by the username we last saw for them. Only
    finds people who have started this bot before - we have no way to
    resolve an arbitrary @username otherwise."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    conn.close()
    return row


# ---------- plans ----------
# Uniquely identified by (duration_days, traffic_gb), NOT a free-text name.
def upsert_plan(duration_days, traffic_gb, price):
    conn = get_conn()
    c = conn.cursor()
    existing = c.execute(
        "SELECT id FROM plans WHERE duration_days=? AND traffic_gb=?",
        (duration_days, traffic_gb),
    ).fetchone()
    if existing:
        c.execute(
            "UPDATE plans SET price=?, active=1, updated_at=? WHERE id=?",
            (price, datetime.utcnow().isoformat(), existing["id"]),
        )
    else:
        c.execute(
            "INSERT INTO plans (duration_days, traffic_gb, price, updated_at) VALUES (?,?,?,?)",
            (duration_days, traffic_gb, price, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def get_active_plans(duration_days=None):
    conn = get_conn()
    if duration_days is not None:
        rows = conn.execute(
            "SELECT * FROM plans WHERE active=1 AND duration_days=? ORDER BY traffic_gb ASC",
            (duration_days,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM plans WHERE active=1 ORDER BY duration_days ASC, traffic_gb ASC"
        ).fetchall()
    conn.close()
    return rows


def get_plan(plan_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    conn.close()
    return row


def deactivate_missing_plans(seen_keys):
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute("SELECT id, duration_days, traffic_gb FROM plans WHERE active=1").fetchall()
    for row in rows:
        if (row["duration_days"], row["traffic_gb"]) not in seen_keys:
            c.execute("UPDATE plans SET active=0 WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()


# ---------- orders (one order = one subscription purchase, one receipt) ----------
def create_order(user_id, plan_id, price, chosen_username=None, expires_at=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, plan_id, price, status, chosen_username, created_at, expires_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, plan_id, price, "awaiting_receipt", chosen_username,
         _now().isoformat(), expires_at),
    )
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id


def get_order(order_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return row


def set_order_receipt(order_id, file_id):
    conn = get_conn()
    conn.execute(
        "UPDATE orders SET receipt_file_id=?, status='awaiting_admin', receipt_at=? WHERE id=?",
        (file_id, _now().isoformat(), order_id),
    )
    conn.commit()
    conn.close()


def mark_order_delivered(order_id):
    conn = get_conn()
    conn.execute(
        "UPDATE orders SET status='delivered', delivered_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), order_id),
    )
    conn.commit()
    conn.close()


def decline_order(order_id):
    """Marks a pending order as declined so it no longer appears in /pending.
    Soft status change (keeps the row for history/stats); does not delete."""
    conn = get_conn()
    conn.execute(
        "UPDATE orders SET status='declined', declined_at=? WHERE id=?",
        (_now().isoformat(), order_id),
    )
    conn.commit()
    conn.close()


def get_pending_orders():
    """Orders where the receipt is in but nobody's delivered the config yet."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT o.id AS order_id, o.price, o.receipt_file_id, o.created_at,
               o.kind, o.extra_days, o.extra_gb, o.chosen_username,
               u.user_id, u.username,
               p.duration_days, p.traffic_gb
        FROM orders o
        JOIN users u ON u.user_id = o.user_id
        LEFT JOIN plans p ON p.id = o.plan_id
        WHERE o.status = 'awaiting_admin'
        ORDER BY o.created_at ASC
        """
    ).fetchall()
    conn.close()
    return rows


# ---------- subscriptions ----------
def create_subscription(user_id, order_id, plan_name, sub_name, config_text, duration_days, total_gb=None):
    start = datetime.utcnow()
    end = start + timedelta(days=duration_days)
    conn = get_conn()
    conn.execute(
        "INSERT INTO subscriptions (user_id, order_id, plan_name, sub_name, config_text, start_date, "
        "end_date, total_gb) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, order_id, plan_name, sub_name, crypto.encrypt_text(config_text), start.isoformat(),
         end.isoformat(), total_gb),
    )
    conn.commit()
    conn.close()
    return end


def get_subscription(sub_id):
    """Single subscription, config_text DECRYPTED - used by the 'Get URL' button."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["config_text"] = crypto.decrypt_text(data["config_text"])
    return data


def get_subscription_by_order(order_id):
    """Returns the subscription with config_text DECRYPTED, for admin lookups."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE order_id=?", (order_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["config_text"] = crypto.decrypt_text(data["config_text"])
    return data


def get_active_subscriptions(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? AND active=1 ORDER BY end_date ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


# ---------- settings (persisted, so admin toggles survive a restart) ----------
def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


# ---------- stats ----------
def get_stats():
    conn = get_conn()
    c = conn.cursor()
    users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    total_orders = c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
    delivered = c.execute(
        "SELECT COUNT(*) n FROM orders WHERE status='delivered'"
    ).fetchone()["n"]
    # net revenue = what delivered/refunded orders paid minus what was refunded
    revenue = c.execute(
        "SELECT COALESCE(SUM(price - COALESCE(refunded_amount,0)),0) r FROM orders "
        "WHERE status IN ('delivered','refunded')"
    ).fetchone()["r"]
    refunded = c.execute(
        "SELECT COALESCE(SUM(refunded_amount),0) r FROM orders"
    ).fetchone()["r"]
    pending = c.execute(
        "SELECT COUNT(*) n FROM orders WHERE status='awaiting_admin'"
    ).fetchone()["n"]
    active_subs = c.execute(
        "SELECT COUNT(*) n FROM subscriptions WHERE active=1"
    ).fetchone()["n"]
    rating = c.execute(
        "SELECT AVG(rating) a, COUNT(rating) n FROM orders WHERE rating IS NOT NULL"
    ).fetchone()
    conn.close()
    return {
        "users": users,
        "total_orders": total_orders,
        "delivered_orders": delivered,
        "revenue": revenue,
        "refunded_total": refunded,
        "pending_orders": pending,
        "active_subscriptions": active_subs,
        "avg_rating": round(rating["a"], 2) if rating["a"] is not None else None,
        "rating_count": rating["n"],
    }


# ---------- bans ----------
def create_ban(user_id, reason, until_iso):
    conn = get_conn()
    c = conn.cursor()
    # only one active ban per person at a time
    c.execute("UPDATE bans SET active=0 WHERE user_id=? AND active=1", (user_id,))
    c.execute(
        "INSERT INTO bans (user_id, reason, banned_at, until, active) VALUES (?,?,?,?,1)",
        (user_id, reason, datetime.utcnow().isoformat(), until_iso),
    )
    ban_id = c.lastrowid
    conn.commit()
    conn.close()
    return ban_id


def get_active_ban(user_id):
    """Returns the active ban row, or None. Lazily expires (deactivates) a
    ban whose time has already passed instead of requiring a background job."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT * FROM bans WHERE user_id=? AND active=1 ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    if datetime.fromisoformat(row["until"]) <= datetime.utcnow():
        c.execute("UPDATE bans SET active=0 WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        return None
    conn.close()
    return row


def get_ban_count(user_id):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) n FROM bans WHERE user_id=?", (user_id,)).fetchone()["n"]
    conn.close()
    return n


def unban_user(user_id):
    """Returns True if an active ban was actually lifted, False if the
    person wasn't banned in the first place."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT id FROM bans WHERE user_id=? AND active=1 ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    c.execute(
        "UPDATE bans SET active=0, lifted_at=? WHERE id=?", (datetime.utcnow().isoformat(), row["id"])
    )
    conn.commit()
    conn.close()
    return True


# ---------- discount codes ----------
def create_discount(code, percent):
    """Upserts by code (case-insensitive - always stored/compared uppercased)."""
    code = code.strip().upper()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO discounts (code, percent, active, created_at) VALUES (?, ?, 1, ?) "
        "ON CONFLICT(code) DO UPDATE SET percent=excluded.percent, active=1",
        (code, percent, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_discount(code):
    """Returns the active discount row for this code, or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM discounts WHERE code=? AND active=1", (code.strip().upper(),)
    ).fetchone()
    conn.close()
    return row


def get_active_discounts():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM discounts WHERE active=1 ORDER BY code ASC").fetchall()
    conn.close()
    return rows


def deactivate_discount(code):
    """Returns True if a code was actually deactivated, False if it didn't exist/was already off."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT code FROM discounts WHERE code=? AND active=1", (code.strip().upper(),)
    ).fetchone()
    if not row:
        conn.close()
        return False
    c.execute("UPDATE discounts SET active=0 WHERE code=?", (row["code"],))
    conn.commit()
    conn.close()
    return True


# ---------- invoice timer ----------
def set_invoice_message(order_id, chat_id, msg_id):
    conn = get_conn()
    conn.execute(
        "UPDATE orders SET invoice_chat_id=?, invoice_msg_id=? WHERE id=?",
        (chat_id, msg_id, order_id),
    )
    conn.commit()
    conn.close()


def get_expired_unpaid_orders(now_iso=None):
    """Orders still waiting for a receipt whose invoice time has run out."""
    now_iso = now_iso or _now().isoformat()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM orders WHERE status='awaiting_receipt' "
        "AND expires_at IS NOT NULL AND expires_at <= ?",
        (now_iso,),
    ).fetchall()
    conn.close()
    return rows


def mark_order_expired(order_id):
    """Only flips orders that are still waiting for a receipt. Returns True
    if it actually expired one."""
    conn = get_conn()
    c = conn.execute(
        "UPDATE orders SET status='expired' WHERE id=? AND status='awaiting_receipt'",
        (order_id,),
    )
    conn.commit()
    changed = c.rowcount > 0
    conn.close()
    return changed


def order_is_expired(order):
    if not order["expires_at"]:
        return False
    return datetime.fromisoformat(order["expires_at"]) <= _now()


# ---------- customer-facing order views ----------
def get_user_orders(user_id, limit=10):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT o.id, o.kind, o.status, o.price, o.created_at, o.extra_days, o.extra_gb,
               o.chosen_username, p.duration_days, p.traffic_gb, s.sub_name AS sub_name
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        LEFT JOIN subscriptions s ON s.id = o.renew_sub_id
        WHERE o.user_id=? ORDER BY o.id DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return rows


def get_avg_delivery_minutes(sample=20):
    """Median minutes between 'receipt sent' and 'delivered' over the most
    recent deliveries, or None if there isn't enough data yet."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT receipt_at, delivered_at FROM orders WHERE status='delivered' "
        "AND receipt_at IS NOT NULL AND delivered_at IS NOT NULL ORDER BY id DESC LIMIT ?",
        (sample,),
    ).fetchall()
    conn.close()
    mins = []
    for r in rows:
        d = (datetime.fromisoformat(r["delivered_at"]) - datetime.fromisoformat(r["receipt_at"])).total_seconds() / 60
        if d >= 0:
            mins.append(d)
    if len(mins) < 3:
        return None
    mins.sort()
    return max(1, round(mins[len(mins) // 2]))


# ---------- ratings ----------
def set_order_rating(order_id, user_id, rating):
    """True only for the owner of a delivered, not-yet-rated order."""
    conn = get_conn()
    c = conn.execute(
        "UPDATE orders SET rating=? WHERE id=? AND user_id=? AND status IN ('delivered','refunded') "
        "AND rating IS NULL",
        (rating, order_id, user_id),
    )
    conn.commit()
    ok = c.rowcount > 0
    conn.close()
    return ok


# ---------- renewals ----------
def create_renewal_order(user_id, sub_id, extra_days, extra_gb, price, expires_at):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, plan_id, price, status, kind, renew_sub_id, extra_days, "
        "extra_gb, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id, None, price, "awaiting_receipt", "renewal", sub_id, extra_days, extra_gb,
         _now().isoformat(), expires_at),
    )
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id


def apply_renewal(order_id):
    """Extends the subscription's expiry (from today if it already lapsed,
    otherwise from its current expiry) and records the extra data. Marks the
    order delivered. Returns the new end datetime, or None if not applicable."""
    conn = get_conn()
    c = conn.cursor()
    order = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order or order["kind"] != "renewal" or order["status"] != "awaiting_admin":
        conn.close()
        return None
    sub = c.execute("SELECT * FROM subscriptions WHERE id=?", (order["renew_sub_id"],)).fetchone()
    if not sub:
        conn.close()
        return None
    base = max(_now(), datetime.fromisoformat(sub["end_date"]))
    new_end = base + timedelta(days=order["extra_days"] or 0)
    c.execute(
        "UPDATE subscriptions SET end_date=?, extra_gb=COALESCE(extra_gb,0)+?, active=1, reminded=0, "
        "total_gb=CASE WHEN total_gb IS NULL THEN NULL ELSE total_gb+? END, "
        "remaining_gb=CASE WHEN remaining_gb IS NULL THEN NULL ELSE remaining_gb+? END WHERE id=?",
        (new_end.isoformat(), order["extra_gb"] or 0, order["extra_gb"] or 0, order["extra_gb"] or 0, sub["id"]),
    )
    c.execute(
        "UPDATE orders SET status='delivered', delivered_at=? WHERE id=?",
        (_now().isoformat(), order_id),
    )
    conn.commit()
    conn.close()
    return new_end


def get_order_card(order_id):
    """Everything the admin needs to see about one order, as a dict (or None)."""
    conn = get_conn()
    o = conn.execute(
        """
        SELECT o.*, u.username, u.lang, u.flagged, p.duration_days, p.traffic_gb
        FROM orders o
        LEFT JOIN users u ON u.user_id = o.user_id
        LEFT JOIN plans p ON p.id = o.plan_id
        WHERE o.id=?
        """,
        (order_id,),
    ).fetchone()
    if not o:
        conn.close()
        return None
    card = dict(o)
    if o["kind"] == "renewal" and o["renew_sub_id"]:
        sub = conn.execute(
            "SELECT sub_name, order_id FROM subscriptions WHERE id=?", (o["renew_sub_id"],)
        ).fetchone()
        card["sub_name"] = sub["sub_name"] if sub else None
        card["original_order_id"] = sub["order_id"] if sub else None
    card["refunds"] = [
        dict(r) for r in conn.execute(
            "SELECT amount, reason, created_at FROM refunds WHERE order_id=? ORDER BY id", (order_id,)
        ).fetchall()
    ]
    conn.close()
    return card


# ---------- refunds ----------
def create_refund(order_id, amount, reason):
    """Records a refund. Returns (ok, message_or_order_dict). Can't refund
    more than what's left, and only delivered/refunded orders."""
    conn = get_conn()
    c = conn.cursor()
    o = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o:
        conn.close()
        return False, "Order not found."
    if o["status"] not in ("delivered", "refunded"):
        conn.close()
        return False, f"Order #{order_id} is '{o['status']}' — only delivered orders can be refunded."
    already = o["refunded_amount"] or 0
    remaining = o["price"] - already
    if amount <= 0 or amount > remaining:
        conn.close()
        return False, f"Amount must be between 1 and {remaining} (what's left on this order)."
    c.execute(
        "INSERT INTO refunds (order_id, amount, reason, created_at) VALUES (?,?,?,?)",
        (order_id, amount, reason, _now().isoformat()),
    )
    new_total = already + amount
    new_status = "refunded" if new_total >= o["price"] else o["status"]
    c.execute(
        "UPDATE orders SET refunded_amount=?, status=? WHERE id=?", (new_total, new_status, order_id)
    )
    conn.commit()
    conn.close()
    return True, {"order_id": order_id, "user_id": o["user_id"], "amount": amount,
                  "total_refunded": new_total, "remaining": o["price"] - new_total,
                  "status": new_status}


# ---------- flags ----------
def count_recent_declines(user_id, days):
    since = (_now() - timedelta(days=days)).isoformat()
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) n FROM orders WHERE user_id=? AND status='declined' AND declined_at >= ?",
        (user_id, since),
    ).fetchone()["n"]
    conn.close()
    return n


def set_user_flag(user_id, reason):
    conn = get_conn()
    conn.execute("UPDATE users SET flagged=1, flag_reason=? WHERE user_id=?", (reason, user_id))
    conn.commit()
    conn.close()


def clear_user_flag(user_id):
    conn = get_conn()
    c = conn.execute(
        "UPDATE users SET flagged=0, flag_reason=NULL WHERE user_id=? AND flagged=1", (user_id,)
    )
    conn.commit()
    ok = c.rowcount > 0
    conn.close()
    return ok


def conn_subs(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, sub_name, end_date, total_gb, remaining_gb, manual, order_id FROM subscriptions "
        "WHERE user_id=? AND active=1 ORDER BY id", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_user_profile(user_id):
    conn = get_conn()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not u:
        conn.close()
        return None
    q = lambda sql, *a: conn.execute(sql, a).fetchone()
    prof = dict(u)
    prof["orders_total"] = q("SELECT COUNT(*) n FROM orders WHERE user_id=?", user_id)["n"]
    for st in ("delivered", "declined", "expired", "awaiting_admin", "refunded"):
        prof[f"orders_{st}"] = q(
            "SELECT COUNT(*) n FROM orders WHERE user_id=? AND status=?", user_id, st)["n"]
    prof["spent"] = q(
        "SELECT COALESCE(SUM(price - COALESCE(refunded_amount,0)),0) s FROM orders "
        "WHERE user_id=? AND status IN ('delivered','refunded')", user_id)["s"]
    prof["active_subs"] = q(
        "SELECT COUNT(*) n FROM subscriptions WHERE user_id=? AND active=1", user_id)["n"]
    prof["ban_count"] = q("SELECT COUNT(*) n FROM bans WHERE user_id=?", user_id)["n"]
    prof["avg_rating"] = q(
        "SELECT AVG(rating) a FROM orders WHERE user_id=? AND rating IS NOT NULL", user_id)["a"]
    prof["last_order_at"] = q(
        "SELECT MAX(created_at) m FROM orders WHERE user_id=?", user_id)["m"]
    conn.close()
    prof["subs"] = [dict(r) for r in conn_subs(user_id)]
    prof["active_ban"] = get_active_ban(user_id)
    return prof


# ---------- subscriptions added by hand / usage notices / reminders ----------
def create_manual_subscription(user_id, sub_name, config_text, end_dt, total_gb):
    """A subscription the admin created outside the bot. No order exists for it."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO subscriptions (user_id, order_id, plan_name, sub_name, config_text, start_date, "
        "end_date, total_gb, remaining_gb, manual) VALUES (?,?,?,?,?,?,?,?,?,1)",
        (user_id, None, "Manual", sub_name, crypto.encrypt_text(config_text or ""),
         _now().isoformat(), end_dt.isoformat(), total_gb, total_gb),
    )
    sub_id = c.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def set_subscription_usage(sub_id, remaining_gb):
    """Records how much data is left. Returns the updated row (dict) or None."""
    conn = get_conn()
    c = conn.execute(
        "UPDATE subscriptions SET remaining_gb=?, remaining_updated_at=? WHERE id=? AND active=1",
        (remaining_gb, _now().isoformat(), sub_id),
    )
    conn.commit()
    row = None
    if c.rowcount:
        row = dict(conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone())
    conn.close()
    return row


def get_subscriptions_expiring(days):
    """Active subscriptions that end within `days` days and haven't been
    reminded yet (already-expired ones are skipped)."""
    now = _now()
    limit = (now + timedelta(days=days)).isoformat()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active=1 AND reminded=0 AND end_date > ? AND end_date <= ?",
        (now.isoformat(), limit),
    ).fetchall()
    conn.close()
    return rows


def mark_subscription_reminded(sub_id):
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET reminded=1 WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
