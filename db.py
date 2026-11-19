import os
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from dotenv import load_dotenv

import crypto

load_dotenv()


def _now():
    """Naive UTC 'now' (same convention as the rest of this file)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg.connect(url, row_factory=dict_row)


def init_db():
    # PostgreSQL tables are created/managed in Supabase.
    # Kept as a no-op because bot.py calls this during startup.
    return


# ---------- users ----------
def upsert_user(user_id, username):
    with get_conn() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (user_id, username, created_at) VALUES (%s,%s,%s)",
                (user_id, username, datetime.utcnow().isoformat()),
            )
        else:
            conn.execute("UPDATE users SET username=%s WHERE user_id=%s", (username, user_id))


def set_lang(user_id, lang):
    with get_conn() as conn:
        conn.execute("UPDATE users SET lang=%s WHERE user_id=%s", (lang, user_id))


def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()


def get_all_user_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


def get_user_by_username(username):
    """Case-insensitive lookup by the username we last saw for them."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username,)
        ).fetchone()


# ---------- plans ----------
def upsert_plan(duration_days, traffic_gb, price):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM plans WHERE duration_days=%s AND traffic_gb=%s",
            (duration_days, traffic_gb),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE plans SET price=%s, active=1, updated_at=%s WHERE id=%s",
                (price, datetime.utcnow().isoformat(), existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO plans (duration_days, traffic_gb, price, updated_at) VALUES (%s,%s,%s,%s)",
                (duration_days, traffic_gb, price, datetime.utcnow().isoformat()),
            )


def get_active_plans(duration_days=None):
    with get_conn() as conn:
        if duration_days is not None:
            return conn.execute(
                "SELECT * FROM plans WHERE active=1 AND duration_days=%s ORDER BY traffic_gb ASC",
                (duration_days,),
            ).fetchall()

        return conn.execute(
            "SELECT * FROM plans WHERE active=1 ORDER BY duration_days ASC, traffic_gb ASC"
        ).fetchall()


def get_plan(plan_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM plans WHERE id=%s", (plan_id,)).fetchone()


def deactivate_missing_plans(seen_keys):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, duration_days, traffic_gb FROM plans WHERE active=1"
        ).fetchall()

        for row in rows:
            if (row["duration_days"], row["traffic_gb"]) not in seen_keys:
                conn.execute("UPDATE plans SET active=0 WHERE id=%s", (row["id"],))


# ---------- orders ----------
def create_order(user_id, plan_id, price, chosen_username=None, expires_at=None):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO orders "
            "(user_id, plan_id, price, status, chosen_username, created_at, expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                user_id,
                plan_id,
                price,
                "awaiting_receipt",
                chosen_username,
                _now().isoformat(),
                expires_at,
            ),
        ).fetchone()
        return row["id"]


def get_order(order_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id=%s", (order_id,)).fetchone()


def set_order_receipt(order_id, file_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET receipt_file_id=%s, status='awaiting_admin', receipt_at=%s WHERE id=%s",
            (file_id, _now().isoformat(), order_id),
        )


def mark_order_delivered(order_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status='delivered', delivered_at=%s WHERE id=%s",
            (datetime.utcnow().isoformat(), order_id),
        )


def decline_order(order_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status='declined', declined_at=%s WHERE id=%s",
            (_now().isoformat(), order_id),
        )


def get_pending_orders():
    with get_conn() as conn:
        return conn.execute(
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


# ---------- subscriptions ----------
def create_subscription(
    user_id, order_id, plan_name, sub_name, config_text, duration_days, total_gb=None
):
    start = datetime.utcnow()
    end = start + timedelta(days=duration_days)

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO subscriptions "
            "(user_id, order_id, plan_name, sub_name, config_text, start_date, end_date, total_gb) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                user_id,
                order_id,
                plan_name,
                sub_name,
                crypto.encrypt_text(config_text),
                start.isoformat(),
                end.isoformat(),
                total_gb,
            ),
        )

    return end


def get_subscription(sub_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE id=%s", (sub_id,)
        ).fetchone()

    if not row:
        return None

    data = dict(row)
    data["config_text"] = crypto.decrypt_text(data["config_text"])
    return data


def get_subscription_by_order(order_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE order_id=%s", (order_id,)
        ).fetchone()

    if not row:
        return None

    data = dict(row)
    data["config_text"] = crypto.decrypt_text(data["config_text"])
    return data


def get_active_subscriptions(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=%s AND active=1 ORDER BY end_date ASC",
            (user_id,),
        ).fetchall()


