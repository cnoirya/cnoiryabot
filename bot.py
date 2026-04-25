import logging
import os
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ── airtable config ───────────────────────────────────────────────────────────
AIRTABLE_API_KEY = "patEQZVaqPtlubFu0.084f1467591118d0e66f2fe6dabecf9cd72faaf531e0720aa1e8f7bc7bda6ff6"
AIRTABLE_BASE_ID = "appo4hTdhoi16wWFW"
AIRTABLE_TABLE_ID = "tblZAjJoedwqxzoNq"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"

# ── pricing data ──────────────────────────────────────────────────────────────
FORMATS = {
    "text": 100,
    "message": 100,
    "response": 100,
    "auto-message": 100,
    "screen-capture": 106,
    "audio / min": 104,
    "live-stream / min": 105,
    "photo": 108,
    "priority-list": 108,
    "audio-call / min": 110,
    "video / min": 112,
    "community": 112,
    "video-call / min": 129.5,
}

LEVELS = {
    "sfw": 1.0,
    "nsfw": 1.1,
}

EXCLUSIVITY = {
    "paid": 1.0,
    "private": 1.2,
    "custom": 1.5,
}

PERSONALIZATION = {
    "generic": 1.0,
    "semi-custom": 1.3,
    "fully-custom": 1.8,
}

INTERACTIVITY = {
    "one-way": 1.0,
    "two-way": 1.3,
}

CAPTION = {
    "no caption": 1.0,
    "with caption": 1.05,
}

URGENCY = {
    "no urgency": 0,
    "urgent (sfw)": 250,
    "urgent (nsfw)": 455,
}

# hardcoded to avoid rounding issues
URGENCY_STARS = {
    "no urgency": 0,
    "urgent (sfw)": 19230,   # 250 × 76.92
    "urgent (nsfw)": 35000,  # exact
}

STEPS = ["format", "level", "exclusivity", "personalization", "interactivity", "caption", "urgency"]
STEP_DATA = {
    "format": FORMATS,
    "level": LEVELS,
    "exclusivity": EXCLUSIVITY,
    "personalization": PERSONALIZATION,
    "interactivity": INTERACTIVITY,
    "caption": CAPTION,
    "urgency": URGENCY,
}
STEP_TITLES = {
    "format": "select content format",
    "level": "select content level",
    "exclusivity": "select exclusivity",
    "personalization": "select personalization",
    "interactivity": "select interactivity",
    "caption": "add caption?",
    "urgency": "add urgency? (billed separately)",
}

# 1 star = $0.013 usd → 1 usd = 76.92 stars
USD_TO_STARS = 76.92

DISCLAIMER = (
    "\n\n⚠️ *all sales are final.*\n"
    "no refunds. no returns.\n"
    "requester will be contacted shortly via telegram."
)

def calculate_price(selections: dict) -> tuple[float, int, float]:
    """returns (base_usd, stars, urgency_usd)"""
    base = FORMATS[selections["format"]]
    multiplier = (
        LEVELS[selections["level"]]
        * EXCLUSIVITY[selections["exclusivity"]]
        * PERSONALIZATION[selections["personalization"]]
        * INTERACTIVITY[selections["interactivity"]]
        * CAPTION[selections["caption"]]
    )
    base_usd = round(base * multiplier, 2)
    urgency_usd = URGENCY[selections["urgency"]]
    stars = max(1, round(base_usd * USD_TO_STARS))
    return base_usd, stars, urgency_usd

def build_keyboard(step: str, prefix: str) -> InlineKeyboardMarkup:
    data = STEP_DATA[step]
    buttons = [[InlineKeyboardButton(label, callback_data=f"{prefix}|{step}|{label}")] for label in data]
    return InlineKeyboardMarkup(buttons)

