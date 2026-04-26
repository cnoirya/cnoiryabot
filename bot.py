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
logger = logging.getLogger(**name**)

BOT_TOKEN = os.environ.get(“BOT_TOKEN”)

AIRTABLE_API_KEY = “patEQZVaqPtlubFu0.084f1467591118d0e66f2fe6dabecf9cd72faaf531e0720aa1e8f7bc7bda6ff6”
AIRTABLE_BASE_ID = “appo4hTdhoi16wWFW”
AIRTABLE_TABLE_ID = “tblZAjJoedwqxzoNq”
AIRTABLE_URL = f”https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}”

USD_TO_STARS = 76.92
MAX_STARS = 35000

MINUTE_FORMATS = {“audio / min”, “video / min”, “audio-call / min”, “video-call / min”, “live-stream / min”}

FORMATS = {
“text”: 6.5, “message”: 6.5, “response”: 6.5, “auto-message”: 6.5,
“screen-capture”: 6.9, “audio / min”: 6.8, “live-stream / min”: 6.8,
“photo”: 7.0, “priority-list”: 7.0, “audio-call / min”: 7.2,
“video / min”: 7.3, “community”: 7.3, “video-call / min”: 25.9,
}
LEVELS = {“sfw”: 1.0, “nsfw”: 1.1}
EXCLUSIVITY = {“paid”: 1.0, “private”: 1.2, “custom”: 1.5}
PERSONALIZATION = {“generic”: 1.0, “semi-custom”: 1.3, “fully-custom”: 1.8}
INTERACTIVITY = {“one-way”: 1.0, “two-way”: 1.3}
CAPTION = {“no caption”: 1.0, “with caption”: 1.05}
URGENCY = {“no urgency”: 0, “urgent (sfw)”: 9615, “urgent (nsfw)”: 35000}

STEPS = [“format”, “level”, “exclusivity”, “personalization”, “interactivity”, “caption”, “urgency”]
STEP_DATA = {
“format”: FORMATS, “level”: LEVELS, “exclusivity”: EXCLUSIVITY,
“personalization”: PERSONALIZATION, “interactivity”: INTERACTIVITY,
“caption”: CAPTION, “urgency”: URGENCY,
}

# ── translations ──────────────────────────────────────────────────────────────

