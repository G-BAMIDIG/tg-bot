# VPN Subscription Telegram Bot

Python + pyTelegramBotAPI + SQLite. Persian and English.

## Updating an existing install (step by step)
1. **Stop the bot** (Ctrl+C in its terminal).
2. **Back up**: copy your whole bot folder somewhere safe. The two files that matter most are
   `vpnbot.db` (all data) and `secret.key` (decrypts stored configs).
3. **Unzip `vpnbot-update.zip` into your bot folder**, choosing "replace" when asked. It only
   contains files that changed or are new. It does **not** contain `.env`, `config.py`,
   `vpnbot.db` or `secret.key`, so your settings and data are untouched.
   *(If you edited `locales.py` or `keyboards.py` yourself, re-apply your edits afterwards.)*
4. **Run the self-test** (needs no Telegram and never touches your real database):
   `python tests/run_tests.py` → the last line should say `162 passed, 0 failed`.
5. **Start the bot**: `python bot.py`. Your database upgrades itself on start; nothing is lost.
   You should see `Dashboard listening on http://127.0.0.1:8080`.
6. **Check it in Telegram** (2 minutes): send `/admin` (button panel), `/help` (command list),
   `/stats`. As a customer, open the menu: you should see **My Orders** and **Share**.
7. **Optional settings** go in `.env` (see `.env.example`). Nothing is required.

## Everything new in this version
**Customers**
- **Invoice timer** – every invoice is valid for `ORDER_EXPIRY_MINUTES` (default 60). The invoice
  prints the deadline; after it, the Send-Receipt button and any late receipt are refused (so an old
  invoice can never be paid at an old price), the button disappears and the customer is told.