# ---------- settings ----------
def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=%s", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ---------- stats ----------
def get_stats():
    with get_conn() as conn:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        total_orders = conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
        delivered = conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE status='delivered'"
        ).fetchone()["n"]

        revenue = conn.execute(
            "SELECT COALESCE(SUM(price - COALESCE(refunded_amount,0)),0) AS r "
            "FROM orders WHERE status IN ('delivered','refunded')"
        ).fetchone()["r"]

        refunded = conn.execute(
            "SELECT COALESCE(SUM(refunded_amount),0) AS r FROM orders"
        ).fetchone()["r"]

        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE status='awaiting_admin'"
        ).fetchone()["n"]

        active_subs = conn.execute(
            "SELECT COUNT(*) AS n FROM subscriptions WHERE active=1"
        ).fetchone()["n"]

        rating = conn.execute(
            "SELECT AVG(rating) AS a, COUNT(rating) AS n "
            "FROM orders WHERE rating IS NOT NULL"
        ).fetchone()

        return {
            "users": users,
            "total_orders": total_orders,
            "delivered_orders": delivered,
            "revenue": revenue,
            "refunded_total": refunded,
            "pending_orders": pending,
            "active_subscriptions": active_subs,
            "avg_rating": round(float(rating["a"]), 2) if rating["a"] is not None else None,
            "rating_count": rating["n"],
        }


# ---------- bans ----------
def create_ban(user_id, reason, until_iso):
    with get_conn() as conn:
        conn.execute(
            "UPDATE bans SET active=0 WHERE user_id=%s AND active=1", (user_id,)
        )

        row = conn.execute(
            'INSERT INTO bans (user_id, reason, banned_at, "until", active) '
            "VALUES (%s,%s,%s,%s,1) RETURNING id",
            (user_id, reason, datetime.utcnow().isoformat(), until_iso),
        ).fetchone()

        return row["id"]


def get_active_ban(user_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM bans WHERE user_id=%s AND active=1 '
            'ORDER BY id DESC LIMIT 1',
            (user_id,),
        ).fetchone()

        if not row:
            return None

        if datetime.fromisoformat(row["until"]) <= datetime.utcnow():
            conn.execute("UPDATE bans SET active=0 WHERE id=%s", (row["id"],))
            return None

        return row


def get_ban_count(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM bans WHERE user_id=%s", (user_id,)
        ).fetchone()["n"]


def unban_user(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM bans WHERE user_id=%s AND active=1 "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        if not row:
            return False

        conn.execute(
            "UPDATE bans SET active=0, lifted_at=%s WHERE id=%s",
            (datetime.utcnow().isoformat(), row["id"]),
        )
        return True


# ---------- discount codes ----------
def create_discount(code, percent):
    code = code.strip().upper()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO discounts (code, percent, active, created_at) "
            "VALUES (%s, %s, 1, %s) "
            "ON CONFLICT(code) DO UPDATE SET percent=excluded.percent, active=1",
            (code, percent, datetime.utcnow().isoformat()),
        )


def get_discount(code):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM discounts WHERE code=%s AND active=1",
            (code.strip().upper(),),
        ).fetchone()


def get_active_discounts():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM discounts WHERE active=1 ORDER BY code ASC"
        ).fetchall()


def deactivate_discount(code):
    code = code.strip().upper()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT code FROM discounts WHERE code=%s AND active=1", (code,)
        ).fetchone()

        if not row:
            return False

        conn.execute(
            "UPDATE discounts SET active=0 WHERE code=%s", (row["code"],)
        )
        return True


# ---------- invoice timer ----------
def set_invoice_message(order_id, chat_id, msg_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET invoice_chat_id=%s, invoice_msg_id=%s WHERE id=%s",
            (chat_id, msg_id, order_id),
        )


def get_expired_unpaid_orders(now_iso=None):
    now_iso = now_iso or _now().isoformat()

    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE status='awaiting_receipt' "
            "AND expires_at IS NOT NULL AND expires_at <= %s",
            (now_iso,),
        ).fetchall()


def mark_order_expired(order_id):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE orders SET status='expired' "
            "WHERE id=%s AND status='awaiting_receipt'",
            (order_id,),
        )
        return cur.rowcount > 0


def order_is_expired(order):
    if not order["expires_at"]:
        return False
    return datetime.fromisoformat(order["expires_at"]) <= _now()


# ---------- customer-facing order views ----------
def get_user_orders(user_id, limit=10):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT o.id, o.kind, o.status, o.price, o.created_at, o.extra_days, o.extra_gb,
                   o.chosen_username, p.duration_days, p.traffic_gb, s.sub_name AS sub_name
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            LEFT JOIN subscriptions s ON s.id = o.renew_sub_id
            WHERE o.user_id=%s ORDER BY o.id DESC LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()