TEXTS = {
“en”: {
“welcome”: “👋 *welcome!*\n\nlet’s build your custom order step by step.”,
“select_lang”: “🌐 please select your language:”,
“step_titles”: {
“format”: “🎭 *what type of content do you want?*”,
“level”: “🎚️ *what content level?*”,
“exclusivity”: “🔐 *how exclusive should it be?*”,
“personalization”: “🎨 *how personalized?*”,
“interactivity”: “💬 *one-way or interactive?*”,
“caption”: “✍️ *do you want a caption?*”,
“urgency”: “⚡ *need it urgently?*\n_urgency is billed separately after your main payment.*”,
“minutes”: “⏱️ *how many minutes?*\n_select duration for your session.*”,
},
“note_prompt”: “📝 *describe your request.*\nthe more detail, the better. type below or tap skip.”,
“skip”: “skip →”,
“start_over”: “🔄 start over”,
“selected”: “✅ *{}* selected.”,
“order_summary”: “📋 *order summary*”,
“duration”: “duration”,
“note”: “note”,
“total”: “⭐ *total:* {:,} stars”,
“split_note”: “*split into {} payments of max {:,} stars each*”,
“urgency_note”: “⚡ *urgency:* {:,} stars *(2nd step after main payment)*”,
“disclaimer”: “\n\n⚠️ *all sales are final.*\nno refunds. no returns.\nrequester will be contacted shortly via telegram.”,
“pay_btn”: “⭐ pay {:,} stars”,
“pay_btn_split”: “⭐ pay {:,} stars ({}/{})”,
“payment_received”: “✅ *payment complete.*\n⭐ {:,} stars — thank you.\nyou will be contacted shortly via telegram.”,
“payment_chunk”: “✅ *payment {}/{} received.* ⭐ {:,} stars\nnext payment coming up…”,
“urgency_prompt”: “⚡ *urgency add-on:* {}\n⭐ {:,} stars — tap below to complete.”,
“urgency_paid”: “⚡ *urgency payment received.*\n⭐ {:,} stars — your request has been prioritized.\nyou will be contacted shortly via telegram.”,
“format_desc”: {
“text”: “plain written content, no media”,
“message”: “a single direct message”,
“response”: “a reply to your specific question or prompt”,
“auto-message”: “a scheduled or automated message”,
“screen-capture”: “a screenshot or screen recording”,
“audio / min”: “voice recording, priced per minute”,
“live-stream / min”: “live broadcast session, priced per minute”,
“photo”: “a single photo”,
“priority-list”: “a curated list with priority access”,
“audio-call / min”: “private audio call, priced per minute”,
“video / min”: “video content, priced per minute”,
“community”: “access to a private community or group”,
“video-call / min”: “private video call, priced per minute”,
},
“level_desc”: {
“sfw”: “general audience — no explicit content”,
“nsfw”: “adult content — explicit material”,
},
“exclusivity_desc”: {
“paid”: “standard access — shared content”,
“private”: “exclusive to you — not shared with others”,
“custom”: “fully tailored to your exact request”,
},
“personalization_desc”: {
“generic”: “ready-made, no customization”,
“semi-custom”: “based on your preferences with adjustments”,
“fully-custom”: “created from scratch for you”,
},
“interactivity_desc”: {
“one-way”: “content delivered to you, no back-and-forth”,
“two-way”: “interactive — includes responses and engagement”,
},
“caption_desc”: {
“no caption”: “no written text accompanies the content”,
“with caption”: “includes a written caption or description”,
},
“urgency_desc”: {
“no urgency”: “standard delivery timeline”,
“urgent (sfw)”: “priority processing for general content — billed as 2nd step”,
“urgent (nsfw)”: “priority processing for adult content — billed as 2nd step”,
},
},
“tr”: {
“welcome”: “👋 *hoş geldin!*\n\nhaydi adım adım özel siparişini oluşturalım.”,
“select_lang”: “🌐 lütfen dilini seç:”,
“step_titles”: {
“format”: “🎭 *ne tür bir içerik istiyorsun?*”,
“level”: “🎚️ *içerik türü nedir?*”,
“exclusivity”: “🔐 *ne kadar özel olsun?*”,
“personalization”: “🎨 *ne kadar kişiselleştirilmiş olsun?*”,
“interactivity”: “💬 *tek yönlü mü, etkileşimli mi?*”,
“caption”: “✍️ *açıklama yazısı ister misin?*”,
“urgency”: “⚡ *acil mi?*\n_aciliyet ücreti ana ödemeden sonra ayrıca tahsil edilir.*”,
“minutes”: “⏱️ *kaç dakika?*\n_oturum süresini seç.*”,
},
“note_prompt”: “📝 *isteğini açıkla.*\nne kadar detaylı olursa o kadar iyi. aşağıya yaz ya da geç’e bas.”,
“skip”: “geç →”,
“start_over”: “🔄 baştan başla”,
“selected”: “✅ *{}* seçildi.”,
“order_summary”: “📋 *sipariş özeti*”,
“duration”: “süre”,
“note”: “not”,
“total”: “⭐ *toplam:* {:,} yıldız”,
“split_note”: “*en fazla {:,} yıldızlık {} ödemeye bölündü*”,
“urgency_note”: “⚡ *aciliyet:* {:,} yıldız *(ana ödemeden sonra 2. adım)*”,
“disclaimer”: “\n\n⚠️ *tüm satışlar kesindir.*\niade ve geri ödeme yapılmaz.\ntalep sahibiyle kısa süre içinde telegram üzerinden iletişime geçilecektir.”,
“pay_btn”: “⭐ {:,} yıldız öde”,
“pay_btn_split”: “⭐ {:,} yıldız öde ({}/{})”,
“payment_received”: “✅ *ödeme tamamlandı.*\n⭐ {:,} yıldız — teşekkürler.\nkısa süre içinde telegram üzerinden seninle iletişime geçilecek.”,
“payment_chunk”: “✅ *{}/{}. ödeme alındı.* ⭐ {:,} yıldız\nsıradaki ödeme geliyor…”,
“urgency_prompt”: “⚡ *aciliyet eklentisi:* {}\n⭐ {:,} yıldız — tamamlamak için aşağıya bas.”,
“urgency_paid”: “⚡ *aciliyet ödemesi alındı.*\n⭐ {:,} yıldız — isteğin önceliklendirildi.\nkısa süre içinde telegram üzerinden seninle iletişime geçilecek.”,
“format_desc”: {
“text”: “düz yazı içeriği, medya yok”,
“message”: “tek bir doğrudan mesaj”,
“response”: “sorunuza veya isteğinize özel yanıt”,
“auto-message”: “zamanlanmış veya otomatik mesaj”,
“screen-capture”: “ekran görüntüsü veya ekran kaydı”,
“audio / min”: “sesli kayıt, dakika başı fiyatlandırma”,
“live-stream / min”: “canlı yayın oturumu, dakika başı fiyatlandırma”,
“photo”: “tek bir fotoğraf”,
“priority-list”: “öncelikli erişimli özenle hazırlanmış liste”,
“audio-call / min”: “özel sesli görüşme, dakika başı fiyatlandırma”,
“video / min”: “video içeriği, dakika başı fiyatlandırma”,
“community”: “özel bir topluluğa veya gruba erişim”,
“video-call / min”: “özel görüntülü görüşme, dakika başı fiyatlandırma”,
},
“level_desc”: {
“sfw”: “genel kitle — açık içerik yok”,
“nsfw”: “yetişkin içeriği — açık materyal”,
},
“exclusivity_desc”: {
“paid”: “standart erişim — paylaşılan içerik”,
“private”: “yalnızca sana özel — başkasıyla paylaşılmaz”,
“custom”: “isteğine göre tamamen özelleştirilmiş”,
},
“personalization_desc”: {
“generic”: “hazır içerik, kişiselleştirme yok”,
“semi-custom”: “tercihlerine göre düzenlenmiş”,
“fully-custom”: “sıfırdan senin için üretilmiş”,
},
“interactivity_desc”: {
“one-way”: “içerik sana iletilir, geri bildirim yok”,
“two-way”: “etkileşimli — yanıt ve katılım içerir”,
},
“caption_desc”: {
“no caption”: “içeriğe eşlik eden yazı yok”,
“with caption”: “açıklama veya altyazı içerir”,
},
“urgency_desc”: {
“no urgency”: “standart teslimat süresi”,
“urgent (sfw)”: “genel içerik için öncelikli işlem — 2. adım olarak ayrıca tahsil edilir”,
“urgent (nsfw)”: “yetişkin içeriği için öncelikli işlem — 2. adım olarak ayrıca tahsil edilir”,
},
“labels”: {
“text”: “yazı”, “message”: “mesaj”, “response”: “yanıt”,
“auto-message”: “otomatik mesaj”, “screen-capture”: “ekran kaydı”,
“audio / min”: “ses kaydı / dakika”, “live-stream / min”: “canlı yayın / dakika”,
“photo”: “fotoğraf”, “priority-list”: “öncelik listesi”,
“audio-call / min”: “sesli görüşme / dakika”, “video / min”: “video / dakika”,
“community”: “topluluk erişimi”, “video-call / min”: “görüntülü görüşme / dakika”,
“sfw”: “genel kitle”, “nsfw”: “yetişkin”,
“paid”: “standart”, “private”: “özel”, “custom”: “tamamen özel”,
“generic”: “hazır içerik”, “semi-custom”: “yarı kişisel”, “fully-custom”: “sıfırdan kişisel”,
“one-way”: “tek taraflı”, “two-way”: “karşılıklı”,
“no caption”: “açıklamasız”, “with caption”: “açıklamalı”,
“no urgency”: “acil değil”, “urgent (sfw)”: “acil — genel”, “urgent (nsfw)”: “acil — yetişkin”,
},
}
}

