TEXT = {
    "choose_lang": {
        "en": "Please choose your language:",
        "fa": "لطفا زبان خود را انتخاب کنید:",
    },
    "main_menu": {
        "en": "Main menu — what would you like to do?",
        "fa": "منوی اصلی — چه کاری می‌خواهید انجام دهید؟",
    },
    "btn_buy": {"en": "🛒 Buy Subscription", "fa": "🛒 خرید اشتراک"},
    "btn_howto": {"en": "📖 How to Connect", "fa": "📖 آموزش اتصال"},
    "btn_support": {"en": "🆘 Support", "fa": "🆘 پشتیبانی"},
    "btn_mysubs": {"en": "📦 My Subscriptions", "fa": "📦 اشتراک‌های من"},
    "btn_faq": {"en": "❓ FAQ", "fa": "❓ سوالات متداول"},
    "btn_back": {"en": "⬅️ Back", "fa": "⬅️ بازگشت"},
    "btn_finalize": {"en": "✅ Finalize purchase", "fa": "✅ نهایی کردن خرید"},
    "btn_sent_receipt": {"en": "📎 Send Receipt", "fa": "📎 ارسال رسید"},
    "btn_custom_plan": {"en": "✨ Custom Plan", "fa": "✨ طرح سفارشی"},
    "btn_1month": {"en": "1️⃣ 1 Month", "fa": "1️⃣ ۱ ماهه"},
    "btn_3months": {"en": "3️⃣ 3 Months", "fa": "3️⃣ ۳ ماهه"},
    "btn_ok": {"en": "👌 OK", "fa": "👌 باشه"},
    "btn_get_url": {"en": "🔗 Get URL", "fa": "🔗 دریافت لینک"},

    # Support: no button, no phone number - just a tappable @mention in the
    # text itself, which Telegram auto-links on its own.
    "support_msg": {
        "en": "You can reach support here: @{support_username}",
        "fa": "می‌توانید از طریق زیر با پشتیبانی در تماس باشید: @{support_username}",
    },

    "no_subs": {
        "en": "You don't have any active subscriptions yet.",
        "fa": "شما هیچ اشتراک فعالی ندارید.",
    },
    "subs_header": {"en": "📦 Your active subscriptions:", "fa": "📦 اشتراک‌های فعال شما:"},
    "sub_line": {
        "en": "• {name} — expires {end_date}",
        "fa": "\u200f• {name} — تاریخ انقضا {end_date}",
    },

    "no_plans": {
        "en": "No plans available right now, please check back later.",
        "fa": "در حال حاضر پلنی موجود نیست، لطفا بعدا دوباره امتحان کنید.",
    },
    "choose_category": {
        "en": "What would you like to buy?",
        "fa": "چه چیزی می‌خواهید بخرید؟",
    },
    "choose_plan": {"en": "Choose a plan:", "fa": "یک پلن را انتخاب کنید:"},
    "custom_plan_msg": {
        "en": "For this type of plan, you'll need to talk to support directly.",
        "fa": "برای این نوع اشتراک، باید مستقیم با پشتیبانی صحبت کنید.",
    },
    "product_brand_name": {
        "en": "🚀 Multi Location Special",
        "fa": "🚀 مولتی لوکیشن ویژه",
    },

    "plan_selected": {
        "fa": (
            "📌 اشتراک انتخابی شما به شرح زیر میباشد 👇\n\n"
            "🛍 GVPNاسم محصول: <b>{product_name}</b>\n"
            "⏳ مدت زمان: <b>{duration_label}</b>\n"
            "♾ مقدار ترافیک: <b>{traffic}</b>\n\n"
            "💳 قیمت: <b>{price}</b>\n\n"
            "🔸 اتصال با پروتکل‌های پیشرفته\n"
            "🔹 سرعت و پایداری بالا\n"
            "🔸 امکان استفاده نامحدود کاربر\n"
            "🔹 بروزرسانی روزانه سرورها\n"
            "🔸 پشتیبانی توسط تیم حرفه‌ای\n"
            "🔹 مناسب گیم، استریم، ترید و ...\n\n"
            "⭐️ شما میتوانید به مرحله قبل برگردید و اشتراک خود را تغییر دهید یا از "
            "همین مرحله خرید خود را نهایی کنید.\n\n"
            "〰️〰️〰️〰️〰️\n"
            "🚀 @GAvpn_bot"
        ),
        "en": (
            "📌 Your selected subscription is as follows 👇\n\n"
            "🛍 GVPN Product: <b>{product_name}</b>\n"
            "⏳ Duration: <b>{duration_label}</b>\n"
            "♾ Traffic: <b>{traffic}</b>\n\n"
            "💳 Price: <b>{price}</b>\n\n"
            "🔸 Advanced protocol connection\n"
            "🔹 High speed and stability\n"
            "🔸 Unlimited concurrent use\n"
            "🔹 Daily server updates\n"
            "🔸 Professional support team\n"
            "🔹 Great for gaming, streaming, trading and more\n\n"
            "⭐️ You can go back to change your subscription, or finalize your "
            "purchase from here.\n\n"
            "〰️〰️〰️〰️〰️\n"
            "🚀 @GAvpn_bot"
        ),
    },

    # exact rules you gave, cleaned up (the `.` was a stray artifact, not a
    # real placeholder - removing it fixes the grammar)
    "ask_username": {
        "fa": (
            "📝 جهت تغییر نام اشتراک، نام مورد نظر خود را ارسال کنید\n\n"
            "📌 مثال: sub1\n\n"
            "⚠️ توجه: نام ارسالی باید بین 5 تا 15 کاراکتر و فقط شامل اعداد و حروف انگلیسی باشد"
        ),
        "en": (
            "📝 To set your subscription name, send your desired name now.\n\n"
            "📌 Example: sub1\n\n"
            "⚠️ Note: the name must be between 5 and 15 characters, English letters "
            "and numbers only."
        ),
    },
    "ask_username_invalid": {
        "en": "❌ That doesn't match the rules — 5 to 15 characters, English letters and numbers only. Try again:",
        "fa": "❌ این نام با قوانین مطابقت ندارد — بین 5 تا 15 کاراکتر، فقط حروف انگلیسی و اعداد. دوباره ارسال کنید:",
    },

    "ask_discount": {
        "en": "🎟 Have a discount code? Send it now, or tap Skip.",
        "fa": "🎟 کد تخفیف دارید؟ همین الان ارسال کنید یا روی «رد شدن» بزنید.",
    },
    "btn_skip_discount": {"en": "⏭ Skip", "fa": "⏭ رد شدن"},
    "discount_invalid": {
        "en": "❌ Invalid or expired discount code. Try another one, or tap Skip.",
        "fa": "❌ کد تخفیف نامعتبر یا منقضی‌شده است. کد دیگری امتحان کنید یا روی «رد شدن» بزنید.",
    },
    "discount_line_fragment": {
        "en": "🏷 Discount ({percent}%): -{amount} Toman (T)\n",
        "fa": "\u200f🏷 تخفیف ({percent}%): -{amount} تومان (T)\n",
    },

    # order invoice - plan price + gateway fee shown separately, total is
    # what's actually charged
    "order_invoice": {
        "fa": (
            "✅ سفارش شما با موفقیت ثبت شد.\n\n"
            "🛍 محصول: <b>{product_name}</b>\n"
            "⏳ مدت زمان: <b>{duration_label}</b>\n"
            "♾ مقدار ترافیک: <b>{traffic}</b>\n"
            "🏷 نام اشتراک: <b>{sub_name}</b>\n\n"
            "💵 قیمت پلن: {plan_price} تومان (T)\n"
            "{discount_line}"
            "🪙 کارمزد درگاه ({fee_percent}%): {fee} تومان (T)\n"
            "💸 مبلغ نهایی قابل پرداخت: <b>{total} تومان (T)</b>\n\n"
            "💳 لطفاً مبلغ <code>{total}</code> تومان را به شماره کارت پایین واریز کنید.\n\n"
            "🔢 شماره کارت مقصد:\n"
            "<code>{card_number}</code>\n"
            "👤 به نام: {card_holder}\n\n"
            "⚠️ مبلغ را دقیق و بدون تغییر واریز کنید.\n\n"
            "{valid_line}"
            "〰️〰️〰️〰️〰️\n"
            "🚀 @GAvpn_bot"
        ),
        "en": (
            "✅ Your order was created successfully.\n\n"
            "🛍 Product: <b>{product_name}</b>\n"
            "⏳ Duration: <b>{duration_label}</b>\n"
            "♾ Traffic: <b>{traffic}</b>\n"
            "🏷 Subscription name: <b>{sub_name}</b>\n\n"
            "💵 Plan price: {plan_price} Toman (T)\n"
            "{discount_line}"
            "🪙 Gateway fee ({fee_percent}%): {fee} Toman (T)\n"
            "💸 Total amount due: <b>{total} Toman (T)</b>\n\n"
            "💳 Please deposit exactly <code>{total}</code> Toman to the card below.\n\n"
            "🔢 Destination card number:\n"
            "<code>{card_number}</code>\n"
            "👤 Holder: {card_holder}\n\n"
            "⚠️ Deposit the exact amount, unchanged.\n\n"
            "{valid_line}"
            "〰️〰️〰️〰️〰️\n"
            "🚀 @GAvpn_bot"
        ),
    },

    "ask_send_receipt": {
        "en": "Please send a photo/screenshot of your payment receipt now.",
        "fa": "لطفا عکس رسید پرداخت خود را ارسال کنید.",
    },
    "order_placed": {
        "en": "✅ Your order has been placed. Please wait while admins work on it.",
        "fa": "✅ سفارش شما ثبت شد. لطفا منتظر بمانید تا ادمین‌ها کار را انجام دهند.",
    },
    "admin_working": {
        "en": "⏳ Admins are working on your order, please wait...",
        "fa": "⏳ ادمین‌ها در حال بررسی سفارش شما هستند، لطفا صبر کنید...",
    },
    "subscription_ready": {
        "en": (
            "🎉 Your subscription is ready!\n\n"
            "Name: {sub_name}\n"
            "Plan: {plan_name}\n"
            "Expires: {end_date} ({jalali_date})\n\n"
            "{config}"
        ),
        "fa": (
            "🎉 اشتراک شما آماده است!\n\n"
            "نام: {sub_name}\n"
            "پلن: {plan_name}\n"
            "تاریخ انقضا: {end_date} ({jalali_date})\n\n"
            "{config}"
        ),
    },

    "bot_closed": {
        "en": "🕙 We're currently closed. Our bot is available from {open_hour}:00 to 23:59. Please come back then!",
        "fa": "🕙 در حال حاضر تعطیل هستیم. ربات از ساعت {open_hour}:۰۰ تا ۲۳:۵۹ فعال است. لطفا بعدا مراجعه کنید!",
    },

    "choose_platform": {
        "en": "Which platform are you connecting from?",
        "fa": "از کدام پلتفرم متصل می‌شوید؟",
    },

    # ban / unban (user-facing, localized)
    "banned_notice": {
        "en": (
            "🚫 You have been banned.\n\n"
            "Reason: {reason}\n"
            "Duration: banned by the admin\n"
            "Time remaining: {remaining}"
        ),
        "fa": (
            "🚫 شما مسدود شده‌اید.\n\n"
            "دلیل: {reason}\n"
            "توسط ادمین مسدود شده‌اید\n"
            "زمان باقی‌مانده: {remaining}"
        ),
    },
    "unbanned_notice": {
        "en": "✅ You have been unbanned and can use the bot again.",
        "fa": "✅ مسدودیت شما برداشته شد و می‌توانید دوباره از ربات استفاده کنید.",
    },

    # admin-facing (English only - MUST be {"en": ...} dicts, t() always does
    # TEXT[key][lang]. A bare string here was the earlier crash bug.)
    "admin_new_order": {
        "en": (
            "🚨 ORDER! ORDER! 🚨\n\n"
            "Order #{order_id}\n"
            "User: @{username} (id {user_id})\n"
            "Plan: {plan_name}\n"
            "Subscription name: {sub_name}\n"
            "Total price: {price} Toman\n"
            "{flag_line}"
        )
    },
    "admin_ask_config": {
        "en": "Send the subscription config/link for order #{order_id} now. This will be forwarded to the user."
    },
    "admin_delivered": {
        "en": "✅ Delivered order #{order_id} to the user."
    },
    "admin_ask_decline_reason": {
        "en": "Why are you declining order #{order_id}? Send the reason now — this exact text will be shown to the customer:"
    },
    "admin_declined": {
        "en": "❌ Declined order #{order_id}. The customer has been notified.\nReason: {reason}"
    },
    "order_declined": {
        "en": (
            "❌ Your order has been declined by the admin.\n\n"
            "Reason: {reason}\n\n"
            "If you have questions, contact Support from the main menu."
        ),
        "fa": (
            "❌ سفارش شما توسط ادمین رد شد.\n\n"
            "دلیل: {reason}\n\n"
            "اگر سوالی دارید از منوی اصلی با پشتیبانی تماس بگیرید."
        ),
    },
    "admin_pending_header": {"en": "📋 Orders awaiting delivery:\n"},
    "admin_pending_none": {"en": "✅ No orders are currently waiting on you."},
    "admin_pending_line": {
        "en": "• Order #{order_id} — @{username} (id {user_id}) — {plan_name} — {price} Toman — since {created_at}\n"
    },
    "admin_stats": {
        "en": (
            "📊 Stats\n\n"
            "👥 Users: {users}\n"
            "🧾 Total orders: {total_orders}\n"
            "✅ Delivered orders: {delivered_orders}\n"
            "💰 Total revenue (delivered): {revenue} Toman\n"
            "⏳ Pending your action: {pending_orders}\n"
            "📦 Active subscriptions: {active_subscriptions}\n"
            "💸 Refunded so far: {refunded_total} Toman\n"
            "⭐ Average rating: {rating_text}\n"
        )
    },
    "admin_new_renewal": {
        "en": (
            "🔄 RENEWAL REQUEST! 🔄\n\n"
            "Order #{order_id} — update of order #{orig_order}\n"
            "User: @{username} (id {user_id})\n"
            "Subscription: {sub_name}\n"
            "Extra time: {time_value}\n"
            "Extra data: {gb_value}\n"
            "Total paid: {price} Toman\n"
            "{flag_line}\n"
            "👉 Apply this on your panel first, then tap Approve."
        )
    },
    "slow_down": {"en": "⏳ Please slow down a little.", "fa": "⏳ لطفاً کمی آهسته‌تر."},
    "admin_broadcast_usage": {
        "en": "Usage: /broadcast <message>\n\nSends the message to every user who has started the bot."
    },
    "admin_broadcast_done": {
        "en": "📣 Broadcast sent to {sent} users ({failed} failed - likely blocked the bot)."
    },

    # admin ban flow
    "admin_ban_ask_target": {
        "en": "Who do you want to ban? Send their numeric user ID, or their @username (only works if they've messaged this bot before)."
    },
    "admin_ban_target_not_found": {
        "en": "I don't recognize that user — they need to have started this bot at least once before I can ban them."
    },
    "admin_ban_prior_record": {
        "en": "📋 This person has been banned {count} time(s) before."
    },
    "admin_ban_ask_duration": {
        "en": "How long should the ban last? Send a number of hours (e.g. 24), or with a suffix like 3d or 12h."
    },
    "admin_ban_invalid_duration": {
        "en": "Couldn't read that as a duration. Try something like 24, 24h, or 3d:"
    },
    "admin_ban_ask_reason": {"en": "Why is this person being banned? Send the reason:"},
    "admin_ban_done": {
        "en": "🚫 Banned user {user_id} for {duration} — reason: {reason}. Unbanned at: {until} UTC."
    },
    "admin_unban_ask_target": {
        "en": "Who do you want to unban? Send their numeric user ID, or their @username."
    },
    "admin_unban_not_banned": {
        "en": "This person is not currently banned — nothing to do."
    },
    "admin_unban_done": {"en": "✅ Unbanned user {user_id}."},

    # ---------- newer features ----------
    "btn_myorders": {"en": "📋 My Orders", "fa": "📋 سفارش‌های من"},
    "btn_share": {"en": "📣 Share with friends", "fa": "📣 معرفی به دوستان"},
    "btn_share_now": {"en": "📤 Share", "fa": "📤 ارسال به دوستان"},
    "share_msg": {
        "en": "Tap below to send the bot to your friends 👇",
        "fa": "برای ارسال ربات به دوستانتان روی دکمه زیر بزنید 👇",
    },
    "share_text": {
        "en": "Fast and stable VPN — try it here:",
        "fa": "فیلترشکن سریع و پایدار — از اینجا امتحان کنید:",
    },
    "btn_update_sub": {"en": "🔄 Update subscription", "fa": "🔄 تمدید / افزایش حجم"},
    "badge_best_value": {"en": "⭐ Best value", "fa": "⭐ به‌صرفه‌ترین"},

    "myorders_header": {"en": "📋 Your recent orders:\n\n", "fa": "📋 آخرین سفارش‌های شما:\n\n"},
    "myorders_none": {"en": "You don't have any orders yet.", "fa": "هنوز سفارشی ثبت نکرده‌اید."},
    "myorders_line": {
        "en": "• #{id} — {what} — {price} Toman\n   {status}\n",
        "fa": "\u200f• #{id} — {what} — {price} تومان\n   {status}\n",
    },
    "order_kind_renewal": {"en": "🔄 Update of {sub_name}", "fa": "🔄 تمدید {sub_name}"},
    "status_awaiting_receipt": {"en": "⏳ Waiting for your receipt", "fa": "⏳ در انتظار ارسال رسید"},
    "status_awaiting_admin": {"en": "🔍 Under review", "fa": "🔍 در حال بررسی"},
    "status_delivered": {"en": "✅ Delivered", "fa": "✅ تحویل داده شد"},
    "status_declined": {"en": "❌ Declined", "fa": "❌ رد شد"},
    "status_expired": {"en": "⌛ Expired (not paid in time)", "fa": "⌛ منقضی شد (پرداخت نشد)"},
    "status_refunded": {"en": "💸 Refunded", "fa": "💸 بازگشت وجه"},

    # invoice timer
    "invoice_valid_line": {
        "en": "⏳ This invoice is valid for {minutes} minutes (until {until}). After that it expires, because prices may change.\n\n",
        "fa": "⏳ این فاکتور {minutes} دقیقه (تا ساعت {until}) اعتبار دارد. پس از آن منقضی می‌شود، چون ممکن است قیمت‌ها تغییر کنند.\n\n",
    },
    "invoice_expired": {
        "en": "⌛ This invoice has expired. Prices may have changed, so please start a new order from the main menu.",
        "fa": "⌛ این فاکتور منقضی شده است. ممکن است قیمت‌ها تغییر کرده باشند، لطفاً از منوی اصلی سفارش جدیدی ثبت کنید.",
    },
    "invoice_expired_notify": {
        "en": "⌛ Your invoice #{order_id} expired because no receipt was sent within {minutes} minutes. Prices may change, so please start a new order from the main menu.",
        "fa": "⌛ فاکتور شماره {order_id} منقضی شد، چون ظرف {minutes} دقیقه رسیدی ارسال نشد. ممکن است قیمت‌ها تغییر کنند، لطفاً از منوی اصلی سفارش جدیدی ثبت کنید.",
    },
    "order_not_payable": {
        "en": "ℹ️ This order is no longer waiting for payment.",
        "fa": "ℹ️ این سفارش دیگر در انتظار پرداخت نیست.",
    },
    "delivery_eta": {
        "en": "🕐 Usually delivered in about {eta} minutes.",
        "fa": "🕐 معمولاً حدود {eta} دقیقه طول می‌کشد.",
    },

    # rating
    "rating_prompt": {
        "en": "⭐ How was your experience with order #{order_id}? Tap a rating:",
        "fa": "⭐ تجربه شما از سفارش شماره {order_id} چطور بود؟ یک امتیاز انتخاب کنید:",
    },
    "rating_thanks": {"en": "Thank you for your feedback! {stars}", "fa": "ممنون از بازخورد شما! {stars}"},
    "rating_already": {"en": "You've already rated this order.", "fa": "قبلاً به این سفارش امتیاز داده‌اید."},

    # renewals
    "renew_intro": {
        "en": (
            "🔄 Update subscription «{sub_name}»\n\n"
            "You can extend its time (minimum 1 month) and/or add more data "
            "(minimum {min_gb} GB, maximum {max_gb} GB).\n\n"
            "⏳ First, how many months do you want to add?"
        ),
        "fa": (
            "🔄 بروزرسانی اشتراک «{sub_name}»\n\n"
            "می‌توانید زمان آن را تمدید کنید (حداقل ۱ ماه) و/یا حجم اضافه بخرید "
            "(حداقل {min_gb} و حداکثر {max_gb} گیگابایت).\n\n"
            "⏳ ابتدا بگویید چند ماه تمدید می‌خواهید؟"
        ),
    },
    "btn_months_skip": {"en": "⏭ No time extension", "fa": "⏭ بدون تمدید زمان"},
    "btn_gb_skip": {"en": "⏭ No extra data", "fa": "⏭ بدون حجم اضافه"},
    "renew_ask_gb": {
        "en": "📶 How much data do you want to add?\nSend a number from {min_gb} to {max_gb} (GB), or tap an option below.",
        "fa": "📶 چقدر حجم اضافه می‌خواهید؟\nعددی بین {min_gb} تا {max_gb} (گیگابایت) بفرستید یا یکی از گزینه‌ها را بزنید.",
    },
    "renew_gb_invalid": {
        "en": "❌ Send a whole number between {min_gb} and {max_gb} (GB).",
        "fa": "❌ یک عدد صحیح بین {min_gb} تا {max_gb} (گیگابایت) بفرستید.",
    },
    "renew_nothing": {
        "en": "⚠️ You skipped both. Please choose at least a time extension or some extra data.",
        "fa": "⚠️ هر دو را رد کردید. لطفاً حداقل تمدید زمان یا حجم اضافه را انتخاب کنید.",
    },
    "renew_line_time": {"en": "⏳ Extra time: <b>{value}</b>\n", "fa": "⏳ زمان اضافه: <b>{value}</b>\n"},
    "renew_line_data": {"en": "📶 Extra data: <b>{value}</b>\n", "fa": "📶 حجم اضافه: <b>{value}</b>\n"},
    "renew_invoice": {
        "fa": (
            "✅ درخواست بروزرسانی شما ثبت شد.\n\n"
            "🏷 اشتراک: <b>{sub_name}</b> (سفارش شماره {orig_order})\n"
            "{extra_lines}\n"
            "💵 قیمت: {plan_price} تومان (T)\n"
            "🪙 کارمزد درگاه ({fee_percent}%): {fee} تومان (T)\n"
            "💸 مبلغ نهایی قابل پرداخت: <b>{total} تومان (T)</b>\n\n"
            "💳 لطفاً مبلغ <code>{total}</code> تومان را به شماره کارت پایین واریز کنید.\n\n"
            "🔢 شماره کارت مقصد:\n"
            "<code>{card_number}</code>\n"
            "👤 به نام: {card_holder}\n\n"
            "⚠️ مبلغ را دقیق و بدون تغییر واریز کنید.\n\n"
            "{valid_line}"
            "〰️〰️〰️〰️〰️\n"
            "🚀 @GAvpn_bot"
        ),
        "en": (
            "✅ Your update request was created.\n\n"
            "🏷 Subscription: <b>{sub_name}</b> (order #{orig_order})\n"
            "{extra_lines}\n"
            "💵 Price: {plan_price} Toman (T)\n"
            "🪙 Gateway fee ({fee_percent}%): {fee} Toman (T)\n"
            "💸 Total amount due: <b>{total} Toman (T)</b>\n\n"
            "💳 Please deposit exactly <code>{total}</code> Toman to the card below.\n\n"
            "🔢 Destination card number:\n"
            "<code>{card_number}</code>\n"
            "👤 Holder: {card_holder}\n\n"
            "⚠️ Deposit the exact amount, unchanged.\n\n"
            "{valid_line}"
            "〰️〰️〰️〰️〰️\n"
            "🚀 @GAvpn_bot"
        ),
    },
    "renew_done": {
        "en": (
            "🎉 Your subscription «{sub_name}» was updated!\n\n"
            "{lines}"
            "⏳ New expiry: {end_date} ({jalali_date})\n\n"
            "🔃 Tip: open your VPN app and update the subscription to see the change.\n"
            "(Order #{order_id})"
        ),
        "fa": (
            "🎉 اشتراک «{sub_name}» بروزرسانی شد!\n\n"
            "{lines}"
            "⏳ تاریخ انقضای جدید: {end_date} ({jalali_date})\n\n"
            "🔃 نکته: برنامه‌ی VPN را باز کنید و اشتراک را بروزرسانی کنید تا تغییر را ببینید.\n"
            "(سفارش شماره {order_id})"
        ),
    },
    "sub_remaining": {
        "en": " — 📶 {gb} GB left",
        "fa": " — 📶 {gb} گیگ باقی‌مانده",
    },
    "reminder_expiring": {
        "en": "⏳ Your subscription «{sub_name}» expires in {when} ({end_date} / {jalali_date}).\nTap below to renew it or add more data.",
        "fa": "⏳ اشتراک «{sub_name}» تا {when} دیگر ({end_date} / {jalali_date}) منقضی می‌شود.\nبرای تمدید یا افزایش حجم روی دکمه زیر بزنید.",
    },
    "usage_notice": {
        "en": "📶 Heads up! Your subscription «{sub_name}» has {remaining} GB of data left{of_total}.",
        "fa": "📶 اطلاع‌رسانی: از اشتراک «{sub_name}» شما {remaining} گیگابایت حجم باقی مانده است{of_total}.",
    },
    "no_link_yet": {"en": "No link is stored for this subscription yet.", "fa": "هنوز لینکی برای این اشتراک ثبت نشده است."},
    "refund_notice": {
        "en": "💸 A refund of {amount} Toman was recorded for order #{order_id}.\nReason: {reason}",
        "fa": "💸 بازگشت وجه {amount} تومان برای سفارش شماره {order_id} ثبت شد.\nدلیل: {reason}",
    },


    # admin -> user direct message
    "admin_message_to_user": {
        "en": "📩 Message from support:\n\n{text}",
        "fa": "📩 پیام از طرف پشتیبانی:\n\n{text}",
    },
    "admin_msg_ask_target": {
        "en": "Who do you want to message? Send their numeric user ID or @username (they must have started this bot before)."
    },
    "admin_msg_target_not_found": {
        "en": "I don't recognize that user — they need to have started this bot at least once."
    },
    "admin_msg_ask_text": {"en": "What should the message say? Send the text now:"},
    "admin_msg_empty": {"en": "That was empty — send the message text:"},
    "admin_msg_sent": {"en": "✅ Message sent to user {user_id} (@{username})."},
    "admin_msg_failed": {
        "en": "❌ Couldn't deliver to user {user_id} — they may have blocked the bot."
    },

    # admin discount management
    "admin_discount_ask_code": {
        "en": "What should the discount code be? (e.g. SAVE10) Send it now:"
    },
    "admin_discount_ask_percent": {
        "en": "What percent off should '{code}' give? Send a number from 1 to 100:"
    },
    "admin_discount_invalid_percent": {
        "en": "Send a whole number between 1 and 100:"
    },
    "admin_discount_created": {
        "en": "✅ Discount code '{code}' created — {percent}% off, active immediately."
    },
    "admin_discounts_list_empty": {"en": "No active discount codes right now."},
    "admin_discounts_list_header": {"en": "🎟 Active discount codes:\n"},
    "admin_discounts_list_line": {"en": "• {code} — {percent}% off\n"},
    "admin_removediscount_usage": {"en": "Usage: /removediscount <code>"},
    "admin_discount_removed": {"en": "✅ Deactivated discount code '{code}'."},
    "admin_discount_not_found": {"en": "No active discount code called '{code}'."},
}


def t(key, lang, **kwargs):
    s = TEXT[key][lang]
    return s.format(**kwargs) if kwargs else s