def get_avg_delivery_minutes(sample=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT receipt_at, delivered_at FROM orders WHERE status='delivered' "
            "AND receipt_at IS NOT NULL AND delivered_at IS NOT NULL "
            "ORDER BY id DESC LIMIT %s",
            (sample,),
        ).fetchall()

    mins = []
    for r in rows:
        d = (
            datetime.fromisoformat(r["delivered_at"])
            - datetime.fromisoformat(r["receipt_at"])
        ).total_seconds() / 60

        if d >= 0:
            mins.append(d)

    if len(mins) < 3:
        return None

    mins.sort()
    return max(1, round(mins[len(mins) // 2]))


# ---------- ratings ----------
def set_order_rating(order_id, user_id, rating):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE orders SET rating=%s WHERE id=%s AND user_id=%s "
            "AND status IN ('delivered','refunded') AND rating IS NULL",
            (rating, order_id, user_id),
        )
        return cur.rowcount > 0


# ---------- renewals ----------
def create_renewal_order(user_id, sub_id, extra_days, extra_gb, price, expires_at):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO orders "
            "(user_id, plan_id, price, status, kind, renew_sub_id, extra_days, "
            "extra_gb, created_at, expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                user_id,
                None,
                price,
                "awaiting_receipt",
                "renewal",
                sub_id,
                extra_days,
                extra_gb,
                _now().isoformat(),
                expires_at,
            ),
        ).fetchone()

        return row["id"]


def apply_renewal(order_id):
    with get_conn() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=%s", (order_id,)
        ).fetchone()

        if not order or order["kind"] != "renewal" or order["status"] != "awaiting_admin":
            return None

        sub = conn.execute(
            "SELECT * FROM subscriptions WHERE id=%s",
            (order["renew_sub_id"],),
        ).fetchone()

        if not sub:
            return None

        base = max(_now(), datetime.fromisoformat(sub["end_date"]))
        new_end = base + timedelta(days=order["extra_days"] or 0)

        conn.execute(
            "UPDATE subscriptions SET end_date=%s, "
            "extra_gb=COALESCE(extra_gb,0)+%s, active=1, reminded=0, "
            "total_gb=CASE WHEN total_gb IS NULL THEN NULL ELSE total_gb+%s END, "
            "remaining_gb=CASE WHEN remaining_gb IS NULL THEN NULL ELSE remaining_gb+%s END "
            "WHERE id=%s",
            (
                new_end.isoformat(),
                order["extra_gb"] or 0,
                order["extra_gb"] or 0,
                order["extra_gb"] or 0,
                sub["id"],
            ),
        )

        conn.execute(
            "UPDATE orders SET status='delivered', delivered_at=%s WHERE id=%s",
            (_now().isoformat(), order_id),
        )

        return new_end


def get_order_card(order_id):
    with get_conn() as conn:
        o = conn.execute(
            """
            SELECT o.*, u.username, u.lang, u.flagged, p.duration_days, p.traffic_gb
            FROM orders o
            LEFT JOIN users u ON u.user_id = o.user_id
            LEFT JOIN plans p ON p.id = o.plan_id
            WHERE o.id=%s
            """,
            (order_id,),
        ).fetchone()

        if not o:
            return None

        card = dict(o)

        if o["kind"] == "renewal" and o["renew_sub_id"]:
            sub = conn.execute(
                "SELECT sub_name, order_id FROM subscriptions WHERE id=%s",
                (o["renew_sub_id"],),
            ).fetchone()

            card["sub_name"] = sub["sub_name"] if sub else None
            card["original_order_id"] = sub["order_id"] if sub else None

        card["refunds"] = [
            dict(r)
            for r in conn.execute(
                "SELECT amount, reason, created_at FROM refunds "
                "WHERE order_id=%s ORDER BY id",
                (order_id,),
            ).fetchall()
        ]

        return card


# ---------- refunds ----------
def create_refund(order_id, amount, reason):
    with get_conn() as conn:
        o = conn.execute(
            "SELECT * FROM orders WHERE id=%s", (order_id,)
        ).fetchone()

        if not o:
            return False, "Order not found."

        if o["status"] not in ("delivered", "refunded"):
            return False, (
                f"Order #{order_id} is '{o['status']}' — only delivered orders can be refunded."
            )

        already = o["refunded_amount"] or 0
        remaining = o["price"] - already

        if amount <= 0 or amount > remaining:
            return False, (
                f"Amount must be between 1 and {remaining} "
                "(what's left on this order)."
            )

        conn.execute(
            "INSERT INTO refunds (order_id, amount, reason, created_at) "
            "VALUES (%s,%s,%s,%s)",
            (order_id, amount, reason, _now().isoformat()),
        )

        new_total = already + amount
        new_status = "refunded" if new_total >= o["price"] else o["status"]

        conn.execute(
            "UPDATE orders SET refunded_amount=%s, status=%s WHERE id=%s",
            (new_total, new_status, order_id),
        )

        return True, {
            "order_id": order_id,
            "user_id": o["user_id"],
            "amount": amount,
            "total_refunded": new_total,
            "remaining": o["price"] - new_total,
            "status": new_status,
        }