def t(lang, key, *args):
val = TEXTS[lang][key]
if args:
return val.format(*args)
return val

def desc(lang, step, label):
key = f”{step}_desc”
return TEXTS[lang].get(key, {}).get(label, “”)

# ── helpers ───────────────────────────────────────────────────────────────────

def calculate_stars(selections, minutes=1):
base = FORMATS[selections[“format”]]
multiplier = (
LEVELS[selections[“level”]]
* EXCLUSIVITY[selections[“exclusivity”]]
* PERSONALIZATION[selections[“personalization”]]
* INTERACTIVITY[selections[“interactivity”]]
* CAPTION[selections[“caption”]]
)
return max(1, round(base * multiplier * minutes * USD_TO_STARS))

def split_invoices(total_stars):
chunks, remaining = [], total_stars
while remaining > 0:
chunks.append(min(remaining, MAX_STARS))
remaining -= MAX_STARS
return chunks

def build_keyboard(step, prefix, lang):
buttons = []
for label in STEP_DATA[step]:
d = desc(lang, step, label)
btn_text = f”{label}  —  {d}” if d else label
buttons.append([InlineKeyboardButton(btn_text, callback_data=f”{prefix}|{step}|{label}”)])
return InlineKeyboardMarkup(buttons)

def build_minutes_keyboard(prefix):
return InlineKeyboardMarkup([
[InlineKeyboardButton(f”{i} min”, callback_data=f”{prefix}|minutes|{i}”)]
for i in range(1, 6)
])

