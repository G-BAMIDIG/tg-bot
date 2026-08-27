
"""
All the settings for the bot.
Secrets (token, admin id, card info) are loaded from a .env file so they're
never hardcoded in a file you might accidentally share or commit to a public
repo. See .env.example for the full list. If a value is missing from .env,
this falls back to the value you originally gave me so the bot still runs -
but for real security you should move everything into .env and never share
that file. See README.md "Security" section.
"""
import os
import pathlib
from dotenv import load_dotenv

# Anchor everything to the folder this file lives in, NOT the terminal's
# current working directory. Otherwise launching the bot from a different
# folder (a different shortcut, a cron job, a different terminal session)
# silently creates a brand new empty database instead of finding the real
# one - which looks exactly like "my data got reset" but isn't a data loss,
# it's just looking in the wrong place.
BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name, default):
    val = os.getenv(name)
    return default if val is None else val.strip().lower() in ("1", "true", "yes")


def _anchored_path(env_value, default_filename):
    """Relative paths are resolved against BASE_DIR, not the cwd. Absolute
    paths (if you ever set one) are left untouched."""
    raw = env_value or default_filename
    p = pathlib.Path(raw)
    return str(p if p.is_absolute() else BASE_DIR / p)


# ---- Required ----
# No hardcoded fallbacks for secrets: this file is committed to git (it's
# not in .gitignore, .env is), so a fallback here would leak into a public
# repo the moment you push. Set these in .env locally / in Render's
# Environment tab in production - if they're missing, fail loudly instead
# of silently running with someone else's old test values.
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to .env (local) or Render's Environment tab (production).")

_admin_id_env = os.getenv("ADMIN_ID")
if not _admin_id_env:
    raise RuntimeError("ADMIN_ID is not set. Add it to .env (local) or Render's Environment tab (production).")
ADMIN_ID = int(_admin_id_env)

# ---- Support ----
_support_id_env = os.getenv("SUPPORT_USER_ID")
SUPPORT_USER_ID = int(_support_id_env) if _support_id_env else None
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")

# ---- Payment card ----
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER_NAME = os.getenv("CARD_HOLDER_NAME", "")

# ---- Alarm behavior ----
ALARM_INTERVAL_SECONDS = int(os.getenv("ALARM_INTERVAL_SECONDS", "5"))
ALARM_MAX_PINGS = int(os.getenv("ALARM_MAX_PINGS", "120"))  # 120 * 5s = 10 minutes

# ---- Order gateway fee ----
# Applied directly to every order's price at checkout (plan price + fee = what
# the customer actually pays and what you receive).
ORDER_FEE_PERCENT = int(os.getenv("ORDER_FEE_PERCENT", "5"))

# ---- USD rate (for showing ~$ next to Toman amounts) ----
DOLLAR_RATE_URL = "https://www.tgju.org/profile/price_dollar_rl"
DOLLAR_RATE_CACHE_SECONDS = 1800  # re-scrape at most every 30 minutes
DOLLAR_RATE_FALLBACK = int(os.getenv("DOLLAR_RATE_FALLBACK", "950000"))

# ---- Plans / scraping ----
TARGET_BOT_USERNAME = os.getenv("TARGET_BOT_USERNAME", "lomesnetbot")
MARKUP_MULTIPLIER = float(os.getenv("MARKUP_MULTIPLIER", "1.8"))

# ---- Working hours ----
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tehran")
OPEN_HOUR = int(os.getenv("OPEN_HOUR", "10"))

