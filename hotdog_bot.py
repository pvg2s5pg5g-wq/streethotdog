"""
STREET HOT DOG — Telegram bot
Savatli buyurtma + to'lov + admin panel (kartalar, zakazlar, adminlar)
=====================================================================

Foydalanuvchi:
  🛒 Buyurtma → mahsulot → o'lcham → son(+/-) → savat → telefon → manzil
  → to'lov turi (Yetkazganda / Online karta) → tasdiq
  Zakaz bosh admin va barcha adminlarga tushadi.

Admin panel (/admin):
  💳 Kartalar   — online to'lov kartalarini qo'shish/o'chirish
  📋 Zakazlar   — barcha buyurtmalar, kim bergani
  👤 Adminlar   — admin qo'shish/o'chirish (faqat bosh admin)

Sozlash:
  BOT_TOKEN   — token
  ADMIN_ID    — bosh admin Telegram ID (siz)
  DATA_DIR    — /data  (Volume mount path bilan bir xil)
"""

import asyncio
import json
import logging
import os
import sqlite3
import time

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
OWNER_ID = int(os.getenv("ADMIN_ID", "0"))     # bosh admin (siz)
PHONE = "+998 90 096 87 70"
TG_CONTACT = "@sh0khrukh1"
SITE = "https://street-hotdog-uz.netlify.app"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)
router = Router()

# ── BAZA (Volume) ─────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "hotdog.db"))
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY, name TEXT)")
db.execute("""CREATE TABLE IF NOT EXISTS cards(
    id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, holder TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, user_id INTEGER, name TEXT, username TEXT,
    items TEXT, total INTEGER, phone TEXT, address TEXT, pay TEXT)""")
db.commit()


def is_admin(uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    return db.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None

def is_owner(uid: int) -> bool:
    return uid == OWNER_ID

def all_admin_ids():
    ids = {OWNER_ID}
    for (uid,) in db.execute("SELECT user_id FROM admins").fetchall():
        ids.add(uid)
    return [i for i in ids if i]

def add_admin(uid: int, name: str):
    db.execute("INSERT OR REPLACE INTO admins(user_id, name) VALUES(?,?)", (uid, name))
    db.commit()

def del_admin(uid: int):
    db.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    db.commit()

def list_admins():
    return db.execute("SELECT user_id, name FROM admins").fetchall()

def add_card(number: str, holder: str):
    db.execute("INSERT INTO cards(number, holder) VALUES(?,?)", (number, holder))
    db.commit()

def del_card(cid: int):
    db.execute("DELETE FROM cards WHERE id=?", (cid,))
    db.commit()

def list_cards():
    return db.execute("SELECT id, number, holder FROM cards ORDER BY id").fetchall()

def save_order(o: dict) -> int:
    cur = db.execute(
        "INSERT INTO orders(ts,user_id,name,username,items,total,phone,address,pay)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (int(time.time()), o["user_id"], o["name"], o["username"],
         json.dumps(o["items"], ensure_ascii=False), o["total"],
         o["phone"], o["address"], o["pay"]))
    db.commit()
    return cur.lastrowid