def translate_label(lang, label):
if lang == “tr”:
return TEXTS[“tr”].get(“labels”, {}).get(label, label)
return label

def build_summary(lang, selections, total_stars, minutes, chunks):
sep = “━━━━━━━━━━━━━━━━━━━━”
lines = [sep, t(lang, “order_summary”), sep]
for step in STEPS:
lines.append(f”• *{step}:* {translate_label(lang, selections[step])}”)
if selections[“format”] in MINUTE_FORMATS:
lines.append(f”• *{t(lang, ‘duration’)}:* {minutes} min”)
note = selections.get(“note”, “”)
if note:
lines.append(f”• *{t(lang, ‘note’)}:* {note}”)
lines.append(sep)
lines.append(t(lang, “total”, total_stars))
if len(chunks) > 1:
lines.append(t(lang, “split_note”, len(chunks), MAX_STARS))
urgency_stars = URGENCY.get(selections.get(“urgency”, “no urgency”), 0)
if urgency_stars > 0:
lines.append(t(lang, “urgency_note”, urgency_stars))
lines.append(sep)
lines.append(t(lang, “disclaimer”))
return “\n”.join(lines)

# ── airtable ──────────────────────────────────────────────────────────────────

async def save_to_airtable(user_id, username, selections, total_stars, minutes, status=“pending”):
headers = {“Authorization”: f”Bearer {AIRTABLE_API_KEY}”, “Content-Type”: “application/json”}
payload = {“fields”: {
“user_id”: user_id, “username”: username or “”,
“format”: selections.get(“format”, “”), “level”: selections.get(“level”, “”),
“exclusivity”: selections.get(“exclusivity”, “”), “personalization”: selections.get(“personalization”, “”),
“interactivity”: selections.get(“interactivity”, “”), “caption”: selections.get(“caption”, “”),
“urgency”: selections.get(“urgency”, “”), “note”: selections.get(“note”, “”),
“minutes”: minutes, “stars”: total_stars, “status”: status,
“created_at”: datetime.utcnow().strftime(”%Y-%m-%d”),
}}
async with aiohttp.ClientSession() as session:
async with session.post(AIRTABLE_URL, json=payload, headers=headers) as resp:
result = await resp.json()
if resp.status == 200:
return result.get(“id”)
logger.error(f”airtable error: {result}”)
return None

async def update_airtable_status(record_id, status):
headers = {“Authorization”: f”Bearer {AIRTABLE_API_KEY}”, “Content-Type”: “application/json”}
async with aiohttp.ClientSession() as session:
async with session.patch(f”{AIRTABLE_URL}/{record_id}”, json={“fields”: {“status”: status}}, headers=headers) as resp:
if resp.status != 200:
logger.error(f”airtable update error: {await resp.json()}”)

async def send_next_invoice(chat_id, context, user_id, selections, lang, is_urgency=False):
if is_urgency:
urgency = selections.get(“urgency”, “no urgency”)
urgency_stars = URGENCY.get(urgency, 0)
if urgency_stars > 0:
await context.bot.send_invoice(
chat_id=chat_id,
title=f”urgency add-on — {urgency}”,
description=“priority processing. all sales are final.”,
payload=f”urgency_{user_id}”,
provider_token=””,
currency=“XTR”,
prices=[LabeledPrice(label=“urgency”, amount=urgency_stars)],
)
return

