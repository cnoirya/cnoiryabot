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

USD_TO_STARS = 76.92
MAX_STARS = 35000

# ── pricing ───────────────────────────────────────────────────────────────────
MINUTE_FORMATS = {"audio / min", "video / min", "audio-call / min", "video-call / min", "live-stream / min"}

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

LEVELS = {"sfw": 1.0, "nsfw": 1.1}
EXCLUSIVITY = {"paid": 1.0, "private": 1.2, "custom": 1.5}
PERSONALIZATION = {"generic": 1.0, "semi-custom": 1.3, "fully-custom": 1.8}
INTERACTIVITY = {"one-way": 1.0, "two-way": 1.3}
CAPTION = {"no caption": 1.0, "with caption": 1.05}

URGENCY = {"no urgency": 0, "urgent (sfw)": 19230, "urgent (nsfw)": 35000}

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
    "urgency": "add urgency? (billed separately as 2nd step)",
    "minutes": "select duration (minutes)",
}

DISCLAIMER = (
    "\n\n⚠️ *all sales are final.*\n"
    "no refunds. no returns.\n"
    "requester will be contacted shortly via telegram."
)

def calculate_stars(selections: dict, minutes: int = 1) -> int:
    base = FORMATS[selections["format"]]
    multiplier = (
        LEVELS[selections["level"]]
        * EXCLUSIVITY[selections["exclusivity"]]
        * PERSONALIZATION[selections["personalization"]]
        * INTERACTIVITY[selections["interactivity"]]
        * CAPTION[selections["caption"]]
    )
    usd = round(base * multiplier * minutes, 2)
    return max(1, round(usd * USD_TO_STARS))

def split_invoices(total_stars: int) -> list[int]:
    """split total stars into chunks of max 35,000"""
    chunks = []
    remaining = total_stars
    while remaining > 0:
        chunk = min(remaining, MAX_STARS)
        chunks.append(chunk)
        remaining -= chunk
    return chunks

def build_keyboard(step: str, prefix: str) -> InlineKeyboardMarkup:
    data = STEP_DATA[step]
    buttons = [[InlineKeyboardButton(label, callback_data=f"{prefix}|{step}|{label}")] for label in data]
    return InlineKeyboardMarkup(buttons)

def build_minutes_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(f"{i} min", callback_data=f"{prefix}|minutes|{i}")] for i in range(1, 6)]
    return InlineKeyboardMarkup(buttons)

def build_summary(selections: dict, total_stars: int, minutes: int, chunks: list[int]) -> str:
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "📋 *order summary*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for step in STEPS:
        lines.append(f"• *{step}:* {selections[step]}")
    if selections["format"] in MINUTE_FORMATS:
        lines.append(f"• *duration:* {minutes} min")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⭐ *total:* {total_stars:,} stars")
    if len(chunks) > 1:
        lines.append(f"_(split into {len(chunks)} invoices of max {MAX_STARS:,} stars each)_")
    urgency_stars = URGENCY.get(selections.get("urgency", "no urgency"), 0)
    if urgency_stars > 0:
        lines.append(f"⚡ *urgency add-on:* {urgency_stars:,} stars _(2nd step)_")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(DISCLAIMER)
    return "\n".join(lines)

# ── airtable ──────────────────────────────────────────────────────────────────
async def save_to_airtable(user_id, username, selections, total_stars, minutes, status="pending"):
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
            "note": selections.get("note", ""),
            "minutes": minutes,
            "stars": total_stars,
            "status": status,
            "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(AIRTABLE_URL, json=payload, headers=headers) as resp:
            result = await resp.json()
            if resp.status == 200:
                return result.get("id")
            logger.error(f"airtable error: {result}")
            return None

async def update_airtable_status(record_id, status):
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(
            f"{AIRTABLE_URL}/{record_id}",
            json={"fields": {"status": status}},
            headers=headers
        ) as resp:
            if resp.status != 200:
                logger.error(f"airtable update error: {await resp.json()}")

# ── invoice sender ────────────────────────────────────────────────────────────
async def send_next_invoice(chat_id, context, user_id, selections, is_urgency=False):
    if is_urgency:
        urgency = selections.get("urgency", "no urgency")
        urgency_stars = URGENCY.get(urgency, 0)
        if urgency_stars > 0:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=f"urgency add-on — {urgency}",
                description="priority processing. all sales are final.",
                payload=f"urgency_{user_id}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label="urgency", amount=urgency_stars)],
            )
        return

    chunks = context.user_data.get("invoice_chunks", [])
    chunk_index = context.user_data.get("chunk_index", 0)

    if chunk_index < len(chunks):
        stars = chunks[chunk_index]
        total_chunks = len(chunks)
        title = f"custom order — {selections.get('format', 'content')}"
        if total_chunks > 1:
            title += f" ({chunk_index + 1}/{total_chunks})"
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=title,
            description=(
                f"{selections.get('level', '')} · {selections.get('exclusivity', '')} · "
                f"{selections.get('personalization', '')} · {selections.get('interactivity', '')}\n"
                "all sales are final. no refunds. no returns."
            ),
            payload=f"order_{user_id}_{chunk_index}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="stars", amount=stars)],
        )
        context.user_data["chunk_index"] = chunk_index + 1

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

    parts = query.data.split("|")
    if len(parts) != 3:
        return

    prefix, step, label = parts
    selections = context.user_data.get("selections", {})

    if step == "minutes":
        minutes = int(label)
        context.user_data["minutes"] = minutes
        context.user_data["step"] = "note"
        await query.edit_message_text(
            text=f"✅ *{label} min* selected.\n\n📝 describe your request in detail.\ntype below or tap *skip*.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("skip →", callback_data="skip_note")]]),
            parse_mode="Markdown"
        )
        return

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
        # check if minute-based format
        if selections.get("format") in MINUTE_FORMATS:
            context.user_data["step"] = "minutes"
            await query.edit_message_text(
                text=f"✅ *{label}* selected.\n\n{STEP_TITLES['minutes']}",
                reply_markup=build_minutes_keyboard(prefix),
                parse_mode="Markdown"
            )
        else:
            context.user_data["step"] = "note"
            await query.edit_message_text(
                text=f"✅ *{label}* selected.\n\n📝 describe your request in detail.\ntype below or tap *skip*.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("skip →", callback_data="skip_note")]]),
                parse_mode="Markdown"
            )

