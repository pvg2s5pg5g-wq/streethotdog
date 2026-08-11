"""
STREET HOT DOG — Telegram bot
==============================

Komandalar / tugmalar:
  🌭 Menyu          — mahsulotlar va narxlar
  🛒 Buyurtma       — buyurtma berish (tugmalar orqali, admin'ga keladi)
  📞 Aloqa          — telefon, Telegram
  🚚 Yetkazib berish — yetkazish shartlari

Buyurtma admin'ga (ADMIN_ID) yuboriladi.

Ishga tushirish:
    pip install aiogram
    BOT_TOKEN va ADMIN_ID (Variables) to'ldiring
    python hotdog_bot.py
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

# ── SOZLAMALAR ────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))       # Buyurtma shu yerga keladi
PHONE = "+998 90 096 87 70"
TG_CONTACT = "@sh0khrukh1"
SITE = "https://street-hotdog-uz.netlify.app"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)
router = Router()

# ── menyu ma'lumotlari (saytdan) ──────────────────────
MENU = """🌭 <b>STREET HOT DOG — MENYU</b>

⭐️ <b>Qazili Hot-Dog</b> (bestseller)
Mo'l-ko'l qazi, tuxum va maxsus sous bilan.
• 2x-Katta — 30 000 so'm
• Katta — 25 000 so'm
• O'rtacha — 20 000 so'm
• Kichkina — 15 000 so'm

🆕 <b>Salatli Hot-Dog</b>
Yangi sabzavotlar, pomidor sousi va krem bilan.
• 2x-Katta — 37 000 so'm
• Katta — 25 000 so'm
• O'rtacha — 17 000 so'm
• Kichkina — 14 000 so'm

🔝 <b>Hot-Let</b>
Go'sht taxtacha, pishloq va salat bargi bilan.
• Katta — 30 000 so'm
• Kichkina — 22 000 so'm

🍔 <b>Gamburger</b>
Sertane, mol go'shti va eritilgan pishloq bilan.
• Gamburger — 22 000 so'm
• Chizburger — 25 000 so'm
• Dabl burger — 32 000 so'm

☕️ <b>Coffee</b>
Issiq va tetiklantiruvchi.
• Katta — 8 000 so'm
• Kichkina — 5 000 so'm

🥤 <b>Salqin Ichimliklar</b>
Coca-Cola, Fanta yoki Sprite.
• 1.5 L — 17 000 so'm
• 1 L — 12 000 so'm
• 0.5 L — 8 000 so'm

<i>Buyurtma berish uchun «🛒 Buyurtma» tugmasini bosing.</i>"""

CONTACT = f"""📞 <b>Bog'lanish</b>

Telefon: <a href="tel:+998900968770">{PHONE}</a>
Telegram: {TG_CONTACT}
Sayt: {SITE}

🕙 Ish vaqti: har kuni 10:00 – 23:00"""

DELIVERY = """🚚 <b>Yetkazib berish</b>

• Toshkent bo'ylab yetkazib beramiz
• Buyurtma qabul qilingach darhol tayyorlanadi
• 🔥 30 daqiqada yetkaziladi
• Maxsus issiq quticha bilan — issiqligicha keladi
• Manzil va yetkazish narxi qo'ng'iroq paytida aniqlashtiriladi