def build_summary(selections: dict, base_usd: float, stars: int, urgency_usd: float, note: str = "") -> str:
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "📋 *order summary*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for step in STEPS:
        lines.append(f"• *{step}:* {selections[step]}")
    if note:
        lines.append(f"• *note:* {note}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⭐ *stars:* {stars:,}  (~${base_usd:,.2f} usd)")
    if urgency_usd > 0:
        lines.append(f"⚡ *urgency add-on:* ${urgency_usd:,.2f} usd _(billed separately)_")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(DISCLAIMER)
    return "\n".join(lines)

# ── airtable ──────────────────────────────────────────────────────────────────
async def save_to_airtable(user_id: int, username: str, selections: dict, base_usd: float, stars: int, urgency_usd: float, note: str = "", status: str = "pending"):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "fields": {
            "user_id": user_id,
            "username": username or "",
            "format": selections.get("format", ""),
            "level": selections.get("level", ""),
            "exclusivity": selections.get("exclusivity", ""),
            "personalization": selections.get("personalization", ""),
            "interactivity": selections.get("interactivity", ""),
            "caption": selections.get("caption", ""),
            "urgency": selections.get("urgency", ""),
            "note": note,
            "usd_price": base_usd,
            "urgency_usd": urgency_usd,
            "stars": stars,
            "status": status,
            "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(AIRTABLE_URL, json=payload, headers=headers) as resp:
            result = await resp.json()
            if resp.status == 200:
                return result.get("id")
            else:
                logger.error(f"airtable error: {result}")
                return None

async def update_airtable_status(record_id: str, status: str):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"fields": {"status": status}}
    async with aiohttp.ClientSession() as session:
        async with session.patch(f"{AIRTABLE_URL}/{record_id}", json=payload, headers=headers) as resp:
            if resp.status != 200:
                logger.error(f"airtable update error: {await resp.json()}")

# ── handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["selections"] = {}
    context.user_data["prefix"] = str(update.effective_user.id)
    context.user_data["step"] = "format"

    await update.message.reply_text(
        f"👋 welcome! let's build your custom order.\n\n{STEP_TITLES['format']}",
        reply_markup=build_keyboard("format", str(update.effective_user.id)),
        parse_mode="Markdown"
    )

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if len(data) != 3:
        return

    prefix, step, label = data
    selections = context.user_data.get("selections", {})
    selections[step] = label
    context.user_data["selections"] = selections

    current_index = STEPS.index(step)
    next_index = current_index + 1

    if next_index < len(STEPS):
        next_step = STEPS[next_index]
        context.user_data["step"] = next_step
        await query.edit_message_text(
            text=f"✅ *{label}* selected.\n\n{STEP_TITLES[next_step]}",
            reply_markup=build_keyboard(next_step, prefix),
            parse_mode="Markdown"
        )
    else:
        context.user_data["step"] = "note"
        await query.edit_message_text(
            text=(
                f"✅ *{label}* selected.\n\n"
                "📝 describe your request in detail.\n"
                "type your message below, or tap *skip* to continue."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("skip →", callback_data="skip_note")]
            ]),
            parse_mode="Markdown"
        )

async def handle_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "note":
        return
    note = update.message.text.strip()
    context.user_data["note"] = note
    await show_summary(update, context, note=note)