async def handle_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "note":
        return
    note = update.message.text.strip()
    context.user_data["selections"]["note"] = note
    await show_summary(update, context)

async def handle_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["selections"]["note"] = ""
    await show_summary_from_query(query, context)

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selections = context.user_data.get("selections", {})
    minutes = context.user_data.get("minutes", 1)
    total_stars = calculate_stars(selections, minutes)
    chunks = split_invoices(total_stars)
    context.user_data["invoice_chunks"] = chunks
    context.user_data["chunk_index"] = 0

    summary = build_summary(selections, total_stars, minutes, chunks)

    record_id = await save_to_airtable(
        user_id=update.effective_user.id,
        username=update.effective_user.username or update.effective_user.first_name,
        selections=selections,
        total_stars=total_stars,
        minutes=minutes,
    )
    context.user_data["airtable_record_id"] = record_id

    pay_label = f"⭐ pay {chunks[0]:,} stars"
    if len(chunks) > 1:
        pay_label += f" (1/{len(chunks)})"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(pay_label, callback_data=f"pay|0")],
        [InlineKeyboardButton("🔄 start over", callback_data="restart")],
    ])

    await update.message.reply_text(text=summary, reply_markup=keyboard, parse_mode="Markdown")

async def show_summary_from_query(query, context: ContextTypes.DEFAULT_TYPE):
    selections = context.user_data.get("selections", {})
    minutes = context.user_data.get("minutes", 1)
    total_stars = calculate_stars(selections, minutes)
    chunks = split_invoices(total_stars)
    context.user_data["invoice_chunks"] = chunks
    context.user_data["chunk_index"] = 0

    summary = build_summary(selections, total_stars, minutes, chunks)

    record_id = await save_to_airtable(
        user_id=query.from_user.id,
        username=query.from_user.username or query.from_user.first_name,
        selections=selections,
        total_stars=total_stars,
        minutes=minutes,
    )
    context.user_data["airtable_record_id"] = record_id

    pay_label = f"⭐ pay {chunks[0]:,} stars"
    if len(chunks) > 1:
        pay_label += f" (1/{len(chunks)})"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(pay_label, callback_data=f"pay|0")],
        [InlineKeyboardButton("🔄 start over", callback_data="restart")],
    ])

    await query.edit_message_text(text=summary, reply_markup=keyboard, parse_mode="Markdown")

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
        selections = context.user_data.get("selections", {})
        await send_next_invoice(query.message.chat_id, context, query.from_user.id, selections)

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars = update.message.successful_payment.total_amount
    payload = update.message.successful_payment.invoice_payload
    selections = context.user_data.get("selections", {})
    chunks = context.user_data.get("invoice_chunks", [])
    chunk_index = context.user_data.get("chunk_index", 0)
    record_id = context.user_data.get("airtable_record_id")

    # urgency payment
    if payload.startswith("urgency_"):
        await update.message.reply_text(
            f"⚡ *urgency payment received.*\n⭐ {stars:,} stars — your request has been prioritized.\n"
            "you will be contacted shortly via telegram.",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return

    # base order — more chunks?
    if chunk_index < len(chunks):
        await update.message.reply_text(
            f"✅ *payment {chunk_index}/{len(chunks)} received.* ⭐ {stars:,} stars\n\nnext payment coming up...",
            parse_mode="Markdown"
        )
        await send_next_invoice(update.message.chat_id, context, update.effective_user.id, selections)
        return

    # all chunks done
    if record_id:
        await update_airtable_status(record_id, "paid")

    await update.message.reply_text(
        f"✅ *payment complete.*\n⭐ {stars:,} stars — thank you.\n"
        "you will be contacted shortly via telegram.",
        parse_mode="Markdown"
    )

    # send urgency invoice if selected
    urgency = selections.get("urgency", "no urgency")
    urgency_stars = URGENCY.get(urgency, 0)
    if urgency_stars > 0:
        context.user_data["urgency_payment"] = True
        await update.message.reply_text(
            f"⚡ *urgency add-on:* {urgency}\n⭐ {urgency_stars:,} stars — tap below to complete.",
            parse_mode="Markdown"
        )
        await send_next_invoice(update.message.chat_id, context, update.effective_user.id, selections, is_urgency=True)
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
