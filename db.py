import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH
import crypto


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
        ],
        "subscriptions": [
            ("sub_name", "TEXT"),
            # Comma-separated list of which expiry reminders were already
            # sent for this subscription, e.g. "7,3" - so the reminder loop
            # never sends the same one twice even if the bot restarts.
            ("reminded_days", "TEXT DEFAULT ''"),
        ],
        "users": [
            # Tracks whether we've already shown this user the one-time
            # "here's your Home button" note, so it's only ever sent once.
            ("home_kb_shown", "INTEGER DEFAULT 0"),
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
def create_order(user_id, plan_id, price, chosen_username=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, plan_id, price, status, chosen_username, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, plan_id, price, "awaiting_receipt", chosen_username, datetime.utcnow().isoformat()),
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
        "UPDATE orders SET receipt_file_id=?, status='awaiting_admin' WHERE id=?",
        (file_id, order_id),
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
        "UPDATE orders SET status='declined' WHERE id=?",
        (order_id,),
    )
    conn.commit()
    conn.close()


def get_pending_orders():
    """Orders where the receipt is in but nobody's delivered the config yet."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT o.id AS order_id, o.price, o.receipt_file_id, o.created_at,
               u.user_id, u.username,
               p.duration_days, p.traffic_gb
        FROM orders o
        JOIN users u ON u.user_id = o.user_id
        JOIN plans p ON p.id = o.plan_id
        WHERE o.status = 'awaiting_admin'
        ORDER BY o.created_at ASC
        """
    ).fetchall()
    conn.close()
    return rows


# ---------- subscriptions ----------
def create_subscription(user_id, order_id, plan_name, sub_name, config_text, duration_days):
    start = datetime.utcnow()
    end = start + timedelta(days=duration_days)
    conn = get_conn()
    conn.execute(
        "INSERT INTO subscriptions (user_id, order_id, plan_name, sub_name, config_text, start_date, end_date) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, order_id, plan_name, sub_name, crypto.encrypt_text(config_text), start.isoformat(), end.isoformat()),
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


def mark_home_kb_shown(user_id):
    conn = get_conn()
    conn.execute("UPDATE users SET home_kb_shown=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_all_active_subscription_users():
    """Distinct user_ids with at least one active subscription - used by the
    expiry-reminder loop."""
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT user_id FROM subscriptions WHERE active=1").fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_subscriptions_needing_reminder(threshold_days):
    """Active subscriptions that have crossed the given days-left threshold
    but haven't been sent that reminder yet."""
    conn = get_conn()
    now = datetime.utcnow()
    cutoff = (now + timedelta(days=threshold_days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active=1 AND end_date<=? AND end_date>?",
        (cutoff, now.isoformat()),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        sent = (r["reminded_days"] or "").split(",")
        if str(threshold_days) not in sent:
            out.append(r)
    return out


def mark_reminder_sent(sub_id, threshold_days):
    conn = get_conn()
    row = conn.execute("SELECT reminded_days FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    existing = (row["reminded_days"] or "") if row else ""
    parts = [p for p in existing.split(",") if p]
    parts.append(str(threshold_days))
    conn.execute(
        "UPDATE subscriptions SET reminded_days=? WHERE id=?", (",".join(parts), sub_id)
    )
    conn.commit()
    conn.close()


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
        "SELECT COUNT(*) n, COALESCE(SUM(price),0) revenue FROM orders WHERE status='delivered'"
    ).fetchone()
    pending = c.execute(
        "SELECT COUNT(*) n FROM orders WHERE status='awaiting_admin'"
    ).fetchone()["n"]
    active_subs = c.execute(
        "SELECT COUNT(*) n FROM subscriptions WHERE active=1"
    ).fetchone()["n"]
    conn.close()
    return {
        "users": users,
        "total_orders": total_orders,
        "delivered_orders": delivered["n"],
        "revenue": delivered["revenue"],
        "pending_orders": pending,
        "active_subscriptions": active_subs,
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