```
chunks = context.user_data.get("invoice_chunks", [])
chunk_index = context.user_data.get("chunk_index", 0)
if chunk_index < len(chunks):
    stars = chunks[chunk_index]
    total_chunks = len(chunks)
    title = f"custom order — {selections.get('format', 'content')}"
    if total_chunks > 1:
        title += f" ({chunk_index + 1}/{total_chunks})"
    await context.bot.send_invoice(
        chat_id=chat_id, title=title,
        description=(
            f"{selections.get('level', '')} · {selections.get('exclusivity', '')} · "
            f"{selections.get('personalization', '')} · {selections.get('interactivity', '')}\n"
            "all sales are final. no refunds. no returns."
        ),
        payload=f"order_{user_id}_{chunk_index}",
        provider_token="", currency="XTR",
        prices=[LabeledPrice(label="stars", amount=stars)],
    )
    context.user_data["chunk_index"] = chunk_index + 1
```

# ── handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
context.user_data.clear()
keyboard = InlineKeyboardMarkup([
[InlineKeyboardButton(“🇬🇧 english”, callback_data=“lang|en”)],
[InlineKeyboardButton(“🇹🇷 türkçe”, callback_data=“lang|tr”)],
])
await update.message.reply_text(“🌐 please select your language / lütfen dilini seç:”, reply_markup=keyboard)

async def handle_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
lang = query.data.split(”|”)[1]
context.user_data[“lang”] = lang
context.user_data[“selections”] = {}
context.user_data[“prefix”] = str(query.from_user.id)
context.user_data[“step”] = “format”
await query.edit_message_text(
text=t(lang, “welcome”) + “\n\n” + t(lang, “step_titles”)[“format”],
reply_markup=build_keyboard(“format”, str(query.from_user.id), lang),
parse_mode=“Markdown”
)

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
parts = query.data.split(”|”)
if len(parts) != 3:
return
prefix, step, label = parts
lang = context.user_data.get(“lang”, “en”)
selections = context.user_data.get(“selections”, {})

```
if step == "minutes":
    context.user_data["minutes"] = int(label)
    context.user_data["step"] = "note"
    await query.edit_message_text(
        text=t(lang, "selected", f"{label} min") + "\n\n" + t(lang, "note_prompt"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "skip"), callback_data="skip_note")]]),
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
        text=t(lang, "selected", label) + "\n\n" + t(lang, "step_titles")[next_step],
        reply_markup=build_keyboard(next_step, prefix, lang),
        parse_mode="Markdown"
    )
else:
    if selections.get("format") in MINUTE_FORMATS:
        context.user_data["step"] = "minutes"
        await query.edit_message_text(
            text=t(lang, "selected", label) + "\n\n" + t(lang, "step_titles")["minutes"],
            reply_markup=build_minutes_keyboard(prefix),
            parse_mode="Markdown"
        )
    else:
        context.user_data["step"] = "note"
        await query.edit_message_text(
            text=t(lang, "selected", label) + "\n\n" + t(lang, "note_prompt"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "skip"), callback_data="skip_note")]]),
            parse_mode="Markdown"
        )
```

async def handle_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
if context.user_data.get(“step”) != “note”:
return
context.user_data[“selections”][“note”] = update.message.text.strip()
await show_summary(update, context)

async def handle_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
context.user_data[“selections”][“note”] = “”
await show_summary_from_query(query, context)

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
lang = context.user_data.get(“lang”, “en”)
selections = context.user_data.get(“selections”, {})
minutes = context.user_data.get(“minutes”, 1)
total_stars = calculate_stars(selections, minutes)
chunks = split_invoices(total_stars)
context.user_data[“invoice_chunks”] = chunks
context.user_data[“chunk_index”] = 0
record_id = await save_to_airtable(
user_id=update.effective_user.id,
username=update.effective_user.username or update.effective_user.first_name,
selections=selections, total_stars=total_stars, minutes=minutes,
)
context.user_data[“airtable_record_id”] = record_id
pay_label = t(lang, “pay_btn”, chunks[0]) if len(chunks) == 1 else t(lang, “pay_btn_split”, chunks[0], 1, len(chunks))
await update.message.reply_text(
text=build_summary(lang, selections, total_stars, minutes, chunks),
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(pay_label, callback_data=“pay|0”)],
[InlineKeyboardButton(t(lang, “start_over”), callback_data=“restart”)],
]),
parse_mode=“Markdown”
)