# ---- "How to connect" content, per platform ----
HOWTO_PLATFORMS = {
    "android": {
        "label": {"en": "🤖 Android (v2rayNG)", "fa": "🤖 اندروید (v2rayNG)"},
        "video_file_id": os.getenv("HOWTO_VIDEO_ANDROID") or None,
        "text": {
            "en": (
                "1️⃣ Copy the link the bot sent you.\n"
                "2️⃣ Open v2rayNG → tap the <b>3 dots (⋮)</b> in the top-right corner.\n"
                "3️⃣ Tap <b>Add config</b> → <b>Import from clipboard</b>.\n"
                "4️⃣ Wait a few seconds — your subscription will appear!\n\n"
                "🚀 <b>How to get the best connection every time:</b>\n"
                "• Before connecting: 3 dots → <b>Update subscription</b> (at the bottom).\n"
                "• Then 3 dots → <b>Real delay test</b>.\n"
                "• After the test finishes: 3 dots → <b>Sort by test results</b>.\n"
                "• The best config (lowest ping) is now at the top — tap it and connect!\n"
                " \n"
                "⚠️if you couldnt connect,power off your device completly and after a minute turn on your device and try again.\n"
            ),
            "fa": (
                "1️⃣ لینکی که ربات براتون فرستاده رو کپی کنید.\n"
                "2️⃣ برنامه v2rayNG رو باز کنید → روی <b>سه نقطه (⋮)</b> گوشه بالا سمت راست بزنید.\n"
                "3️⃣ گزینه <b>Add config</b> → <b>Import from clipboard</b> رو انتخاب کنید.\n"
                "4️⃣ چند ثانیه صبر کنید — اشتراک‌تون ظاهر می‌شه!\n\n"
                "🚀 <b>چطور بهترین اتصال رو داشته باشید:</b>\n"
                "• قبل از هر بار اتصال: سه نقطه → <b>Update subscription</b> (پایین لیست).\n"
                "• دوباره سه نقطه → <b>Real delay test</b>.\n"
                "• بعد از تموم شدن تست: سه نقطه → <b>Sort by test results</b>.\n"
                "• بهترین کانفیگ (کمترین پینگ) میاد بالای لیست — روش بزنید و وصل بشید!\n"
                " \n"
                "⚠️اگر موفق به برقراری اتصال نشدید، دستگاه خود را کاملاً خاموش کنید، پس از یک دقیقه آن را روشن نمایید و دوباره تلاش کنید.\n"
            ),
        },
        "update_note": {
            "en": "<b>⚠️ Please make sure v2rayNG is updated to the latest version (not a beta) before connecting.</b>",
            "fa": "<b>⚠️ لطفاً قبل از اتصال، از به‌روزرسانی v2rayNG به آخرین نسخه (نه نسخه بتا) مطمئن شوید.</b>",
        },
        "downloads": [
            {
                "url": "https://github.com/2dust/v2rayNG/releases/latest",
                "label": {"en": "⬇️ Download v2rayNG (GitHub)", "fa": "⬇️ دانلود v2rayNG (گیت‌هاب)"},
            }
        ],
    },
    "ios": {
        "label": {"en": "🍎 iOS / Android (V2Box)", "fa": "🍎 آیفون / اندروید (V2Box)"},
        "video_file_id": os.getenv("HOWTO_VIDEO_IOS") or None,
        "text": {
            "en": (
                "1️⃣ Copy the link the bot sent you.\n"
                "2️⃣ Open V2Box → go to the <b>Configs</b> tab at the bottom.\n"
                "3️⃣ Tap the <b>+</b> button → <b>Import V2Ray URI from Clipboard</b>.\n"
                "4️⃣ Your subscription will appear — slide the connect switch to connect!\n\n"
                "🚀 <b>How to get the best connection every time:</b>\n"
                "• Before connecting: go to Configs → tap <b>+</b> → <b>Update All Subscriptions</b>.\n"
                "• Wait until the loading finishes.\n"
                "• The best config will be at the top — select it and connect!\n"
                " \n"
                "⚠️if you couldnt connect,power off your device completly and after a minute turn on your device and try again.\n"
            ),
            "fa": (
                "1️⃣ لینکی که ربات براتون فرستاده رو کپی کنید.\n"
                "2️⃣ برنامه V2Box رو باز کنید → به تب <b>Configs</b> پایین صفحه برید.\n"
                "3️⃣ روی دکمه <b>+</b> بزنید → گزینه <b>Import V2Ray URI from Clipboard</b> رو انتخاب کنید.\n"
                "4️⃣ اشتراک‌تون ظاهر می‌شه — اسلایدر اتصال رو بکشید تا وصل بشید!\n\n"
                "🚀 <b>چطور بهترین اتصال رو داشته باشید:</b>\n"
                "• قبل از هر بار اتصال: به Configs برید → روی <b>+</b> بزنید → <b>Update All Subscriptions</b>.\n"
                "• صبر کنید تا لودینگ تموم بشه.\n"
                "• بهترین کانفیگ میاد بالای لیست — انتخابش کنید و وصل بشید!\n"
                " \n"
                "⚠️اگر موفق به برقراری اتصال نشدید، دستگاه خود را کاملاً خاموش کنید، پس از یک دقیقه آن را روشن نمایید و دوباره تلاش کنید.\n"
            ),
        },
        "update_note": {
            "en": "<b>⚠️ Please make sure V2Box is updated to the latest version (not a beta) before connecting.</b>",
            "fa": "<b>⚠️ لطفاً قبل از اتصال، از به‌روزرسانی V2Box به آخرین نسخه (نه نسخه بتا) مطمئن شوید.</b>",
        },
        "downloads": [
            {
                "url": "https://apps.apple.com/app/v2box-v2ray-client/id6446814690",
                "label": {
                    "en": "⬇️ Download V2Box (App Store)",
                    "fa": "⬇️ دانلود V2Box (اپ استور)"
                }
            },
            {
                "url": "https://play.google.com/store/apps/details?id=dev.hexasoftware.v2box&hl=ru&pli=1",
                "label": {
                    "en": "⬇️ Download V2Box (Play Store)",
                    "fa": "⬇️ دانلود V2Box (پلی استور)"
                }
            }
        ],
    },
    "windows": {
        "label": {"en": "🖥 Windows (v2rayN)", "fa": "🖥 ویندوز (v2rayN)"},
        "video_file_id": os.getenv("HOWTO_VIDEO_WINDOWS") or None,
        "text": {
            "en": (
                "<b>Part 1 – How to import & connect:</b>\n"
                "1️⃣ Copy the link the bot sent you.\n"
                "2️⃣ Open v2rayN → press <b>Ctrl + V</b>. The config list will appear.\n"
                "3️⃣ Click <b>Subscription group</b> (top-left) → <b>Update current group subscription without proxy</b>.\n"
                "4️⃣ Wait until you see “Update subscription ended” in the terminal.\n"
                "5️⃣ Turn <b>Enable Tun</b> off → set mode to <b>V3 WhiteList</b>.\n"
                "6️⃣ Press <b>Ctrl + A</b> then <b>Ctrl + R</b>. Wait for the “Task complete” notification.\n"
                "7️⃣ Right-click the configs list → <b>Select by test result</b> → <b>Sort by test result</b>.\n"
                "8️⃣ The best config (lowest ping) is now at the top — select it and press <b>Enter</b>.\n"
                "9️⃣ Change “Clear system proxy” to <b>Set system proxy</b>.\n\n"
                "🚀 <b>Part 2 – Best experience every time:</b>\n"
                "• Always update the subscription first (step 3).\n"
                "• Always run the real-delay test and sort by results (steps 6-7).\n"
                "• This way you always get the fastest server for your internet!\n"
                " \n"
                "⚠️if you couldnt connect,power off your device completly and after a minute turn on your device and try again.\n"
            ),
            "fa": (
                "<b>قسمت ۱ – وارد کردن و اتصال:</b>\n"
                "1️⃣ لینکی که ربات براتون فرستاده رو کپی کنید.\n"
                "2️⃣ برنامه v2rayN رو باز کنید → کلیدهای <b>Ctrl + V</b> رو بزنید. لیست کانفیگ‌ها ظاهر می‌شه.\n"
                "3️⃣ روی <b>Subscription group</b> (بالا سمت چپ) کلیک کنید → گزینه <b>Update current group subscription without proxy</b> رو بزنید.\n"
                "4️⃣ صبر کنید تا پیام “Update subscription ended” تو ترمینال بیاد.\n"
                "5️⃣ گزینه <b>Enable Tun</b> رو خاموش کنید → حالت رو روی <b>V3 WhiteList</b> بذارید.\n"
                "6️⃣ کلیدهای <b>Ctrl + A</b> و بعد <b>Ctrl + R</b> رو بزنید. منتظر اعلان “Task complete” بمونید.\n"
                "7️⃣ روی لیست کانفیگ‌ها راست‌کلیک کنید → <b>Select by test result</b> → <b>Sort by test result</b>.\n"
                "8️⃣ بهترین کانفیگ (کمترین پینگ) میاد بالای لیست — انتخابش کنید و <b>Enter</b> بزنید.\n"
                "9️⃣ گزینه “Clear system proxy” رو به <b>Set system proxy</b> تغییر بدید.\n\n"
                "🚀 <b>قسمت ۲ – بهترین تجربه هر بار:</b>\n"
                "• همیشه اول اشتراک رو آپدیت کنید (مرحله ۳).\n"
                "• همیشه تست تأخیر واقعی رو اجرا کنید و بر اساس نتیجه مرتب کنید (مراحل ۶ و ۷).\n"
                "• اینطوری همیشه سریع‌ترین سرور رو برای اینترنت‌تون دارید!\n"
                " \n"
                "⚠️اگر موفق به برقراری اتصال نشدید، دستگاه خود را کاملاً خاموش کنید، پس از یک دقیقه آن را روشن نمایید و دوباره تلاش کنید.\n"
            ),
        },
        "update_note": {
            "en": "<b>⚠️ Please make sure v2rayN is updated to the latest version (not a beta) before connecting.</b>",
            "fa": "<b>⚠️ لطفاً قبل از اتصال، از به‌روزرسانی v2rayN به آخرین نسخه (نه نسخه بتا) مطمئن شوید.</b>",
        },
        "downloads": [
            {
                "url": "https://github.com/2dust/v2rayN/releases/latest",
                "label": {"en": "⬇️ Download v2rayN (GitHub)", "fa": "⬇️ دانلود v2rayN (گیت‌هاب)"},
            }
        ],
    },
}

