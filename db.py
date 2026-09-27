"""
Same function names/signatures as before - only the storage engine changed,
from a local SQLite file (wiped by Render on every redeploy/restart) to a
real Postgres database (Supabase/Neon free tier), which survives deploys.

Row objects behave like dicts (row["field"]), same as sqlite3.Row did, via
psycopg2's RealDictCursor - so bot.py, keyboards.py etc. needed no changes.
"""
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from config import DATABASE_URL
import crypto


def get_conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            lang TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS plans (
            id SERIAL PRIMARY KEY,
            duration_days INTEGER,
            traffic_gb TEXT,
            price INTEGER,
            active INTEGER DEFAULT 1,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            plan_id INTEGER,
            price INTEGER,
            receipt_file_id TEXT,
            status TEXT DEFAULT 'awaiting_receipt',
            created_at TEXT,
            delivered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
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
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
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

    required_columns = {
        "plans": [
            ("duration_days", "INTEGER"),
            ("traffic_gb", "TEXT"),
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
            ("reminded_days", "TEXT DEFAULT ''"),
        ],
        "users": [
            ("home_kb_shown", "INTEGER DEFAULT 0"),
        ],
    }
    for table, columns in required_columns.items():
        c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
            (table,),
        )
        existing = {row["column_name"] for row in c.fetchall()}
        for col_name, col_def in columns:
            if col_name not in existing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
    conn.commit()
    conn.close()


# ---------- users ----------
def upsert_user(user_id, username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (user_id, username, created_at) VALUES (%s,%s,%s)",
            (user_id, username, datetime.utcnow().isoformat()),
        )
    else:
        c.execute("UPDATE users SET username=%s WHERE user_id=%s", (username, user_id))
    conn.commit()
    conn.close()