async def handle_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["note"] = ""
    await show_summary_from_query(query, context, note="")

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str = ""):
    selections = context.user_data.get("selections", {})
    base_usd, stars, urgency_usd = calculate_price(selections)
    summary = build_summary(selections, base_usd, stars, urgency_usd, note)

    record_id = await save_to_airtable(
        user_id=update.effective_user.id,
        username=update.effective_user.username or update.effective_user.first_name,
        selections=selections,
        base_usd=base_usd,
        stars=stars,
        urgency_usd=urgency_usd,
        note=note,
        status="pending"
    )
    context.user_data["airtable_record_id"] = record_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ pay {stars:,} stars", callback_data=f"pay|{stars}")],
        [InlineKeyboardButton("🔄 start over", callback_data="restart")],
    ])

    await update.message.reply_text(
        text=summary,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def show_summary_from_query(query, context: ContextTypes.DEFAULT_TYPE, note: str = ""):
    selections = context.user_data.get("selections", {})
    base_usd, stars, urgency_usd = calculate_price(selections)
    summary = build_summary(selections, base_usd, stars, urgency_usd, note)

    record_id = await save_to_airtable(
        user_id=query.from_user.id,
        username=query.from_user.username or query.from_user.first_name,
        selections=selections,
        base_usd=base_usd,
        stars=stars,
        urgency_usd=urgency_usd,
        note=note,
        status="pending"
    )
    context.user_data["airtable_record_id"] = record_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ pay {stars:,} stars", callback_data=f"pay|{stars}")],
        [InlineKeyboardButton("🔄 start over", callback_data="restart")],
    ])

    await query.edit_message_text(
        text=summary,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def handle_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "restart":
        context.user_data.clear()
        context.user_data["selections"] = {}
        context.user_data["step"] = "format"
        await query.edit_message_text(
            text=STEP_TITLES["format"],
            reply_markup=build_keyboard("format", str(query.from_user.id)),
        )
        return

    if query.data == "skip_note":
        await handle_skip_note(update, context)
        return

    if query.data.startswith("pay|"):
        stars = int(query.data.split("|")[1])
        selections = context.user_data.get("selections", {})
        urgency = selections.get("urgency", "no urgency")

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=f"custom order — {selections.get('format', 'content')}",
            description=(
                f"{selections.get('level', '')} · {selections.get('exclusivity', '')} · "
                f"{selections.get('personalization', '')} · {selections.get('interactivity', '')}\n\n"
                "all sales are final. no refunds. no returns."
            ),
            payload=f"order_{query.from_user.id}",
            currency="XTR",
            prices=[LabeledPrice(label="stars", amount=stars)],
        )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars = update.message.successful_payment.total_amount
    record_id = context.user_data.get("airtable_record_id")
    selections = context.user_data.get("selections", {})
    urgency = selections.get("urgency", "no urgency")
    urgency_usd = URGENCY.get(urgency, 0)

    # check if this is the urgency payment (2nd step)
    if context.user_data.get("urgency_payment"):
        await update.message.reply_text(
            "⚡ *urgency payment received.*\n\n"
            f"⭐ {stars:,} stars — your request has been prioritized.\n"
            "you will be contacted shortly via telegram.",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return

    # first payment done
    if record_id:
        await update_airtable_status(record_id, "paid")

    await update.message.reply_text(
        "✅ *payment received.*\n\n"
        f"⭐ {stars:,} stars — thank you.\n"
        "you will be contacted shortly via telegram.",
        parse_mode="Markdown"
    )

    # send urgency invoice as 2nd step if selected
    if urgency_usd > 0:
        urgency_stars = URGENCY_STARS.get(urgency, max(1, round(urgency_usd * USD_TO_STARS)))
        context.user_data["urgency_payment"] = True
        await update.message.reply_text(
            f"⚡ *urgency add-on selected:* {urgency}\n\n"
            f"please complete the urgency payment below.\n"
            f"⭐ {urgency_stars:,} stars (~${urgency_usd:,.2f} usd)\n\n"
            "tap the button to pay.",
            parse_mode="Markdown"
        )
        await context.bot.send_invoice(
            chat_id=update.message.chat_id,
            title=f"urgency add-on — {urgency}",
            description="priority processing for your order. all sales are final.",
            payload=f"urgency_{update.effective_user.id}",
            currency="XTR",
            prices=[LabeledPrice(label="urgency stars", amount=urgency_stars)],
        )
    else:
        context.user_data.clear()

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_pay, pattern="^pay\\|"))
    app.add_handler(CallbackQueryHandler(handle_pay, pattern="^restart$"))
    app.add_handler(CallbackQueryHandler(handle_skip_note, pattern="^skip_note$"))
    app.add_handler(CallbackQueryHandler(handle_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