- **My Orders** with live status (waiting for receipt / under review / delivered / declined /
  expired / refunded), **delivery estimate** (from your real delivery times; a default until
  there's data), **⭐ rating** after delivery, **Share with friends**, **"Best value"** badge.
- **Update subscription** (under My Subscriptions): add **months** (minimum 1) and/or **data**
  (20–600 GB). Price = months × per-month + GB × per-GB, plus the gateway fee. Starting prices are
  50000 / month and 3000 / GB – **change them with `/setrenew <per_month> <per_gb>`**. The admin
  alert says which order is being updated; **Approve** extends the expiry and adds the data.
- **Expiry reminder** 3 days before a subscription ends (with an Update button) and **"data
  left"** shown in My Subscriptions.

**Admin** (all of it only works for `ADMIN_ID`)
| Command | What it does |
|---|---|
| `/admin` | Button panel for everything below |
| `/help` | List of all commands |
| `/pending` | Orders waiting on you, each with working buttons |
| `/order <id>` | One order with its receipt photo (+ Deliver/Decline/Refund buttons) |
| `/user <id or @name>` | Full customer profile: orders, spend, bans, subscriptions (+ buttons) |
| `/addsub` | **Add a subscription by hand** for someone who can't buy in the bot. Guided, or one line: `/addsub <id or @user> <name> <days or YYYY-MM-DD> <GB or -> [link]`. The bot messages them the link and later sends the expiry reminders. |
| `/usage` | **Tell a customer how much data is left**: `/usage <sub number> <GB>` or guided. The bot notifies them. |
| `/message` | Message one customer (guided or `/message <id\|@user> <text>`) |
| `/broadcast <text>` | Message everyone |
| `/refund` | Record a refund (guided, or `/refund <order> <amount\|full> <reason>`). Customer is notified; stats update. It only *records* it – you send the money. |
| `/ban` `/unban` | Bans with reason, countdown and history |
| `/adddiscount` `/discounts` `/removediscount` | Discount codes |
| `/updateplans` | Set plans/prices (`months - GB - price` lines) |
| `/setrenew` | Prices for subscription updates |
| `/stats` | Users, orders, revenue (net of refunds), refunds, ratings |
| `/dashboard` | Link to the web dashboard |
| `/backup` | Sends you the database now (daily automatic backup too) |
| `/getconfig <order>` | Re-fetch a delivered config |
| `/togglehours` | Working-hours restriction on/off |

> **Manual subscriptions and notifications:** Telegram only lets a bot message people who have
> opened it at least once. For customers who never did, ask them to press /start once. If you
> add a subscription for an unknown numeric ID, the bot creates a placeholder and warns you.

**Protection**
- **Rate limiting + flood protection**: more than 8 actions in 5 seconds gets "slow down"; repeating it
  gets an automatic 10-minute ban and you get an alert with an **Unban** button. Admin is never limited.
- **Auto-flag**: 3 declined receipts in 30 days flags a customer (warning on their next orders;
  Ban / Dismiss buttons).
- **Non-admin alert**: if anyone tries an admin command or button, you get a message.
- **Backups**: `/backup` and one automatic backup per day at `BACKUP_HOUR` (03:00 local). Backups
  contain encrypted configs; **keep `secret.key` safe separately** – it is deliberately not in them.

## The admin dashboard (read-only)
Send `/dashboard` to the bot. It gives a one-time link (valid 10 minutes, works once). Pages are grouped
like a notebook: Overview, Orders, Customers, Subscriptions, Finance, Marketing, Feedback, System and a
**Roadmap** page (500 needs & ideas, 80 already built – also in `ROADMAP.md`). Tables are searchable and
sortable; order/customer rows open detail pages; receipts open in the browser.

It listens on `127.0.0.1` only, so it's invisible from the internet. Two ways to open it:
- **From your PC (simplest):** `ssh -L 8080:127.0.0.1:8080 you@your-server`, keep that window open, send
  `/dashboard`, and open the link in your PC's browser.
- **Inside Telegram on your phone (Mini App):** needs a domain with HTTPS. Example with Caddy:
  `dash.example.com { reverse_proxy 127.0.0.1:8080 }`, then set `DASHBOARD_PUBLIC_URL=https://dash.example.com`
  in `.env` and restart. `/dashboard` then shows an **Open dashboard** button; the page checks Telegram's
  signature and that you are the admin.
Turn it off with `DASHBOARD_ENABLED=0`.

## Settings (`.env`, all optional)
`ORDER_EXPIRY_MINUTES=60` · `DELIVERY_ETA_DEFAULT=10-30` · `RENEW_PRICE_PER_MONTH` · `RENEW_PRICE_PER_GB` ·
`REMINDER_DAYS=3` · `RATE_LIMIT_MAX=8` · `RATE_LIMIT_WINDOW=5` · `FLOOD_STRIKES=3` · `FLOOD_BAN_MINUTES=10` ·
`FLAG_DECLINE_THRESHOLD=3` · `FLAG_WINDOW_DAYS=30` · `BACKUP_ENABLED=1` · `BACKUP_HOUR=3` ·
`DASHBOARD_ENABLED=1` · `DASHBOARD_HOST` · `DASHBOARD_PORT=8080` · `DASHBOARD_PUBLIC_URL` · `BOT_USERNAME`.
They live in `extra_config.py` (not `config.py`), so updates never overwrite your edited `config.py`.

## Troubleshooting
- *Dashboard says "could not start"*: port 8080 is taken – set `DASHBOARD_PORT=8081`.
- *Customer didn't get a reminder/notice*: they never pressed /start or blocked the bot; the bot tells you when a
  message can't be delivered.
- *Backup says it failed*: check the folder is writable; `/backup` shows the error.

## Testing
`python tests/run_tests.py` plays customer and admin conversations through the real bot code against a fake
Telegram, using a temporary database. It checks 162 things (invoice expiry, renewals, manual subscriptions,
reminders, refunds, security, every dashboard page, database upgrade from an old version, …). It cannot
reach the real Telegram, so do the quick check in step 6 after updating.