def recent_orders(limit=15):
    return db.execute(
        "SELECT id,ts,name,username,total,phone,address,pay FROM orders "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ── MAHSULOTLAR ───────────────────────────────────────
PRODUCTS = {
    "qazili":  {"name": "🌭 Qazili Hot-Dog",   "desc": "Mo'l-ko'l qazi, tuxum va maxsus sous bilan.",
                "sizes": [("2x-Katta",30000),("Katta",25000),("O'rtacha",20000),("Kichkina",15000)]},
    "salatli": {"name": "🌭 Salatli Hot-Dog",  "desc": "Yangi sabzavotlar, pomidor sousi va krem bilan.",
                "sizes": [("2x-Katta",37000),("Katta",25000),("O'rtacha",17000),("Kichkina",14000)]},
    "hotlet":  {"name": "🥪 Hot-Let",          "desc": "Go'sht taxtacha, pishloq va salat bargi bilan.",
                "sizes": [("Katta",30000),("Kichkina",22000)]},
    "burger":  {"name": "🍔 Gamburger",        "desc": "Sertane, mol go'shti va eritilgan pishloq bilan.",
                "sizes": [("Gamburger",22000),("Chizburger",25000),("Dabl burger",32000)]},
    "coffee":  {"name": "☕️ Coffee",           "desc": "Issiq va tetiklantiruvchi.",
                "sizes": [("Katta",8000),("Kichkina",5000)]},
    "drink":   {"name": "🥤 Salqin Ichimliklar","desc": "Coca-Cola, Fanta yoki Sprite.",
                "sizes": [("1.5 L",17000),("1 L",12000),("0.5 L",8000)]},
}

def money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " so'm"


CONTACT = f"""📞 <b>Bog'lanish</b>

Telefon: <a href="tel:+998900968770">{PHONE}</a>
Telegram: {TG_CONTACT}
Sayt: {SITE}

🕙 Ish vaqti: har kuni 10:00 – 23:00"""

DELIVERY = """🚚 <b>Yetkazib berish</b>

• Toshkent bo'ylab yetkazib beramiz
• 🔥 30 daqiqada yetkaziladi
• Maxsus issiq quticha bilan
• Manzil va narx qo'ng'iroqda aniqlashtiriladi

🕙 Har kuni 10:00 – 23:00"""


# ── pastdagi menyu ────────────────────────────────────
def main_menu(uid: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛒 Buyurtma"), KeyboardButton(text="🧺 Savat")],
        [KeyboardButton(text="🌭 Menyu"), KeyboardButton(text="📞 Aloqa")],
        [KeyboardButton(text="🚚 Yetkazib berish")],
    ]
    if is_admin(uid):
        rows.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               is_persistent=True, input_field_placeholder="Menyudan tanlang")


# ── inline klaviaturalar ──────────────────────────────
def products_kb():
    rows = [[InlineKeyboardButton(text=p["name"], callback_data=f"p:{pid}")]
            for pid, p in PRODUCTS.items()]
    rows.append([InlineKeyboardButton(text="🧺 Savatni ko'rish", callback_data="cart:show")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def sizes_kb(pid):
    rows = [[InlineKeyboardButton(text=f"{s} — {money(pr)}", callback_data=f"s:{pid}:{i}")]
            for i,(s,pr) in enumerate(PRODUCTS[pid]["sizes"])]
    rows.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back:products")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def qty_kb(pid, si, qty):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➖", callback_data=f"q:{pid}:{si}:{qty-1}"),
         InlineKeyboardButton(text=f"{qty} ta", callback_data="noop"),
         InlineKeyboardButton(text="➕", callback_data=f"q:{pid}:{si}:{qty+1}")],
        [InlineKeyboardButton(text="✅ Savatga qo'shish", callback_data=f"add:{pid}:{si}:{qty}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"back:sizes:{pid}")],
    ])

def cart_kb(has):
    rows = []
    if has:
        rows.append([InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="cart:order")])
        rows.append([InlineKeyboardButton(text="🗑 Tozalash", callback_data="cart:clear")])
    rows.append([InlineKeyboardButton(text="➕ Yana qo'shish", callback_data="back:products")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def pay_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Yetkazganda to'lash", callback_data="pay:cash")],
        [InlineKeyboardButton(text="💳 Online (karta)", callback_data="pay:online")],
    ])


# ── holatlar ──────────────────────────────────────────
class Order(StatesGroup):
    phone = State()
    address = State()
    pay = State()

class AdminSt(StatesGroup):
    card_number = State()
    card_holder = State()
    new_admin = State()


# ── savat yordamchilari ───────────────────────────────
async def get_cart(state): return (await state.get_data()).get("cart", [])
async def set_cart(state, cart): await state.update_data(cart=cart)

def cart_text(cart):
    if not cart:
        return "🧺 <b>Savat bo'sh.</b>\n\n«🛒 Buyurtma» orqali mahsulot qo'shing."
    lines = ["🧺 <b>Savatingiz:</b>\n"]; total = 0
    for it in cart:
        p = PRODUCTS[it["pid"]]; sname, pr = p["sizes"][it["si"]]
        sub = pr*it["qty"]; total += sub
        lines.append(f"• {p['name']} ({sname}) × {it['qty']} = {money(sub)}")
    lines.append(f"\n💰 <b>Jami: {money(total)}</b>")
    return "\n".join(lines)

def cart_total(cart):
    return sum(PRODUCTS[i["pid"]]["sizes"][i["si"]][1]*i["qty"] for i in cart)


# ── /start ────────────────────────────────────────────
@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.set_data({})
    await message.answer(
        "🌭 <b>STREET HOT DOG</b> ga xush kelibsiz!\n\n"
        "«Yeysiz, yana bormi? deysiz» 😋\n\n"
        "Buyurtma berish uchun «🛒 Buyurtma» ni bosing:",
        reply_markup=main_menu(message.from_user.id))


