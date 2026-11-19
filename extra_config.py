"""
Settings for the newer features. Kept in their own file (instead of config.py)
so updating the bot never overwrites your edited config.py. Every value can be
overridden in .env; the defaults below work as-is.
"""
import os

import config  # loads .env


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


# ---- invoice timer ----
ORDER_EXPIRY_MINUTES = _int("ORDER_EXPIRY_MINUTES", 60)

# ---- delivery estimate shown to customers (used until enough real data exists) ----
DELIVERY_ETA_DEFAULT = os.getenv("DELIVERY_ETA_DEFAULT", "10-30")

# ---- subscription updates (renewals) ----
# Starting prices - change anytime from Telegram with /setrenew (no restart).
RENEW_PRICE_PER_MONTH = _int("RENEW_PRICE_PER_MONTH", 50000)
RENEW_PRICE_PER_GB = _int("RENEW_PRICE_PER_GB", 3000)
RENEW_MAX_MONTHS = _int("RENEW_MAX_MONTHS", 12)
RENEW_MIN_GB = 20
RENEW_MAX_GB = 600

# ---- expiry reminders ----
REMINDER_DAYS = _int("REMINDER_DAYS", 3)

# ---- abuse protection ----
RATE_LIMIT_MAX = _int("RATE_LIMIT_MAX", 8)          # updates allowed per window
RATE_LIMIT_WINDOW = _int("RATE_LIMIT_WINDOW", 5)    # seconds
FLOOD_STRIKES = _int("FLOOD_STRIKES", 3)            # violations within a minute -> auto-ban
FLOOD_BAN_MINUTES = _int("FLOOD_BAN_MINUTES", 10)
FLAG_DECLINE_THRESHOLD = _int("FLAG_DECLINE_THRESHOLD", 3)
FLAG_WINDOW_DAYS = _int("FLAG_WINDOW_DAYS", 30)

# ---- backups ----
BACKUP_ENABLED = _int("BACKUP_ENABLED", 1)
BACKUP_HOUR = _int("BACKUP_HOUR", 3)                # local hour (TIMEZONE) of the daily backup

# ---- admin dashboard ----
DASHBOARD_ENABLED = _int("DASHBOARD_ENABLED", 1)
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = _int("DASHBOARD_PORT", int(os.getenv("PORT", "8080")))
DASHBOARD_PUBLIC_URL = os.getenv("DASHBOARD_PUBLIC_URL", "").rstrip("/")

# optional; looked up from Telegram automatically if empty
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")