# ---- Database ----
DB_PATH = _anchored_path(os.getenv("DB_PATH"), "vpnbot.db")

# ---- FAQ content shown from the home menu ----
# Placeholder questions - edit these to match your actual policies.
FAQ_TEXT = {
    "en": (
        "❓ Frequently Asked Questions\n\n"
        "• How long after payment do I get my subscription?\n"
        "  Usually within a few minutes during working hours.\n\n"
        "• Can I use one subscription on multiple devices?\n"
        "  Check the plan description - most plans support multiple users.\n\n"
        "• What if my payment isn't confirmed?\n"
        "  Contact Support from the main menu with your receipt.\n\n"
        "• Do you offer refunds?\n"
        "  Contact Support to discuss your specific situation."
    ),
    "fa": (
        "❓ سوالات متداول\n\n"
        "• بعد از پرداخت چقدر طول می‌کشد تا اشتراکم را دریافت کنم؟\n"
        "  معمولاً طی چند دقیقه در ساعات کاری.\n\n"
        "• آیا می‌توانم از یک اشتراک روی چند دستگاه استفاده کنم؟\n"
        "  توضیحات پلن را بررسی کنید - اکثر پلن‌ها چند کاربره هستند.\n\n"
        "• اگر پرداختم تایید نشد چه کار کنم؟\n"
        "  از منوی اصلی با پشتیبانی تماس بگیرید و رسید خود را ارسال کنید.\n\n"
        "• آیا امکان بازگشت وجه وجود دارد؟\n"
        "  برای بررسی وضعیت خود با پشتیبانی صحبت کنید."
    ),
}

# ---- Encryption ----
# Encrypts sensitive data (delivered VPN configs) before it's stored on disk,
# so a stolen/leaked vpnbot.db file doesn't hand over live subscription
# credentials. Key is auto-generated into secret.key on first run if you
# don't set ENCRYPTION_KEY yourself in .env - see crypto.py and README.md.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY") or None