# ── Menyu / Aloqa / Yetkazish ─────────────────────────
@router.message(F.text == "🌭 Menyu")
async def show_menu(m: Message):
    parts = ["🌭 <b>STREET HOT DOG — MENYU</b>\n"]
    for p in PRODUCTS.values():
        parts.append(f"\n<b>{p['name']}</b>\n<i>{p['desc']}</i>")
        for s,pr in p["sizes"]:
            parts.append(f"• {s} — {money(pr)}")
    await m.answer("\n".join(parts), reply_markup=main_menu(m.from_user.id))

@router.message(F.text == "📞 Aloqa")
async def show_contact(m: Message):
    await m.answer(CONTACT, disable_web_page_preview=True, reply_markup=main_menu(m.from_user.id))

@router.message(F.text == "🚚 Yetkazib berish")
async def show_delivery(m: Message):
    await m.answer(DELIVERY, reply_markup=main_menu(m.from_user.id))


# ── buyurtma / savat ──────────────────────────────────
@router.message(F.text == "🛒 Buyurtma")
async def order_start(m: Message):
    if not all_admin_ids():
        await m.answer("Hozircha buyurtma qabul qilinmayapti. Qo'ng'iroq: " + PHONE); return
    await m.answer("🛒 Mahsulotni tanlang:", reply_markup=products_kb())

@router.message(F.text == "🧺 Savat")
async def cart_msg(m: Message, state: FSMContext):
    cart = await get_cart(state)
    await m.answer(cart_text(cart), reply_markup=cart_kb(bool(cart)))

@router.callback_query(F.data == "noop")
async def noop(c): await c.answer()

@router.callback_query(F.data == "back:products")
async def back_products(c: CallbackQuery):
    await c.message.edit_text("🛒 Mahsulotni tanlang:", reply_markup=products_kb()); await c.answer()

@router.callback_query(F.data.startswith("p:"))
async def choose_product(c: CallbackQuery):
    pid = c.data.split(":",1)[1]; p = PRODUCTS[pid]
    await c.message.edit_text(f"<b>{p['name']}</b>\n<i>{p['desc']}</i>\n\nO'lchamni tanlang:",
                              reply_markup=sizes_kb(pid)); await c.answer()

@router.callback_query(F.data.startswith("back:sizes:"))
async def back_sizes(c: CallbackQuery):
    pid = c.data.split(":")[2]; p = PRODUCTS[pid]
    await c.message.edit_text(f"<b>{p['name']}</b>\n<i>{p['desc']}</i>\n\nO'lchamni tanlang:",
                              reply_markup=sizes_kb(pid)); await c.answer()

@router.callback_query(F.data.startswith("s:"))
async def choose_size(c: CallbackQuery):
    _, pid, si = c.data.split(":"); si=int(si)
    sname, pr = PRODUCTS[pid]["sizes"][si]
    await c.message.edit_text(f"<b>{PRODUCTS[pid]['name']}</b> — {sname}\nNarxi: {money(pr)}\n\nSonini tanlang:",
                              reply_markup=qty_kb(pid,si,1)); await c.answer()

@router.callback_query(F.data.startswith("q:"))
async def change_qty(c: CallbackQuery):
    _, pid, si, qty = c.data.split(":"); si,qty=int(si),int(qty)
    qty = max(1, min(50, qty))
    sname, pr = PRODUCTS[pid]["sizes"][si]
    await c.message.edit_text(
        f"<b>{PRODUCTS[pid]['name']}</b> — {sname}\nNarxi: {money(pr)} × {qty} = {money(pr*qty)}\n\nSonini tanlang:",
        reply_markup=qty_kb(pid,si,qty)); await c.answer()

@router.callback_query(F.data.startswith("add:"))
async def add_cart(c: CallbackQuery, state: FSMContext):
    _, pid, si, qty = c.data.split(":"); si,qty=int(si),int(qty)
    cart = await get_cart(state)
    for it in cart:
        if it["pid"]==pid and it["si"]==si:
            it["qty"]+=qty; break
    else:
        cart.append({"pid":pid,"si":si,"qty":qty})
    await set_cart(state, cart)
    await c.message.edit_text(cart_text(cart)+"\n\n✅ Qo'shildi!", reply_markup=cart_kb(True))
    await c.answer("Savatga qo'shildi")

