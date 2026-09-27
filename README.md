# VPN Subscription Telegram Bot

Built with [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) (`telebot`) + SQLite.

## Setup
1. `pip install -r requirements.txt --break-system-packages`
2. Your real values are already in `.env`. Still-blank: `SUPPORT_USER_ID` and the
   `HOWTO_VIDEO_*` file_ids (see the how-to-connect walkthrough below).
3. `python bot.py`

## Buy flow (as seen by the customer)
1. **Buy Subscription** → **✨ Custom Plan** / **1 Month** / **3 Months**.
2. Picking a duration lists its GB tiers; picking a tier shows the plan details.
3. **Finalize purchase** → asks for a subscription name (5–15 chars, English letters
   and numbers only, retries on anything invalid) → then asks for an optional
   discount code (tap Skip or type a code) → then shows the payment invoice: plan
   price, the discount if one was applied, the gateway fee (`ORDER_FEE_PERCENT` in
   `.env`, default 5%, calculated on the discounted price), and the total — card
   number as tap-to-copy.
4. **Send Receipt** → photo → you get a repeating alert with **Seen** / **Deliver**.
5. You send the config as text → forwarded to the user wrapped in a copyable code
   block, with both the Gregorian and Jalali (Persian) expiry date.
6. **My Subscriptions** lists each one by its chosen name with its own **🔗 Get URL**
   button — tapping it resends that exact config, copyable, any time.

## Admin commands
| Command | What it does |
|---|---|
| `/updateplans` | Paste `months - GB - price` lines, exact prices before the fee |
| `/getconfig <order_id>` | Re-fetch a delivered config (decrypted, copyable) |
| `/pending` | List every order still waiting on you |
| `/stats` | Users, orders, revenue, active subscriptions |
| `/broadcast <message>` | Message every user who's started the bot |
| `/togglehours` | Turn the 10:00–23:59 restriction on/off (persists) |
| `/ban` | Ban someone — asks for id/@username, shows their ban history, asks duration then reason |
| `/unban` | Unban someone — asks for id/@username, tells you plainly if they weren't banned |
| `/adddiscount` | Create/update a discount code — asks for the code, then percent off |
| `/discounts` | List every active discount code |
| `/removediscount <code>` | Deactivate a code |

## Banning
`/ban` walks through: **who** (numeric ID or @username — only works if they've
messaged the bot before, since Telegram gives no other way to resolve a username to
an ID) → shows how many times they've been banned before → **how long** (`24`, `24h`,
or `3d`) → **why**. The banned user is notified immediately in their own language with
the reason and a countdown, and gets that exact same notice again every time they try
to use the bot until it expires or you `/unban` them (also available as a one-tap
"🔓 Unban now" button right after banning). `/unban` on someone not currently banned
tells you so instead of silently doing nothing. Ban history is never deleted, even
after unbanning — only whether it's *currently* active resets.

## Discount codes
`/adddiscount` → send the code (e.g. `SAVE10`) → send the percent off (1–100).
During checkout, right after picking a subscription name, the customer is asked for
a code (or can tap Skip). A valid code discounts the **plan price**, and the gateway
fee is calculated on the *discounted* amount — the invoice shows the original price,
the discount line, the fee, and the final total, so nothing is hidden. Codes are
case-insensitive (`save10` and `SAVE10` both work) and re-running `/adddiscount` with
an existing code just updates its percentage.

## How to set up "How to Connect" content
1. Open `config.py`, find `HOWTO_PLATFORMS`. Edit the `text` for android/ios/windows
   directly — it's plain dict values, no special syntax.
2. Run the bot, send each tutorial video to it directly as the admin. It replies with
   a `file_id`.
3. Paste each `file_id` into `.env` under `HOWTO_VIDEO_ANDROID` / `_IOS` / `_WINDOWS`.
4. Restart the bot. Text-only works fine if you skip the videos.

## FAQ button
Home menu now has **❓ FAQ**. Content is `FAQ_TEXT` in `config.py` — placeholder
questions right now, edit them to match your actual policies.

