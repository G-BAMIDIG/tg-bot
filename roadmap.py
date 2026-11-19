"""
Everything this bot could need, grouped like a notebook (25 sections x 20 ideas).
A leading "✓ " means it is already built. The dashboard's Roadmap page and
ROADMAP.md are both generated from this one list.
"""

_RAW = """
## 1. Customer experience
✓ Choose Persian or English on first start
✓ FAQ page from the main menu
✓ Per-platform How to Connect guides with videos
✓ Copy-ready subscription link (Get URL)
✓ Persian (Jalali) dates next to Gregorian
✓ Share-with-friends button
✓ Order history with live status
✓ "Best value" badge on the cheapest-per-GB plan
Welcome message with a short intro and rules
Terms-of-service acceptance on first start
Remember each customer's language across reinstalls
Persian-digit display option
Friendly error messages with a "contact support" button everywhere
Quick-reply buttons instead of typing wherever possible
Progress indicator in multi-step flows ("step 2 of 4")
Undo / cancel button inside every multi-step flow
Seasonal themes for the menu (Nowruz, Yalda)
Tips shown after delivery ("how to get the best speed")
Light "typing..." indicator on slow actions
Saved device preference so the right guide opens directly
## 2. Buying and checkout
✓ 1-month and 3-month plan menus with GB tiers
✓ Custom-plan handoff to support
✓ Subscription name with strict validation
✓ Optional discount code at checkout
Order summary screen before payment
Edit-order button (change plan without starting over)
Remember the last purchased plan for one-tap reorder
Suggested plan based on previous usage
Bundle deals (two subscriptions together)
Gift a subscription to another Telegram user
Buy for a friend using their @username
Cart with several subscriptions in one payment
Plan comparison table
Limited-time offers with a countdown
Stock limits on promotional plans
Waitlist when a plan is sold out
Pre-order for a future start date
Pause before the first connection
One-message checkout for returning customers
USD estimate shown next to Toman prices
## 3. Payments
✓ Card-to-card details with a copy-ready card number
✓ Gateway fee shown as its own line
✓ Receipt photo upload
Rotate between several bank cards
Show a different card per amount range
Online payment gateway (Zarinpal / IDPay)
Crypto payments (USDT TRC20)
Automatic payment confirmation instead of manual review
Detect duplicate receipt images
Read amount and time from receipt photos (OCR) to pre-check
Partial payments with a remaining balance
Payment link that can be forwarded to someone else
Payment reminder messages
Overpayment and underpayment handling
Instalment payments for long plans
Invoice PDF for businesses
Tax / VAT line when needed
Multi-currency price display
Payment method preference remembered
Receipt archive downloadable per customer
## 4. Invoices and timers
✓ Invoices expire after a set time
✓ Customer is told when an invoice expired
✓ Old payment buttons stop working after expiry
✓ Valid-until time printed on every invoice
Countdown shown on the invoice
Extend-invoice button, once
Different expiry per payment method
Re-price an expired invoice on request
Admin can extend one invoice by hand
Invoice numbering with a fixed format
Invoice status page the customer can open
Auto-cancel stuck "awaiting admin" orders after N days with a notice
Escalation when an order waits too long for review
Business-hours-aware expiry (don't expire overnight)
Warn customers 10 minutes before expiry
Reuse a still-valid unpaid invoice instead of making duplicates
Cancel-invoice button for the customer
Invoice history export
Time-zone aware expiry display per customer
Audit trail of every invoice state change
## 5. Subscriptions and renewals
✓ Update subscription: add months and/or data
✓ Minimum 1 month and 20-600 GB limits enforced
✓ Admin alert shows which order number is being updated
✓ Approval button applies the renewal and tells the customer
✓ Expiry reminder before a subscription ends
✓ Add a subscription by hand for customers who can't buy in the bot
One-tap renew for the same plan and price
Auto-renew opt-in with a reminder first
Grace period after expiry
Expired-subscription tab with a Renew button
Upgrade to a bigger plan with the price difference
Downgrade at the next renewal
Pause and resume a subscription
Transfer a subscription to another customer
Multiple configs per subscription
Rename a subscription after purchase
Revoke or disable a subscription from the admin side
Merge two subscriptions
Subscription notes visible only to admins
Bulk-extend all subscriptions after an outage
## 6. Data usage and notifications
✓ Admin records remaining data and the customer is notified
✓ Remaining data shown in My Subscriptions
Automatic usage sync from the VPN panel
Alert at 80% and 100% of data used
Daily or weekly usage summary opt-in
Usage graph image
Low-data alert with a "Top up" button
Speed tips when usage looks abnormal
Alert when data is nearly gone and expiry is close
Quiet hours for notifications
Per-customer notification preferences
Notification when a server is replaced
Notification when a new config link is available
Reminder to update the subscription inside the app
Expiry reminders at several intervals (7, 3, 1 days)
Notification history page
Handling for customers who blocked the bot
Fallback to SMS or email when Telegram fails
Admin digest of customers who blocked the bot
Auto-clean subscriptions of customers who left
## 7. Delivery and fulfilment
✓ Repeating alarm until the admin acknowledges
✓ Alarm resumes after a restart
✓ Seen / Deliver / Decline buttons on every order
✓ Estimated delivery time based on real history
✓ Delivered configs stored encrypted
✓ /pending resends actionable cards
Stock pool of pre-made configs handed out automatically
Panel API: create accounts automatically (no manual delivery)
Delivery by QR code image as well as link
Multiple delivery formats (link, file, QR)
Delivery checklist for the admin
Saved replies attached to configs
Second admin receives escalated alarms
Quiet-hours rules for the alarm
Delivery SLA tracking per day
Retry delivery if the customer's chat is unreachable
Config health check before sending
Region or server choice at delivery time
Auto-generate a name if the customer's is taken
Delivery confirmation button for the customer
## 8. Customer support
✓ Support contact via an @mention
✓ Admin can message any customer from the bot
✓ Star rating after delivery
Support tickets with numbers
Customers can reply to admin messages and have them forwarded
Canned reply templates
Auto-answers for common questions
Troubleshooting wizard by platform and symptom
Server status message customers can check
Known-issues banner on the menu
Escalation from the wizard to a human with context attached
Support hours shown on the support screen
Satisfaction survey after a ticket closes
Ticket categories and priorities
Internal notes on tickets
Merge duplicate tickets
Customers can attach screenshots to a ticket
Agent assignment for multi-agent support
Response-time statistics
Search through past conversations
## 9. Order management
✓ /order shows any order with its receipt
✓ Refunds recorded against an order
✓ Decline with a reason shown to the customer
✓ Pending list with working buttons
Preset decline reasons as one-tap buttons
Edit an order's price before approving
Split and merge orders
Re-open a declined order
Manual order creation for offline sales
Order notes
Order tags and filters
Bulk approve for trusted customers
Auto-approve for repeat customers under a limit
Order search by amount
Order search by date range
Order timeline view
Duplicate-order warning
Attach a second receipt to an order
Export orders to CSV
Scheduled order reports
## 10. Customer management
✓ /user profile with orders, spend, bans and subscriptions
✓ Ban and unban with reasons and a countdown
✓ Auto-flag customers with repeated declined receipts
✓ One-tap actions from a profile (message, ban, add subscription, usage)
Customer tags (VIP, reseller, trial)
Customer notes
Lifetime-value ranking
Merge duplicate accounts
Delete a customer's data on request
Saved customer segments for broadcasts
Reseller accounts with their own price tiers
Trusted-customer status that skips extra checks
Birthday and anniversary messages
Win-back messages for inactive customers
Customer import from a spreadsheet
Customer export
Tracking of customers who blocked the bot
Per-customer language override
Per-customer discount that applies automatically
Customer timeline of every action
## 11. Messaging and broadcasts
✓ Broadcast to everyone
✓ Direct message to one customer
Preview and confirm before broadcasting
Schedule a broadcast
Broadcast with photo, video or buttons
Broadcast to a segment (active, expired, never bought)
A/B test two broadcast texts
Broadcast delivery report with failures
Throttled sending to respect Telegram limits
Message templates with placeholders ({name}, {expiry})
Pinned announcements
Auto-post to a channel
Two-way broadcast replies routed to support
Opt-out for marketing messages
Message history per customer
Draft saving for long messages
Persian and English variants chosen per customer
Emergency broadcast shortcut for outages
Delivery-rate tracking
Link click tracking
## 12. Discounts and promotions
✓ Discount codes with a percentage
✓ Create, list and deactivate codes from Telegram
Usage limit per code
Expiry date per code
One use per customer
Fixed-amount discounts
Codes restricted to certain plans
Codes restricted to new customers
Auto-generated unique codes per customer
Stackable versus exclusive code rules
Flash sales on selected plans
Seasonal campaigns in one command
Happy-hour pricing
Volume discounts for multiple months
Loyalty points
Cashback toward future orders
Coupon performance report
Code suggestions when checkout is abandoned
Referral-only codes
Fraud checks on coupon abuse
## 13. Referral and growth
✓ Share-with-friends button
Personal referral links
Reward for the referrer and the new customer
Referral leaderboard
Referral fraud detection
Channel membership required before buying
Public reviews page
Testimonial collection after good ratings
Social-proof counters
Affiliate commissions
Ambassador program
Landing page with a Telegram deep link
Promo-link tracking per source
Welcome offer for first-time buyers
Win-back offers for expired customers
Abandoned-checkout reminders
Cross-sell a data top-up at renewal
Trial-to-paid conversion tracking
Referral link QR codes
Growth dashboard
## 14. Pricing and plans
✓ Plans and prices set from Telegram
✓ Renewal prices adjustable by command
Plan editor with buttons
Bulk price change by percent
Scheduled price changes
Per-country or per-route price lists
Plan descriptions editable from the bot
Plan ordering and highlighting
Hide and show plans without deleting
History of price changes
Cost tracking per plan for margin
Margin warnings when a price is too low
Currency-rate based auto-pricing
Customer-group pricing
Minimum order amounts
Rounding rules for prices
Traffic overage pricing
Unlimited-plan fair-use rules
Plan availability by time window
Price-change notifications to affected customers
## 15. Finance and reporting
✓ Stats command with revenue, refunds and ratings
✓ Revenue counted net of refunds
✓ Revenue charts by day and month
✓ Revenue by plan
Profit tracking with server costs
Expense entries
Monthly profit and loss report
Tax report
Daily revenue message
Weekly summary message
Cash-flow forecast from expiring subscriptions
Refund-rate monitoring
Average order value trend
Churn and retention report
Cohort analysis
Fee reconciliation with the bank statement
Bank-statement import to match receipts
Export to Excel
Scheduled financial reports
Read-only access for an accountant
## 16. Security and fraud
✓ Admin-only commands and buttons
✓ Alert when a non-admin tries an admin action
✓ Configs encrypted at rest
✓ Repeated declined receipts flag the customer
✓ One-time login links for the dashboard
Two-step confirmation for destructive actions
Admin action audit log
Multiple admins with roles and permissions
Password-encrypted backups
Secret rotation reminders
Receipt tampering hints (metadata checks)
Duplicate receipt detection across customers
Velocity checks (many orders in a short time)
Suspicious-name blocklist
Data retention policy with auto-purge
Customer data export and delete tools
Session list and revoke for the dashboard
Alert on unusual admin hours
Honeypot commands that flag scanners
Security checklist run at startup
## 17. Abuse protection
✓ Per-customer rate limiting
✓ Flood detection with an automatic temporary ban
✓ Banned customers get the reason and a countdown
✓ Commands always escape stuck conversation states
Captcha-style check for new accounts
Progressive penalties for repeat offenders
Shadow-ban mode
Spam keyword filter
Rate limits per action type
Limit on open unpaid invoices per customer
Cooldown between invoices
Block disposable-looking accounts
Appeals flow for banned customers
Auto-unban after good behavior
Abuse reports from customers
Admin alert thresholds that adapt
Abuse dashboard
Whitelist for trusted customers
Abuse scoring per account
Automated ban review queue
## 18. Reliability and operations
✓ Working-hours restriction with an on/off command
✓ Background jobs for expiry, reminders and backups
✓ Settings stored in the database so they survive restarts
✓ Anchored file paths so launching from another folder is safe
Health check command
Errors forwarded to the admin
Rotating log files
Webhook mode instead of polling
systemd service file
Docker image
Auto-restart watchdog
Startup config validation
Graceful shutdown that finishes in-flight orders
Maintenance mode with a custom message
Staging bot for testing changes
Automated tests for core flows
Version number and changelog command
Update checker
Resource usage alerts
Uptime monitoring with outside pings
## 19. Backups and recovery
✓ /backup sends the database on demand
✓ Automatic daily backup
Backups to a second location (cloud storage)
Backup retention and pruning
Backup verification (restore test)
One-command restore
Separate secure backup of the encryption key
Point-in-time recovery
Backup of settings and a .env template
Backup size and age monitoring
Alert when a backup fails
Export of everything to CSV
Disaster-recovery checklist
Migration script between servers
Read-only replica for reporting
Schema version tracking
Safe migrations with an automatic pre-migration backup
Data integrity checks
Archive of old orders
Backup encryption with a passphrase
## 20. Dashboard and GUI
✓ Admin-only web dashboard opened from Telegram
✓ Categorized sidebar with searchable, sortable tables
✓ Charts for revenue, sign-ups and order status
✓ Order and customer detail pages with receipts
✓ Roadmap page showing what's built
Actions from the dashboard (approve, decline, ban)
Live updates without refreshing
Dark and light theme switch
Saved filters and views
Export any table to CSV
Dashboard notifications
Map of customers by region
Plan editor in the browser
Broadcast composer in the browser
Receipt zoom and side-by-side compare
Keyboard shortcuts
Multi-admin login with roles
Mobile app wrapper
Public status page for customers
Customizable home widgets
## 21. Automation and panel integration
✓ Automatic expiry of unpaid invoices
✓ Automatic expiry reminders
Panel API integration (3x-ui / Marzban / Hiddify)
Create accounts automatically after payment
Sync usage from the panel hourly
Auto-disable expired accounts on the panel
Auto-extend on the panel when a renewal is approved
Reset traffic on renewal
Server load balancing at delivery
Server health checks with auto-removal
Automatic config rotation when a server is blocked
Webhooks for external systems
Zapier / n8n friendly API
Scheduled jobs page
Auto-reply rules
Auto-tagging customers by behavior
Auto-ban rules editable by the admin
Auto-approve rules
Event bus for new features
API for resellers
## 22. Localization and content
✓ Persian and English throughout
✓ Admin-editable FAQ and how-to text
Edit FAQ and guides from inside the bot
Arabic, Turkish, Russian and Kurdish translations
Right-to-left polish for every message
Per-language plan descriptions
Localized dates and numbers everywhere
Translation review tool
Rich text templates
Video guides with fallbacks if a file id expires
Screenshot guides per app version
Auto-detect language from the Telegram profile
Seasonal greetings
Tone settings (formal or friendly)
Message A/B testing
Emoji style presets
Glossary for consistent wording
Content versioning
Preview a message as a customer would see it
Missing-translation warnings
## 23. Accessibility and UX polish
Shorter messages for small screens
Consistent button ordering
Large-tap-target layouts
Screen-reader friendly wording
Reduced-emoji mode
Copy-then-paste instructions that work offline
Clear loading and success states
Consistent back and cancel behavior
Confirmation before irreversible actions
Smart defaults in every form
Auto-fill suggestions for subscription names
Input validation with examples
Gentle correction of common typos
Number input in Persian or English digits
Copy-ready blocks for anything the customer must paste
Message editing instead of sending new messages
Clean-up of old bot messages
Pinned quick-help message
Usability testing checklist
Feedback button on every screen
## 24. Analytics and insights
✓ Orders by status overview
Funnel: start, plan, name, pay, receipt, delivered
Drop-off report per step
Best-selling plans over time
Peak-hour heatmap
Average delivery time trend
Customer acquisition sources
Retention curve
Revenue per customer
Discount impact on revenue
Refund and decline reasons breakdown
Rating trend
Support load by topic
Forecast of renewals due
Seasonality charts
Anomaly alerts (sudden drop in orders)
Experiment framework
Custom report builder
Weekly insights message to the admin
Benchmark against your own history
## 25. Business and legal
Terms of service and refund policy texts
Privacy policy and data-handling notes
Acceptable-use rules
Complaint handling procedure
Customer data export on request
Right-to-delete workflow
Reseller agreement template
Invoice and receipt templates
Business-hours announcement
Holiday schedule with automatic notices
Status and incident communication templates
Onboarding guide for new support staff
Staff roles and responsibilities
Training checklist
Operating runbook (what to do when X breaks)
Vendor and server provider tracking
Domain and certificate renewal reminders
Cost tracking for your own tools
Growth goals and KPIs
Quarterly review checklist
"""


def parsed():
    """[(category, [(text, built_bool), ...]), ...]"""
    out, cur = [], None
    for line in _RAW.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            cur = (line[3:], [])
            out.append(cur)
        else:
            built = line.startswith("✓ ")
            cur[1].append((line[2:] if built else line, built))
    return out


def total_count():
    return sum(len(items) for _, items in parsed())


def built_count():
    return sum(1 for _, items in parsed() for _, b in items if b)


def to_markdown():
    lines = ["# Needs & ideas", "",
             f"{built_count()} of {total_count()} are built. ✅ = built, ⬜ = not yet.", ""]
    for cat, items in parsed():
        done = sum(1 for _, b in items if b)
        lines += [f"## {cat} ({done}/{len(items)})", ""]
        lines += [f"- {'✅' if b else '⬜'} {text}" for text, b in items]
        lines.append("")
    return "\n".join(lines)