@router.callback_query(F.data == "cart:show")
async def cart_show(c: CallbackQuery, state: FSMContext):
    cart = await get_cart(state)
    await c.message.edit_text(cart_text(cart), reply_markup=cart_kb(bool(cart))); await c.answer()

@router.callback_query(F.data == "cart:clear")
async def cart_clear(c: CallbackQuery, state: FSMContext):
    await set_cart(state, [])
    await c.message.edit_text("🧺 Savat tozalandi.", reply_markup=cart_kb(False)); await c.answer("Tozalandi")


# ── buyurtma → telefon → manzil → to'lov ──────────────
@router.callback_query(F.data == "cart:order")
async def cart_order(c: CallbackQuery, state: FSMContext):
    if not await get_cart(state):
        await c.answer("Savat bo'sh.", show_alert=True); return
    await state.set_state(Order.phone)
    await c.message.answer("📱 Telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)],
                      [KeyboardButton(text="◀️ Bekor qilish")]], resize_keyboard=True))
    await c.answer()

@router.message(Order.phone, F.contact)
async def phone_c(m: Message, state: FSMContext):
    await state.update_data(phone=m.contact.phone_number); await ask_addr(m, state)

@router.message(Order.phone, F.text)
async def phone_t(m: Message, state: FSMContext):
    if m.text == "◀️ Bekor qilish":
        await state.set_state(None); await m.answer("Bekor qilindi.", reply_markup=main_menu(m.from_user.id)); return
    await state.update_data(phone=m.text); await ask_addr(m, state)

