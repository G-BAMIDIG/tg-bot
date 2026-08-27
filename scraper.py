"""
OPTIONAL fully-automated scraper for lomesnetbot's Multi Location plans.
Only "1 Month" and "3 Months" are kept - "Close" and "Make your own" are
skipped entirely.

If you haven't gotten past the my.telegram.org login step yet, you don't
need this file - use the /updateplans command in bot.py instead (paste the
plan text yourself, no API credentials needed).

Setup:
    pip install telethon
    Get API_ID / API_HASH from https://my.telegram.org
Run once manually first (with SHOW_RAW=True) to confirm the navigation
below actually matches lomesnetbot's real menu structure, then schedule it
hourly with cron. See README.md.
"""

import asyncio
from telethon import TelegramClient

import db
from plan_parser import parse_plan_detail_message
from config import MARKUP_MULTIPLIER, TARGET_BOT_USERNAME

# ---- fill these in ----
API_ID = 12345  # from my.telegram.org
API_HASH = "your_api_hash_here"
SESSION_NAME = "scraper_session"

# Only these two plan names (as they appear as buttons under Multi Location)
# get scraped - everything else, including "Make your own", is skipped.
WANTED_PLAN_BUTTONS = ["1 Month", "3 Months"]  # TODO: adjust to the bot's exact button text

SHOW_RAW = True

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def main():
    await client.start()
    db.init_db()

    plans = []

    async with client.conversation(TARGET_BOT_USERNAME, timeout=30) as conv:
        await conv.send_message("/start")
        resp = await conv.get_response()

        if SHOW_RAW:
            print("----- START MENU -----")
            print(resp.raw_text)
            if resp.buttons:
                for row in resp.buttons:
                    for b in row:
                        print(repr(b.text))

        # TODO: adjust button text below to match exactly what lomesnetbot shows
        resp = await resp.click(text="Buy")
        resp = await conv.get_response()

        if SHOW_RAW:
            print("----- AFTER 'Buy' -----")
            print(resp.raw_text)
            if resp.buttons:
                for row in resp.buttons:
                    for b in row:
                        print(repr(b.text))

        # Only go into Multi Location - "Close" is never clicked
        resp = await resp.click(text="Multi Location")
        resp = await conv.get_response()

        if SHOW_RAW:
            print("----- AFTER 'Multi Location' -----")
            print(resp.raw_text)
            if resp.buttons:
                for row in resp.buttons:
                    for b in row:
                        print(repr(b.text))

        # Click each wanted plan button, skip "Make your own" and anything
        # not in WANTED_PLAN_BUTTONS
        for row in resp.buttons or []:
            for b in row:
                if b.text not in WANTED_PLAN_BUTTONS:
                    continue
                detail_resp = await b.click()
                detail_resp = await conv.get_response()

                if SHOW_RAW:
                    print(f"----- DETAIL for '{b.text}' -----")
                    print(detail_resp.raw_text)

                parsed = parse_plan_detail_message(detail_resp.raw_text, MARKUP_MULTIPLIER)
                if parsed:
                    plans.append(parsed)
                else:
                    print(
                        f"Could not parse plan detail for '{b.text}' - adjust "
                        f"parse_plan_detail_message() in plan_parser.py to match the raw text above."
                    )

    if not plans:
        print("No plans parsed - see the raw text printed above and adjust the parser/navigation.")
        return

    import re as _re
    seen_keys = set()
    for p in plans:
        gb_match = _re.search(r"\d+", p.get("traffic", "") or "")
        traffic_gb = int(gb_match.group()) if gb_match else 0
        price = int(p["price"])
        db.upsert_plan(p["duration_days"], traffic_gb, price)
        seen_keys.add((p["duration_days"], traffic_gb))
        print(f"Synced plan: {p['duration_label']} / {traffic_gb}GB — your price {price:,}")

    db.deactivate_missing_plans(seen_keys)


if __name__ == "__main__":
    asyncio.run(main())