async def show_summary_from_query(query, context: ContextTypes.DEFAULT_TYPE):
lang = context.user_data.get(“lang”, “en”)
selections = context.user_data.get(“selections”, {})
minutes = context.user_data.get(“minutes”, 1)
total_stars = calculate_stars(selections, minutes)
chunks = split_invoices(total_stars)
context.user_data[“invoice_chunks”] = chunks
context.user_data[“chunk_index”] = 0
record_id = await save_to_airtable(
user_id=query.from_user.id,
username=query.from_user.username or query.from_user.first_name,
selections=selections, total_stars=total_stars, minutes=minutes,
)
context.user_data[“airtable_record_id”] = record_id
pay_label = t(lang, “pay_btn”, chunks[0]) if len(chunks) == 1 else t(lang, “pay_btn_split”, chunks[0], 1, len(chunks))
await query.edit_message_text(
text=build_summary(lang, selections, total_stars, minutes, chunks),
reply_markup=InlineKeyboardMarkup([
[InlineKeyboardButton(pay_label, callback_data=“pay|0”)],
[InlineKeyboardButton(t(lang, “start_over”), callback_data=“restart”)],
]),
parse_mode=“Markdown”
)

async def handle_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
lang = context.user_data.get(“lang”, “en”)

```
if query.data == "restart":
    context.user_data.clear()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 english", callback_data="lang|en")],
        [InlineKeyboardButton("🇹🇷 türkçe", callback_data="lang|tr")],
    ])
    await query.edit_message_text("🌐 please select your language / lütfen dilini seç:", reply_markup=keyboard)
    return

if query.data == "skip_note":
    await handle_skip_note(update, context)
    return

if query.data.startswith("pay|"):
    selections = context.user_data.get("selections", {})
    await send_next_invoice(query.message.chat_id, context, query.from_user.id, selections, lang)
```

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
stars = update.message.successful_payment.total_amount
payload = update.message.successful_payment.invoice_payload
lang = context.user_data.get(“lang”, “en”)
selections = context.user_data.get(“selections”, {})
chunks = context.user_data.get(“invoice_chunks”, [])
chunk_index = context.user_data.get(“chunk_index”, 0)
record_id = context.user_data.get(“airtable_record_id”)

```
if payload.startswith("urgency_"):
    await update.message.reply_text(t(lang, "urgency_paid", stars), parse_mode="Markdown")
    context.user_data.clear()
    return

if chunk_index < len(chunks):
    await update.message.reply_text(
        t(lang, "payment_chunk", chunk_index, len(chunks), stars), parse_mode="Markdown"
    )
    await send_next_invoice(update.message.chat_id, context, update.effective_user.id, selections, lang)
    return

if record_id:
    await update_airtable_status(record_id, "paid")

await update.message.reply_text(t(lang, "payment_received", stars), parse_mode="Markdown")

urgency = selections.get("urgency", "no urgency")
urgency_stars = URGENCY.get(urgency, 0)
if urgency_stars > 0:
    await update.message.reply_text(t(lang, "urgency_prompt", urgency, urgency_stars), parse_mode="Markdown")
    await send_next_invoice(update.message.chat_id, context, update.effective_user.id, selections, lang, is_urgency=True)
else:
    context.user_data.clear()
```

def main():
app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler(“start”, start))
app.add_handler(CallbackQueryHandler(handle_lang, pattern=”^lang\|”))
app.add_handler(CallbackQueryHandler(handle_pay, pattern=”^pay\|”))
app.add_handler(CallbackQueryHandler(handle_pay, pattern=”^restart$”))
app.add_handler(CallbackQueryHandler(handle_skip_note, pattern=”^skip_note$”))
app.add_handler(CallbackQueryHandler(handle_selection))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note))
app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
logger.info(“bot is running…”)
app.run_polling()

if **name** == “**main**”:
main()