async def ask_addr(m, state):
    await state.set_state(Order.address)
    await m.answer("📍 Yetkazish manzilingizni yozing:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="◀️ Bekor qilish")]], resize_keyboard=True))

@router.message(Order.address, F.text)
async def got_addr(m: Message, state: FSMContext):
    if m.text == "◀️ Bekor qilish":
        await state.set_state(None); await m.answer("Bekor qilindi.", reply_markup=main_menu(m.from_user.id)); return
    await state.update_data(address=m.text)
    await state.set_state(Order.pay)
    await m.answer("💰 <b>To'lov turini tanlang:</b>", reply_markup=pay_kb())


@router.callback_query(Order.pay, F.data.startswith("pay:"))
async def choose_pay(c: CallbackQuery, state: FSMContext, bot: Bot):
    pay = "Yetkazganda" if c.data == "pay:cash" else "Online (karta)"
    data = await state.get_data()
    cart = data.get("cart", [])
    total = cart_total(cart)
    u = c.from_user
    uname = f"@{u.username}" if u.username else "—"

    # bazaga saqlash
    oid = save_order({
        "user_id": u.id, "name": u.full_name, "username": uname,
        "items": cart, "total": total,
        "phone": data.get("phone"), "address": data.get("address"), "pay": pay,
    })

    # adminlarga xabar
    lines = [f"🛒 <b>YANGI BUYURTMA #{oid}</b>\n"]
    for it in cart:
        p = PRODUCTS[it["pid"]]; sname, pr = p["sizes"][it["si"]]
        lines.append(f"• {p['name']} ({sname}) × {it['qty']} = {money(pr*it['qty'])}")
    lines.append(f"\n💰 Jami: <b>{money(total)}</b>")
    lines.append(f"💳 To'lov: {pay}")
    lines.append(f"📱 {data.get('phone')}")
    lines.append(f"📍 {data.get('address')}")
    lines.append(f"\n👤 {u.full_name} ({uname}) · 🆔 <code>{u.id}</code>")
    order_msg = "\n".join(lines)
    for aid in all_admin_ids():
        try: await bot.send_message(aid, order_msg)
        except Exception: pass

    await state.set_data({})

    # foydalanuvchiga
    if c.data == "pay:online":
        cards = list_cards()
        if cards:
            ctext = "\n".join(f"💳 <code>{num}</code>\n👤 {holder}" for _,num,holder in cards)
        else:
            ctext = "💳 <code>xxxx xxxx xxxx xxxx</code>"
        await c.message.edit_text(
            f"✅ <b>Buyurtma #{oid} qabul qilindi!</b>\n\n"
            f"💳 <b>Online to'lov uchun karta:</b>\n\n{ctext}\n\n"
            f"💰 To'lov summasi: <b>{money(total)}</b>\n\n"
            "To'lovni amalga oshirib, chekni operatorga yuboring. "
            f"Savol bo'lsa: {PHONE}")
    else:
        await c.message.edit_text(
            f"✅ <b>Buyurtma #{oid} qabul qilindi!</b>\n\n"
            f"💰 Summa: <b>{money(total)}</b>\n💳 To'lov: yetkazganda\n\n"
            f"Tez orada operator bog'lanadi. Savol bo'lsa: {PHONE}")
    await c.message.answer("Bosh menyu 👇", reply_markup=main_menu(u.id))
    await c.answer()


# ══════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════
def admin_kb(uid):
    rows = [
        [InlineKeyboardButton(text="📋 Zakazlar", callback_data="a:orders")],
        [InlineKeyboardButton(text="💳 Kartalar", callback_data="a:cards")],
    ]
    if is_owner(uid):
        rows.append([InlineKeyboardButton(text="👤 Adminlar", callback_data="a:admins")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(F.text == "🛠 Admin panel")
async def admin_panel(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("🛠 <b>Admin panel</b>", reply_markup=admin_kb(m.from_user.id))


# ── Zakazlar ──────────────────────────────────────────
@router.callback_query(F.data == "a:orders")
async def a_orders(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True); return
    rows = recent_orders()
    if not rows:
        await c.message.edit_text("📋 Hali zakaz yo'q.", reply_markup=admin_kb(c.from_user.id)); await c.answer(); return
    out = ["📋 <b>So'nggi zakazlar:</b>\n"]
    for oid, ts, name, uname, total, phone, addr, pay in rows:
        t = time.strftime("%d.%m %H:%M", time.localtime(ts))
        out.append(f"<b>#{oid}</b> · {t} · {money(total)} · {pay}\n"
                   f"👤 {name} ({uname})\n📱 {phone} · 📍 {addr}\n")
    out.append("\n<i>Batafsil: /zakaz raqam (masalan /zakaz 5)</i>")
    await c.message.edit_text("\n".join(out), reply_markup=admin_kb(c.from_user.id))
    await c.answer()

@router.message(Command("zakaz"))
async def zakaz_detail(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await m.answer("Format: /zakaz 5"); return
    row = db.execute("SELECT id,ts,name,username,items,total,phone,address,pay,user_id "
                     "FROM orders WHERE id=?", (int(parts[1]),)).fetchone()
    if not row:
        await m.answer("Bunday zakaz yo'q."); return
    oid,ts,name,uname,items,total,phone,addr,pay,uid = row
    its = json.loads(items)
    lines = [f"📋 <b>ZAKAZ #{oid}</b>\n"]
    for it in its:
        p = PRODUCTS[it["pid"]]; sname, pr = p["sizes"][it["si"]]
        lines.append(f"• {p['name']} ({sname}) × {it['qty']} = {money(pr*it['qty'])}")
    lines.append(f"\n💰 Jami: <b>{money(total)}</b>\n💳 {pay}\n📱 {phone}\n📍 {addr}")
    lines.append(f"\n👤 {name} ({uname}) · 🆔 <code>{uid}</code>")
    lines.append(f"🕙 {time.strftime('%d.%m.%Y %H:%M', time.localtime(ts))}")
    await m.answer("\n".join(lines))


# ── Kartalar ──────────────────────────────────────────
def cards_kb(uid):
    rows = [[InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="card:add")]]
    for cid, num, holder in list_cards():
        rows.append([InlineKeyboardButton(text=f"🗑 {num} ({holder})", callback_data=f"card:del:{cid}")])
    rows.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="a:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data == "a:cards")
async def a_cards(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True); return
    cards = list_cards()
    txt = "💳 <b>Online to'lov kartalari</b>\n\n"
    txt += ("\n".join(f"• <code>{n}</code> — {h}" for _,n,h in cards) if cards
            else "Hozircha karta yo'q.")
    txt += "\n\n🗑 tugmasi — o'chirish."
    await c.message.edit_text(txt, reply_markup=cards_kb(c.from_user.id)); await c.answer()

@router.callback_query(F.data == "card:add")
async def card_add(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True); return
    await state.set_state(AdminSt.card_number)
    await c.message.answer("💳 Karta raqamini yuboring (16 xona):")
    await c.answer()

@router.message(AdminSt.card_number, F.text)
async def card_num(m: Message, state: FSMContext):
    num = m.text.replace(" ", "")
    if not (num.isdigit() and len(num) == 16):
        await m.answer("⚠️ 16 xonali raqam kiriting:"); return
    pretty = " ".join(num[i:i+4] for i in range(0,16,4))
    await state.update_data(card_number=pretty)
    await state.set_state(AdminSt.card_holder)
    await m.answer("👤 Karta egasi ismini yuboring:")

@router.message(AdminSt.card_holder, F.text)
async def card_hold(m: Message, state: FSMContext):
    data = await state.get_data()
    add_card(data["card_number"], m.text.strip().upper())
    await state.set_state(None)
    await m.answer("✅ Karta qo'shildi.", reply_markup=main_menu(m.from_user.id))

@router.callback_query(F.data.startswith("card:del:"))
async def card_del(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True); return
    del_card(int(c.data.split(":")[2]))
    cards = list_cards()
    txt = "💳 <b>Online to'lov kartalari</b>\n\n"
    txt += ("\n".join(f"• <code>{n}</code> — {h}" for _,n,h in cards) if cards else "Hozircha karta yo'q.")
    await c.message.edit_text(txt, reply_markup=cards_kb(c.from_user.id)); await c.answer("O'chirildi")


# ── Adminlar (faqat bosh admin) ───────────────────────
def admins_kb():
    rows = [[InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm:add")]]
    for uid, name in list_admins():
        rows.append([InlineKeyboardButton(text=f"🗑 {name or uid}", callback_data=f"adm:del:{uid}")])
    rows.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="a:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data == "a:admins")
async def a_admins(c: CallbackQuery):
    if not is_owner(c.from_user.id):
        await c.answer("Faqat bosh admin uchun", show_alert=True); return
    admins = list_admins()
    txt = "👤 <b>Adminlar</b>\n\n"
    txt += ("\n".join(f"• {name or uid} (<code>{uid}</code>)" for uid,name in admins)
            if admins else "Boshqa admin yo'q.")
    txt += "\n\n🗑 — adminni olib tashlash."
    await c.message.edit_text(txt, reply_markup=admins_kb()); await c.answer()

@router.callback_query(F.data == "adm:add")
async def adm_add(c: CallbackQuery, state: FSMContext):
    if not is_owner(c.from_user.id):
        await c.answer("Faqat bosh admin", show_alert=True); return
    await state.set_state(AdminSt.new_admin)
    await c.message.answer("👤 Yangi admin Telegram <b>ID</b> raqamini yuboring.\n"
                           "(U @userinfobot ga yozib ID'sini olsin)")
    await c.answer()

@router.message(AdminSt.new_admin, F.text)
async def adm_save(m: Message, state: FSMContext):
    await state.set_state(None)
    if not m.text.strip().isdigit():
        await m.answer("⚠️ Faqat raqam kiriting.", reply_markup=main_menu(m.from_user.id)); return
    uid = int(m.text.strip())
    add_admin(uid, f"admin{uid}")
    await m.answer(f"✅ Admin qo'shildi: <code>{uid}</code>", reply_markup=main_menu(m.from_user.id))

@router.callback_query(F.data.startswith("adm:del:"))
async def adm_del(c: CallbackQuery):
    if not is_owner(c.from_user.id):
        await c.answer("Faqat bosh admin", show_alert=True); return
    del_admin(int(c.data.split(":")[2]))
    admins = list_admins()
    txt = "👤 <b>Adminlar</b>\n\n"
    txt += ("\n".join(f"• {name or uid} (<code>{uid}</code>)" for uid,name in admins) if admins else "Boshqa admin yo'q.")
    await c.message.edit_text(txt, reply_markup=admins_kb()); await c.answer("O'chirildi")

@router.callback_query(F.data == "a:back")
async def a_back(c: CallbackQuery):
    await c.message.edit_text("🛠 <b>Admin panel</b>", reply_markup=admin_kb(c.from_user.id)); await c.answer()


# ── boshqa matn ───────────────────────────────────────
@router.message(F.text)
async def fallback(m: Message):
    await m.answer("Pastdagi menyudan tanlang 👇", reply_markup=main_menu(m.from_user.id))


# ── ishga tushirish ───────────────────────────────────
async def set_commands(bot: Bot):
    from aiogram.types import BotCommand
    await bot.set_my_commands([BotCommand(command="start", description="Boshlash")])

async def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN o'rnatilmagan.")
    if OWNER_ID == 0:
        log.warning("ADMIN_ID sozlanmagan.")
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(); dp.include_router(router)
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Baza: %s", DB_PATH)
    log.info("Bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("To'xtatildi")