def set_lang(user_id, lang):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, user_id))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_all_user_ids():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_user_by_username(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
    row = c.fetchone()
    conn.close()
    return row


# ---------- plans ----------
def upsert_plan(duration_days, traffic_gb, price):
    traffic_gb = str(traffic_gb)
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM plans WHERE duration_days=%s AND traffic_gb=%s",
        (duration_days, traffic_gb),
    )
    existing = c.fetchone()
    if existing:
        c.execute(
            "UPDATE plans SET price=%s, active=1, updated_at=%s WHERE id=%s",
            (price, datetime.utcnow().isoformat(), existing["id"]),
        )
    else:
        c.execute(
            "INSERT INTO plans (duration_days, traffic_gb, price, updated_at) VALUES (%s,%s,%s,%s)",
            (duration_days, traffic_gb, price, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def get_active_plans(duration_days=None):
    conn = get_conn()
    c = conn.cursor()
    if duration_days is not None:
        c.execute(
            "SELECT * FROM plans WHERE active=1 AND duration_days=%s ORDER BY traffic_gb ASC",
            (duration_days,),
        )
    else:
        c.execute(
            "SELECT * FROM plans WHERE active=1 ORDER BY duration_days ASC, traffic_gb ASC"
        )
    rows = c.fetchall()
    conn.close()
    return rows


def get_plan(plan_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM plans WHERE id=%s", (plan_id,))
    row = c.fetchone()
    conn.close()
    return row


def deactivate_missing_plans(seen_keys):
    seen_keys = {(d, str(t)) for d, t in seen_keys}
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, duration_days, traffic_gb FROM plans WHERE active=1")
    rows = c.fetchall()
    for row in rows:
        if (row["duration_days"], row["traffic_gb"]) not in seen_keys:
            c.execute("UPDATE plans SET active=0 WHERE id=%s", (row["id"],))
    conn.commit()
    conn.close()


# ---------- orders ----------
def create_order(user_id, plan_id, price, chosen_username=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, plan_id, price, status, chosen_username, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (user_id, plan_id, price, "awaiting_receipt", chosen_username, datetime.utcnow().isoformat()),
    )
    order_id = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return order_id


def get_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id=%s", (order_id,))
    row = c.fetchone()
    conn.close()
    return row


def set_order_receipt(order_id, file_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE orders SET receipt_file_id=%s, status='awaiting_admin' WHERE id=%s",
        (file_id, order_id),
    )
    conn.commit()
    conn.close()


def mark_order_delivered(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE orders SET status='delivered', delivered_at=%s WHERE id=%s",
        (datetime.utcnow().isoformat(), order_id),
    )
    conn.commit()
    conn.close()


def decline_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE orders SET status='declined' WHERE id=%s", (order_id,))
    conn.commit()
    conn.close()


def get_pending_orders():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
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
    )
    rows = c.fetchall()
    conn.close()
    return rows


# ---------- subscriptions ----------
def create_subscription(user_id, order_id, plan_name, sub_name, config_text, duration_days):
    start = datetime.utcnow()
    end = start + timedelta(days=duration_days)
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO subscriptions (user_id, order_id, plan_name, sub_name, config_text, start_date, end_date) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (user_id, order_id, plan_name, sub_name, crypto.encrypt_text(config_text), start.isoformat(), end.isoformat()),
    )
    conn.commit()
    conn.close()
    return end


def get_subscription(sub_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE id=%s", (sub_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["config_text"] = crypto.decrypt_text(data["config_text"])
    return data


def get_subscription_by_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE order_id=%s", (order_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["config_text"] = crypto.decrypt_text(data["config_text"])
    return data


def get_active_subscriptions(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM subscriptions WHERE user_id=%s AND active=1 ORDER BY end_date ASC",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def mark_home_kb_shown(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET home_kb_shown=1 WHERE user_id=%s", (user_id,))
    conn.commit()
    conn.close()


def get_all_active_subscription_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM subscriptions WHERE active=1")
    rows = c.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_subscriptions_needing_reminder(threshold_days):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow()
    cutoff = (now + timedelta(days=threshold_days)).isoformat()
    c.execute(
        "SELECT * FROM subscriptions WHERE active=1 AND end_date<=%s AND end_date>%s",
        (cutoff, now.isoformat()),
    )
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        sent = (r["reminded_days"] or "").split(",")
        if str(threshold_days) not in sent:
            out.append(r)
    return out


def mark_reminder_sent(sub_id, threshold_days):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT reminded_days FROM subscriptions WHERE id=%s", (sub_id,))
    row = c.fetchone()
    existing = (row["reminded_days"] or "") if row else ""
    parts = [p for p in existing.split(",") if p]
    parts.append(str(threshold_days))
    c.execute(
        "UPDATE subscriptions SET reminded_days=%s WHERE id=%s", (",".join(parts), sub_id)
    )
    conn.commit()
    conn.close()


# ---------- settings ----------
def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


# ---------- stats ----------
def get_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) n FROM users")
    users = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) n FROM orders")
    total_orders = c.fetchone()["n"]
    c.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(price),0) revenue FROM orders WHERE status='delivered'"
    )
    delivered = c.fetchone()
    c.execute("SELECT COUNT(*) n FROM orders WHERE status='awaiting_admin'")
    pending = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) n FROM subscriptions WHERE active=1")
    active_subs = c.fetchone()["n"]
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
    c.execute("UPDATE bans SET active=0 WHERE user_id=%s AND active=1", (user_id,))
    c.execute(
        "INSERT INTO bans (user_id, reason, banned_at, until, active) VALUES (%s,%s,%s,%s,1) RETURNING id",
        (user_id, reason, datetime.utcnow().isoformat(), until_iso),
    )
    ban_id = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return ban_id


def get_active_ban(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM bans WHERE user_id=%s AND active=1 ORDER BY id DESC LIMIT 1", (user_id,)
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    if datetime.fromisoformat(row["until"]) <= datetime.utcnow():
        c.execute("UPDATE bans SET active=0 WHERE id=%s", (row["id"],))
        conn.commit()
        conn.close()
        return None
    conn.close()
    return row


def get_ban_count(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) n FROM bans WHERE user_id=%s", (user_id,))
    n = c.fetchone()["n"]
    conn.close()
    return n


def unban_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM bans WHERE user_id=%s AND active=1 ORDER BY id DESC LIMIT 1", (user_id,)
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    c.execute(
        "UPDATE bans SET active=0, lifted_at=%s WHERE id=%s", (datetime.utcnow().isoformat(), row["id"])
    )
    conn.commit()
    conn.close()
    return True


# ---------- discount codes ----------
def create_discount(code, percent):
    code = code.strip().upper()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO discounts (code, percent, active, created_at) VALUES (%s, %s, 1, %s) "
        "ON CONFLICT(code) DO UPDATE SET percent=excluded.percent, active=1",
        (code, percent, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_discount(code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM discounts WHERE code=%s AND active=1", (code.strip().upper(),))
    row = c.fetchone()
    conn.close()
    return row


def get_active_discounts():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM discounts WHERE active=1 ORDER BY code ASC")
    rows = c.fetchall()
    conn.close()
    return rows


def deactivate_discount(code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT code FROM discounts WHERE code=%s AND active=1", (code.strip().upper(),))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    c.execute("UPDATE discounts SET active=0 WHERE code=%s", (row["code"],))
    conn.commit()
    conn.close()
    return True