🕙 Har kuni 10:00 – 23:00"""

# ── buyurtma uchun mahsulotlar (tugmalar orqali tanlash) ─
CATEGORIES = {
    "qazili": "⭐️ Qazili Hot-Dog",
    "salatli": "🆕 Salatli Hot-Dog",
    "hotlet": "🔝 Hot-Let",
    "burger": "🍔 Gamburger",
    "coffee": "☕️ Coffee",
    "drinks": "🥤 Salqin Ichimliklar",
}

ITEMS = {
    "qazili": [
        ("qazili_2x", "2x-Katta", 30000),
        ("qazili_katta", "Katta", 25000),
        ("qazili_orta", "O'rtacha", 20000),
        ("qazili_kichkina", "Kichkina", 15000),
    ],
    "salatli": [
        ("salatli_2x", "2x-Katta", 37000),
        ("salatli_katta", "Katta", 25000),
        ("salatli_orta", "O'rtacha", 17000),
        ("salatli_kichkina", "Kichkina", 14000),
    ],
    "hotlet": [
        ("hotlet_katta", "Katta", 30000),
        ("hotlet_kichkina", "Kichkina", 22000),
    ],
    "burger": [
        ("gamburger", "Gamburger", 22000),
        ("chizburger", "Chizburger", 25000),
        ("dabl_burger", "Dabl burger", 32000),
    ],
    "coffee": [
        ("coffee_katta", "Katta", 8000),
        ("coffee_kichkina", "Kichkina", 5000),
    ],
    "drinks": [
        ("cola_1_5", "1.5 L", 17000),
        ("cola_1", "1 L", 12000),
        ("cola_0_5", "0.5 L", 8000),
    ],
}


def find_item(item_id: str):
    for items in ITEMS.values():
        for iid, name, price in items:
            if iid == item_id:
                return name, price
    return None, None


def format_price(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " so'm"


def cart_total(cart: list) -> int:
    return sum(i["price"] * i["qty"] for i in cart)


def cart_text(cart: list) -> str:
    if not cart:
        return "🛒 Savat bo'sh."
    lines = ["🛒 <b>Savat</b>\n"]
    for i in cart:
        lines.append(f"• {i['name']} x{i['qty']} — {format_price(i['price'] * i['qty'])}")
    lines.append(f"\n<b>Jami: {format_price(cart_total(cart))}</b>")
    return "\n".join(lines)


def cart_order_line(cart: list) -> str:
    return ", ".join(f"{i['name']} x{i['qty']}" for i in cart)


# ── inline klaviaturalar ──────────────────────────────
def categories_kb() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=v, callback_data=f"cat:{k}")] for k, v in CATEGORIES.items()]
    buttons.append([InlineKeyboardButton(text="🛒 Savatni ko'rish", callback_data="show_cart")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def items_kb(cat: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{name} — {format_price(price)}", callback_data=f"item:{iid}")]
        for iid, name, price in ITEMS[cat]
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_cats")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def qty_kb(item_id: str, qty: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"qty_dec:{item_id}"),
            InlineKeyboardButton(text=str(qty), callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"qty_inc:{item_id}"),
        ],
        [InlineKeyboardButton(text="✅ Savatga qo'shish", callback_data=f"add:{item_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_cats")],
    ])


def cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yana mahsulot qo'shish", callback_data="back_cats")],
        [InlineKeyboardButton(text="✅ Buyurtmani yakunlash", callback_data="finish_order")],
        [InlineKeyboardButton(text="🗑 Savatni tozalash", callback_data="clear_cart")],
    ])


# ── pastdagi menyu ────────────────────────────────────
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌭 Menyu"), KeyboardButton(text="🛒 Buyurtma")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="🚚 Yetkazib berish")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Menyudan tanlang",
    )


def contact_share() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)],
                  [KeyboardButton(text="◀️ Bekor qilish")]],
        resize_keyboard=True,
    )


def cancel_only_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Bekor qilish")]],
        resize_keyboard=True,
    )


# ── holatlar (buyurtma bosqichlari) ───────────────────
class Order(StatesGroup):
    browsing = State()   # menyudan tugma orqali mahsulot/son tanlash
    phone = State()       # telefon
    address = State()     # manzil


# ── /start ────────────────────────────────────────────
@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🌭 <b>STREET HOT DOG</b> ga xush kelibsiz!\n\n"
        "«Yeysiz, yana bormi? deysiz» 😋\n\n"
        "Toshkentdagi eng mazali qazili hot-dog. "
        "Pastdagi menyudan tanlang:",
        reply_markup=main_menu(),
    )


# ── Menyu / Aloqa / Yetkazib berish ───────────────────
@router.message(F.text == "🌭 Menyu")
async def show_menu(message: Message) -> None:
    await message.answer(MENU, reply_markup=main_menu())


@router.message(F.text == "📞 Aloqa")
async def show_contact(message: Message) -> None:
    await message.answer(CONTACT, disable_web_page_preview=True, reply_markup=main_menu())


@router.message(F.text == "🚚 Yetkazib berish")
async def show_delivery(message: Message) -> None:
    await message.answer(DELIVERY, reply_markup=main_menu())


# ── Buyurtma: tugmalar orqali mahsulot tanlash ────────
@router.message(F.text == "🛒 Buyurtma")
async def order_start(message: Message, state: FSMContext) -> None:
    if ADMIN_ID == 0:
        await message.answer("Hozircha buyurtma qabul qilinmayapti. Qo'ng'iroq qiling: "
                             + PHONE, reply_markup=main_menu())
        return
    await state.set_state(Order.browsing)
    await state.update_data(cart=[], pending_item=None, pending_qty=1)
    await message.answer(
        "🛒 <b>Buyurtma</b>\n\n"
        "Kategoriyani tanlang, so'ng mahsulot va sonini belgilang:",
        reply_markup=categories_kb(),
    )


@router.callback_query(Order.browsing, F.data.startswith("cat:"))
async def cb_category(cb: CallbackQuery, state: FSMContext) -> None:
    cat = cb.data.split(":", 1)[1]
    await cb.message.edit_text(
        f"{CATEGORIES[cat]}\n\nMahsulotni tanlang:",
        reply_markup=items_kb(cat),
    )
    await cb.answer()


@router.callback_query(Order.browsing, F.data == "back_cats")
async def cb_back_cats(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.message.edit_text(
        "🛒 <b>Buyurtma</b>\n\nKategoriyani tanlang:",
        reply_markup=categories_kb(),
    )
    await cb.answer()


@router.callback_query(Order.browsing, F.data.startswith("item:"))
async def cb_item(cb: CallbackQuery, state: FSMContext) -> None:
    item_id = cb.data.split(":", 1)[1]
    name, price = find_item(item_id)
    await state.update_data(pending_item=item_id, pending_qty=1)
    await cb.message.edit_text(
        f"<b>{name}</b>\nNarxi: {format_price(price)}\n\nSonini tanlang:",
        reply_markup=qty_kb(item_id, 1),
    )
    await cb.answer()


@router.callback_query(Order.browsing, F.data.startswith("qty_inc:"))
async def cb_qty_inc(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    item_id = cb.data.split(":", 1)[1]
    qty = min(data.get("pending_qty", 1) + 1, 20)
    await state.update_data(pending_qty=qty)
    name, price = find_item(item_id)
    await cb.message.edit_text(
        f"<b>{name}</b>\nNarxi: {format_price(price)}\n\nSonini tanlang:",
        reply_markup=qty_kb(item_id, qty),
    )
    await cb.answer()


@router.callback_query(Order.browsing, F.data.startswith("qty_dec:"))
async def cb_qty_dec(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    item_id = cb.data.split(":", 1)[1]
    qty = max(data.get("pending_qty", 1) - 1, 1)
    await state.update_data(pending_qty=qty)
    name, price = find_item(item_id)
    await cb.message.edit_text(
        f"<b>{name}</b>\nNarxi: {format_price(price)}\n\nSonini tanlang:",
        reply_markup=qty_kb(item_id, qty),
    )
    await cb.answer()


@router.callback_query(Order.browsing, F.data.startswith("add:"))
async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    item_id = cb.data.split(":", 1)[1]
    qty = data.get("pending_qty", 1)
    name, price = find_item(item_id)
    cart = data.get("cart", [])
    for i in cart:
        if i["id"] == item_id:
            i["qty"] += qty
            break
    else:
        cart.append({"id": item_id, "name": name, "price": price, "qty": qty})
    await state.update_data(cart=cart, pending_item=None, pending_qty=1)
    await cb.message.edit_text(
        f"✅ Qo'shildi: {name} x{qty}\n\n{cart_text(cart)}",
        reply_markup=cart_kb(),
    )
    await cb.answer("Savatga qo'shildi")


@router.callback_query(Order.browsing, F.data == "show_cart")
async def cb_show_cart(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await cb.answer("Savat bo'sh — avval mahsulot tanlang", show_alert=True)
        return
    await cb.message.edit_text(cart_text(cart), reply_markup=cart_kb())
    await cb.answer()


@router.callback_query(Order.browsing, F.data == "clear_cart")
async def cb_clear_cart(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(cart=[])
    await cb.message.edit_text(
        "🛒 Savat tozalandi.\n\nKategoriyani tanlang:",
        reply_markup=categories_kb(),
    )
    await cb.answer()


@router.callback_query(Order.browsing, F.data == "finish_order")
async def cb_finish(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await cb.answer("Savat bo'sh — avval mahsulot tanlang", show_alert=True)
        return
    await state.set_state(Order.phone)
    await cb.message.edit_text(cart_text(cart))
    await cb.message.answer(
        "📱 Telefon raqamingizni yuboring (tugma orqali yoki qo'lda yozing):",
        reply_markup=contact_share(),
    )
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


# ── telefon / manzil ──────────────────────────────────
@router.message(Order.phone, F.contact)
async def order_phone_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(Order.address)
    await message.answer("📍 Yetkazish manzilingizni yozing:", reply_markup=cancel_only_kb())


@router.message(Order.phone, F.text)
async def order_phone_text(message: Message, state: FSMContext) -> None:
    if message.text == "◀️ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_menu())
        return
    await state.update_data(phone=message.text)
    await state.set_state(Order.address)
    await message.answer("📍 Yetkazish manzilingizni yozing:", reply_markup=cancel_only_kb())


@router.message(Order.address, F.text)
async def order_address(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.text == "◀️ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_menu())
        return

    data = await state.get_data()
    cart = data.get("cart", [])
    await state.clear()
    u = message.from_user
    uname = f"@{u.username}" if u.username else "—"

    order_line = cart_order_line(cart)
    total = format_price(cart_total(cart))

    # Admin'ga buyurtma
    order_text = (
        "🛒 <b>YANGI BUYURTMA</b>\n\n"
        f"🌭 Buyurtma: {order_line}\n"
        f"💰 Jami: {total}\n"
        f"📱 Telefon: {data.get('phone')}\n"
        f"📍 Manzil: {message.text}\n\n"
        f"👤 Mijoz: {u.full_name} ({uname})\n"
        f"🆔 <code>{u.id}</code>"
    )
    try:
        await bot.send_message(ADMIN_ID, order_text)
    except Exception:
        log.warning("Admin'ga yuborilmadi")

    # Mijozga tasdiq
    await message.answer(
        "✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"🌭 {order_line}\n"
        f"💰 Jami: {total}\n"
        f"📱 {data.get('phone')}\n"
        f"📍 {message.text}\n\n"
        "Tez orada operator siz bilan bog'lanadi. "
        f"Savol bo'lsa: {PHONE}",
        reply_markup=main_menu(),
    )


# ── admin buyurtmaga javob (ixtiyoriy) ────────────────
@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Sizning ID: <code>{message.from_user.id}</code>")


# ── boshqa har qanday xabar ───────────────────────────
@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("Pastdagi menyudan tanlang 👇", reply_markup=main_menu())


# ── ishga tushirish ───────────────────────────────────
async def set_commands(bot: Bot) -> None:
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash"),
    ])


async def main() -> None:
    if not TOKEN:
        raise SystemExit("BOT_TOKEN o'rnatilmagan.")
    if ADMIN_ID == 0:
        log.warning("ADMIN_ID sozlanmagan — buyurtmalar hech kimga bormaydi.")
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot ishga tushdi")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("To'xtatildi")