## Support
No button, no phone number — the message text itself contains `@{support_username}`,
which Telegram auto-links on its own. (The "OK" button under Custom Plan is a
different, intentional thing — it still opens your profile directly via
`tg://user?id=`, since that's a deliberate one-tap handoff, not the general Support
screen.)

## What changed this round (all re-verified with real simulated tests, not just read)
- **Subscription naming restored**, with your exact validation rules and message text.
- **Fee is back**, applied directly to the order total (5% default, `ORDER_FEE_PERCENT`
  in `.env`) — shown broken out in the invoice.
- **All prices dropped the thousands separator** — `98000`, not `98,000`, everywhere.
- **Delivered configs are now copyable** (wrapped in a code block) — I deliberately
  tested this with special characters (`&`, `<`, `>`) in a fake config to make sure
  they're safely escaped rather than breaking the message.
- **Persian (Jalali) date** added next to the Gregorian one on delivery — converted
  with a small pure-Python algorithm (no extra dependency to fail installing), checked
  against three independently-known reference dates including Nowruz 1403 and 1404.
- **Get URL button** per subscription under My Subscriptions.
- **Support is button-free** — just a tappable `@mention` in the text.
- **Ban/unban system**, fully covered above.

## Latest fixes (this round)
- **Critical: a stuck conversation state could silently swallow every admin
  command.** If a purchase flow (or any multi-step admin flow) was ever left
  mid-way — e.g. asked for a subscription name but never given a valid one —
  every message from that person, including real commands like `/pending`,
  got intercepted and treated as if it were still answering that old prompt.
  Fixed at the root: every stateful "waiting for your next message" handler
  now explicitly ignores anything starting with `/`, so a command always
  reaches its real handler regardless of leftover state. `/start` and every
  admin command also now actively clear any stuck flow the moment they run,
  as a second layer of protection. Reproduced the exact reported scenario in
  a test and confirmed it's fixed.
- **`/pending` is now actionable, not just informational** — it resends each
  waiting order as a full card with working Seen/Deliver/Decline buttons (not
  a repeating alarm, just a one-time resend), so if a button or alert ever
  gets lost, scrolled past, or times out, you can still act on it immediately
  instead of the order being stuck with no way to complete it.
- **Discount codes** — see the section above.
- **Persian text mixed with numbers was rendering out of order** (e.g. plan tiers,
  prices) — fixed by adding a Right-to-Left Mark (U+200F, a standard invisible
  Unicode character made for exactly this) to the start of any Persian string that
  combines Persian words with numbers or Latin text: prices, traffic amounts,
  durations, the subscriptions list, and the "Get URL" buttons. I can't render an
  actual Telegram client from here, so please double check it looks right in the app
  — but this is the standard, widely-used fix for this exact class of problem, not a
  guess.
- **Subscription-name prompt had a stray artifact** — the Persian message had a
  leftover `` `.` `` (backtick-period-backtick) sitting in it that rendered as
  garbled punctuation. Removed it and the sentence now reads as clean, grammatical
  Persian.

## Encryption
Delivered VPN configs are encrypted at rest in `vpnbot.db` (Fernet via `crypto.py`).
`secret.key` (auto-generated on first run) is what decrypts them — back it up, never
share it. Card number/prices aren't encrypted since they're shown to every customer
anyway.

## Working hours
10:00–23:59 by default (`TIMEZONE`/`OPEN_HOUR` in `.env`), toggle with `/togglehours`.
`ADMIN_ID` is never restricted by this or by bans.

## Free 24/7 hosting
**Oracle Cloud's Always Free tier** (real small VPS, no time limit). Run under
`systemd` (or `tmux`/`pm2`) so it restarts after crashes/reboots. If the bot restarts
while an order is mid-flight (receipt sent, not yet delivered), it automatically
re-alerts you on startup — verified with a direct test.

## Notes
- No automated payment processing — card-to-card + manual admin confirmation, by
  design. Fraud protection is only as good as your own check of each receipt photo.
- Every admin command and admin-only button checks `ADMIN_ID` — anyone else triggering
  them is silently ignored.
- `.env` holds every secret and is gitignored — never share it.
