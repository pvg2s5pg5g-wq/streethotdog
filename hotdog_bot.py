"""
STREET HOT DOG — Telegram bot
==============================

Komandalar / tugmalar:
  🌭 Menyu          — mahsulotlar va narxlar
  🛒 Buyurtma       — buyurtma berish (admin'ga keladi)
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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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


# ── holatlar (buyurtma bosqichlari) ───────────────────
class Order(StatesGroup):
    what = State()     # nima buyurtma
    phone = State()    # telefon
    address = State()  # manzil


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


# ── Buyurtma bosqichlari ──────────────────────────────
@router.message(F.text == "🛒 Buyurtma")
async def order_start(message: Message, state: FSMContext) -> None:
    if ADMIN_ID == 0:
        await message.answer("Hozircha buyurtma qabul qilinmayapti. Qo'ng'iroq qiling: "
                             + PHONE, reply_markup=main_menu())
        return
    await state.set_state(Order.what)
    await message.answer(
        "🛒 <b>Buyurtma</b>\n\n"
        "Nima buyurtma qilasiz? Mahsulot nomi va sonini yozing.\n\n"
        "Masalan: <i>2 ta katta qazili hot-dog, 1 ta coffee</i>\n\n"
        "Bekor qilish uchun /start bosing.",
    )


@router.message(Order.what, F.text)
async def order_what(message: Message, state: FSMContext) -> None:
    if message.text == "◀️ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_menu())
        return
    await state.update_data(what=message.text)
    await state.set_state(Order.phone)
    await message.answer(
        "📱 Telefon raqamingizni yuboring (tugma orqali yoki qo'lda yozing):",
        reply_markup=contact_share(),
    )


@router.message(Order.phone, F.contact)
async def order_phone_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(Order.address)
    await message.answer("📍 Yetkazish manzilingizni yozing:",
                         reply_markup=ReplyKeyboardMarkup(
                             keyboard=[[KeyboardButton(text="◀️ Bekor qilish")]],
                             resize_keyboard=True))


@router.message(Order.phone, F.text)
async def order_phone_text(message: Message, state: FSMContext) -> None:
    if message.text == "◀️ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_menu())
        return
    await state.update_data(phone=message.text)
    await state.set_state(Order.address)
    await message.answer("📍 Yetkazish manzilingizni yozing:",
                         reply_markup=ReplyKeyboardMarkup(
                             keyboard=[[KeyboardButton(text="◀️ Bekor qilish")]],
                             resize_keyboard=True))


@router.message(Order.address, F.text)
async def order_address(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.text == "◀️ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_menu())
        return

    data = await state.get_data()
    await state.clear()
    u = message.from_user
    uname = f"@{u.username}" if u.username else "—"

    # Admin'ga buyurtma
    order_text = (
        "🛒 <b>YANGI BUYURTMA</b>\n\n"
        f"🌭 Buyurtma: {data.get('what')}\n"
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
        f"🌭 {data.get('what')}\n"
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