# ---------- flags ----------
def count_recent_declines(user_id, days):
    since = (_now() - timedelta(days=days)).isoformat()

    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM orders "
            "WHERE user_id=%s AND status='declined' AND declined_at >= %s",
            (user_id, since),
        ).fetchone()["n"]


def set_user_flag(user_id, reason):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET flagged=1, flag_reason=%s WHERE user_id=%s",
            (reason, user_id),
        )


def clear_user_flag(user_id):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET flagged=0, flag_reason=NULL "
            "WHERE user_id=%s AND flagged=1",
            (user_id,),
        )
        return cur.rowcount > 0


def conn_subs(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, sub_name, end_date, total_gb, remaining_gb, manual, order_id "
            "FROM subscriptions WHERE user_id=%s AND active=1 ORDER BY id",
            (user_id,),
        ).fetchall()


def get_user_profile(user_id):
    with get_conn() as conn:
        u = conn.execute(
            "SELECT * FROM users WHERE user_id=%s", (user_id,)
        ).fetchone()

        if not u:
            return None

        def q(sql, *args):
            return conn.execute(sql, args).fetchone()

        prof = dict(u)
        prof["orders_total"] = q(
            "SELECT COUNT(*) AS n FROM orders WHERE user_id=%s", user_id
        )["n"]

        for st in ("delivered", "declined", "expired", "awaiting_admin", "refunded"):
            prof[f"orders_{st}"] = q(
                "SELECT COUNT(*) AS n FROM orders WHERE user_id=%s AND status=%s",
                user_id,
                st,
            )["n"]

        prof["spent"] = q(
            "SELECT COALESCE(SUM(price - COALESCE(refunded_amount,0)),0) AS s "
            "FROM orders WHERE user_id=%s AND status IN ('delivered','refunded')",
            user_id,
        )["s"]

        prof["active_subs"] = q(
            "SELECT COUNT(*) AS n FROM subscriptions WHERE user_id=%s AND active=1",
            user_id,
        )["n"]

        prof["ban_count"] = q(
            "SELECT COUNT(*) AS n FROM bans WHERE user_id=%s", user_id
        )["n"]

        prof["avg_rating"] = q(
            "SELECT AVG(rating) AS a FROM orders "
            "WHERE user_id=%s AND rating IS NOT NULL",
            user_id,
        )["a"]

        prof["last_order_at"] = q(
            "SELECT MAX(created_at) AS m FROM orders WHERE user_id=%s",
            user_id,
        )["m"]

        prof["subs"] = [
            dict(r)
            for r in conn.execute(
                "SELECT id, sub_name, end_date, total_gb, remaining_gb, manual, order_id "
                "FROM subscriptions WHERE user_id=%s AND active=1 ORDER BY id",
                (user_id,),
            ).fetchall()
        ]

        prof["active_ban"] = conn.execute(
            'SELECT * FROM bans WHERE user_id=%s AND active=1 '
            'ORDER BY id DESC LIMIT 1',
            (user_id,),
        ).fetchone()

        return prof


# ---------- subscriptions added by hand / usage notices / reminders ----------
def create_manual_subscription(user_id, sub_name, config_text, end_dt, total_gb):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO subscriptions "
            "(user_id, order_id, plan_name, sub_name, config_text, start_date, "
            "end_date, total_gb, remaining_gb, manual) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1) RETURNING id",
            (
                user_id,
                None,
                "Manual",
                sub_name,
                crypto.encrypt_text(config_text or ""),
                _now().isoformat(),
                end_dt.isoformat(),
                total_gb,
                total_gb,
            ),
        ).fetchone()

        return row["id"]


def set_subscription_usage(sub_id, remaining_gb):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE subscriptions SET remaining_gb=%s, remaining_updated_at=%s "
            "WHERE id=%s AND active=1",
            (remaining_gb, _now().isoformat(), sub_id),
        )

        if not cur.rowcount:
            return None

        return dict(
            conn.execute(
                "SELECT * FROM subscriptions WHERE id=%s", (sub_id,)
            ).fetchone()
        )


def get_subscriptions_expiring(days):
    now = _now()
    limit = (now + timedelta(days=days)).isoformat()

    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM subscriptions "
            "WHERE active=1 AND reminded=0 AND end_date > %s AND end_date <= %s",
            (now.isoformat(), limit),
        ).fetchall()


def mark_subscription_reminded(sub_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE subscriptions SET reminded=1 WHERE id=%s",
            (sub_id,),
        )
