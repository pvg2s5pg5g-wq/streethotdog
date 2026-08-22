"""
STREET HOT DOG — Telegram bot (to'liq)
======================================
Savatli buyurtma + to'lov turi + yetkazib berish/olib ketish + lokatsiya/hudud + qabul qilish + eslatma + admin panel

Foydalanuvchi:
  🛒 Buyurtma → mahsulot → o'lcham → son(+/-) → savat
  → 💰 to'lov turi → 🚚 yetkazib berish / 🏃 olib ketish
     → telefon → (yetkazib berish bo'lsa) 📍 joylashuv (Telegram lokatsiya)
                 (olib ketish bo'lsa) 📍 Chirchiq hududini tanlash → tasdiq

Admin (siz + tayinlaganlaringiz):
  • Yangi zakaz kelganda «✅ Qabul qilish» tugmasi bilan keladi (lokatsiya/hudud bilan)
  • Qabul qilinmasa har 2 daqiqada eslatib turadi
  • Qabul qilingach mijozga xabar boradi
  🛠 Admin panel: 📋 Zakazlar · 💳 Kartalar · 👤 Adminlar (faqat bosh admin)

Sozlash: BOT_TOKEN, ADMIN_ID, DATA_DIR=/data (+ Volume mount /data)
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
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

# ── SOZLAMALAR ────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("ADMIN_ID", "0"))
PHONE = "+998 90 096 87 70"
TG_CONTACT = "@sh0khrukh1"
SITE = "https://street-hotdog-uz.netlify.app"
REMIND_SEC = 120          # eslatma oralig'i (2 daqiqa)

# Chirchiqdagi xizmat ko'rsatiladigan / olib ketish mumkin bo'lgan hududlar
CHIRCHIQ_AREAS = ["Yangiobod", "Do'stlik", "Yubileyniy", "Guliston", "Nurafshon"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)
router = Router()
bot_ref = {"bot": None}   # eslatma tsikli uchun

# ── BAZA (Volume) ─────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "hotdog.db"))
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY, name TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS cards(id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, holder TEXT)")
db.execute("""CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, user_id INTEGER, name TEXT, username TEXT,
    items TEXT, total INTEGER, phone TEXT,
    lat REAL, lon REAL, pay TEXT, method TEXT, area TEXT,
    status TEXT DEFAULT 'new',          -- new | accepted
    accepted_by INTEGER, last_remind INTEGER DEFAULT 0)""")
db.commit()
# Eski bazalarda (yangi ustunlarsiz) migratsiya
for _col in ("method", "area"):
    try:
        db.execute(f"ALTER TABLE orders ADD COLUMN {_col} TEXT")
        db.commit()
    except sqlite3.OperationalError:
        pass

def is_admin(uid): 
    return uid == OWNER_ID or db.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None
def is_owner(uid): return uid == OWNER_ID
def all_admin_ids():
    ids = {OWNER_ID}
    for (u,) in db.execute("SELECT user_id FROM admins"): ids.add(u)
    return [i for i in ids if i]
def add_admin(uid, name): db.execute("INSERT OR REPLACE INTO admins VALUES(?,?)", (uid,name)); db.commit()
def del_admin(uid): db.execute("DELETE FROM admins WHERE user_id=?", (uid,)); db.commit()
def list_admins(): return db.execute("SELECT user_id,name FROM admins").fetchall()
def add_card(n,h): db.execute("INSERT INTO cards(number,holder) VALUES(?,?)",(n,h)); db.commit()
def del_card(cid): db.execute("DELETE FROM cards WHERE id=?", (cid,)); db.commit()
def list_cards(): return db.execute("SELECT id,number,holder FROM cards ORDER BY id").fetchall()

def save_order(o):
    cur = db.execute(
        "INSERT INTO orders(ts,user_id,name,username,items,total,phone,lat,lon,pay,method,area,status,last_remind)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'new', ?)",
        (int(time.time()), o["user_id"], o["name"], o["username"],
         json.dumps(o["items"], ensure_ascii=False), o["total"], o["phone"],
         o.get("lat"), o.get("lon"), o["pay"], o.get("method"), o.get("area"), int(time.time())))
    db.commit(); return cur.lastrowid

def get_order(oid): 
    return db.execute("SELECT id,ts,user_id,name,username,items,total,phone,lat,lon,pay,status,accepted_by,method,area "
                      "FROM orders WHERE id=?", (oid,)).fetchone()
def accept_order(oid, uid):
    db.execute("UPDATE orders SET status='accepted', accepted_by=? WHERE id=?", (uid,oid)); db.commit()
def recent_orders(limit=15):
    return db.execute("SELECT id,ts,name,username,total,phone,pay,status FROM orders ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
def pending_orders():
    return db.execute("SELECT id,last_remind FROM orders WHERE status='new'").fetchall()
def touch_remind(oid):
    db.execute("UPDATE orders SET last_remind=? WHERE id=?", (int(time.time()),oid)); db.commit()


# ── MAHSULOTLAR ───────────────────────────────────────
PRODUCTS = {
    "qazili":{"name":"🌭 Qazili Hot-Dog","desc":"Mo'l-ko'l qazi, tuxum va maxsus sous bilan.",
              "sizes":[("2x-Katta",30000),("Katta",25000),("O'rtacha",20000),("Kichkina",15000)]},
    "salatli":{"name":"🌭 Salatli Hot-Dog","desc":"Yangi sabzavotlar, pomidor sousi va krem bilan.",
              "sizes":[("2x-Katta",30000),("Katta",25000),("O'rtacha",17000),("Kichkina",14000)]},
    "hotlet":{"name":"🥪 Hot-Let","desc":"Go'sht taxtacha, pishloq va salat bargi bilan.",
              "sizes":[("Katta",30000),("Kichkina",22000)]},
    "burger":{"name":"🍔 Gamburger","desc":"Sertane, mol go'shti va eritilgan pishloq bilan.",
              "sizes":[("Gamburger",22000),("Chizburger",25000),("Dabl burger",32000)]},
    "coffee":{"name":"☕️ Coffee","desc":"Issiq va tetiklantiruvchi.",
              "sizes":[("Katta",8000),("Kichkina",5000)]},
    "drink":{"name":"🥤 Salqin Ichimliklar","desc":"Coca-Cola, Fanta yoki Sprite.",
              "sizes":[("1.5 L",17000),("1 L",12000),("0.5 L",8000)]},
}
def money(n): return f"{n:,}".replace(",", " ") + " so'm"

CONTACT = f"""📞 <b>Bog'lanish</b>

Telefon: <a href="tel:+998900968770">{PHONE}</a>
Telegram: {TG_CONTACT}
Sayt: {SITE}

🕙 Ish vaqti: har kuni 10:00 – 23:00"""

DELIVERY = f"""🚚 <b>Yetkazib berish</b>

• Chirchiq bo'ylab yetkazib beramiz
• Xizmat hududlarimiz: {', '.join(CHIRCHIQ_AREAS)}
• 🔥 30 daqiqada yetkaziladi
• Maxsus issiq quticha bilan

🕙 Har kuni 10:00 – 23:00"""


def main_menu(uid):
    rows = [[KeyboardButton(text="🛒 Buyurtma"), KeyboardButton(text="🧺 Savat")],
            [KeyboardButton(text="🌭 Menyu"), KeyboardButton(text="📞 Aloqa")],
            [KeyboardButton(text="🚚 Yetkazib berish")]]
    if is_admin(uid): rows.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True,
                               input_field_placeholder="Menyudan tanlang")

def products_kb():
    rows=[[InlineKeyboardButton(text=p["name"],callback_data=f"p:{pid}")] for pid,p in PRODUCTS.items()]
    rows.append([InlineKeyboardButton(text="🧺 Savatni ko'rish",callback_data="cart:show")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def sizes_kb(pid):
    rows=[[InlineKeyboardButton(text=f"{s} — {money(pr)}",callback_data=f"s:{pid}:{i}")]
          for i,(s,pr) in enumerate(PRODUCTS[pid]["sizes"])]
    rows.append([InlineKeyboardButton(text="◀️ Orqaga",callback_data="back:products")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def qty_kb(pid,si,qty):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➖",callback_data=f"q:{pid}:{si}:{qty-1}"),
         InlineKeyboardButton(text=f"{qty} ta",callback_data="noop"),
         InlineKeyboardButton(text="➕",callback_data=f"q:{pid}:{si}:{qty+1}")],
        [InlineKeyboardButton(text="✅ Savatga qo'shish",callback_data=f"add:{pid}:{si}:{qty}")],
        [InlineKeyboardButton(text="◀️ Orqaga",callback_data=f"back:sizes:{pid}")]])
def cart_kb(has):
    rows=[]
    if has:
        rows.append([InlineKeyboardButton(text="✅ Buyurtma berish",callback_data="cart:order")])
        rows.append([InlineKeyboardButton(text="🗑 Tozalash",callback_data="cart:clear")])
    rows.append([InlineKeyboardButton(text="➕ Yana qo'shish",callback_data="back:products")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def pay_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Naqd (qabul qilganda)",callback_data="pay:cash")],
        [InlineKeyboardButton(text="💳 Online (karta)",callback_data="pay:online")]])
def method_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Yetkazib berish",callback_data="method:delivery")],
        [InlineKeyboardButton(text="🏃 Olib ketish",callback_data="method:pickup")],
        [InlineKeyboardButton(text="◀️ Bekor qilish",callback_data="method:cancel")]])
def pickup_kb():
    rows=[[InlineKeyboardButton(text=a,callback_data=f"area:{i}")] for i,a in enumerate(CHIRCHIQ_AREAS)]
    rows.append([InlineKeyboardButton(text="◀️ Bekor qilish",callback_data="area:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)],
                  [KeyboardButton(text="◀️ Bekor qilish")]], resize_keyboard=True)
def accept_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Zakazni qabul qilish",callback_data=f"acc:{oid}")]])


class Order(StatesGroup):
    pay = State(); method = State(); phone = State(); location = State(); pickup_area = State()
class AdminSt(StatesGroup):
    card_number = State(); card_holder = State(); new_admin = State()


async def get_cart(state): return (await state.get_data()).get("cart", [])
async def set_cart(state,cart): await state.update_data(cart=cart)
def cart_text(cart):
    if not cart: return "🧺 <b>Savat bo'sh.</b>\n\n«🛒 Buyurtma» orqali mahsulot qo'shing."
    lines=["🧺 <b>Savatingiz:</b>\n"]; total=0
    for it in cart:
        p=PRODUCTS[it["pid"]]; s,pr=p["sizes"][it["si"]]; sub=pr*it["qty"]; total+=sub
        lines.append(f"• {p['name']} ({s}) × {it['qty']} = {money(sub)}")
    lines.append(f"\n💰 <b>Jami: {money(total)}</b>"); return "\n".join(lines)
def cart_total(cart): return sum(PRODUCTS[i["pid"]]["sizes"][i["si"]][1]*i["qty"] for i in cart)
def items_text(items):
    out=[]
    for it in items:
        p=PRODUCTS[it["pid"]]; s,pr=p["sizes"][it["si"]]
        out.append(f"• {p['name']} ({s}) × {it['qty']} = {money(pr*it['qty'])}")
    return "\n".join(out)


# ── /start ────────────────────────────────────────────
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.set_data({})
    await m.answer("🌭 <b>STREET HOT DOG</b> ga xush kelibsiz!\n\n"
                   "«Yeysiz, yana bormi? deysiz» 😋\n\n"
                   "Buyurtma berish uchun «🛒 Buyurtma» ni bosing:",
                   reply_markup=main_menu(m.from_user.id))

@router.message(F.text == "🌭 Menyu")
async def show_menu(m: Message):
    parts=["🌭 <b>STREET HOT DOG — MENYU</b>\n"]
    for p in PRODUCTS.values():
        parts.append(f"\n<b>{p['name']}</b>\n<i>{p['desc']}</i>")
        for s,pr in p["sizes"]: parts.append(f"• {s} — {money(pr)}")
    await m.answer("\n".join(parts), reply_markup=main_menu(m.from_user.id))

@router.message(F.text == "📞 Aloqa")
async def show_contact(m: Message):
    await m.answer(CONTACT, disable_web_page_preview=True, reply_markup=main_menu(m.from_user.id))

@router.message(F.text == "🚚 Yetkazib berish")
async def show_delivery(m: Message):
    await m.answer(DELIVERY, reply_markup=main_menu(m.from_user.id))

@router.message(F.text == "🛒 Buyurtma")
async def order_start(m: Message):
    await m.answer("🛒 Mahsulotni tanlang:", reply_markup=products_kb())

@router.message(F.text == "🧺 Savat")
async def cart_msg(m: Message, state: FSMContext):
    cart=await get_cart(state); await m.answer(cart_text(cart), reply_markup=cart_kb(bool(cart)))

@router.callback_query(F.data=="noop")
async def noop(c): await c.answer()
@router.callback_query(F.data=="back:products")
async def back_products(c):
    await c.message.edit_text("🛒 Mahsulotni tanlang:", reply_markup=products_kb()); await c.answer()
@router.callback_query(F.data.startswith("p:"))
async def choose_product(c):
    pid=c.data.split(":",1)[1]; p=PRODUCTS[pid]
    await c.message.edit_text(f"<b>{p['name']}</b>\n<i>{p['desc']}</i>\n\nO'lchamni tanlang:",reply_markup=sizes_kb(pid)); await c.answer()
@router.callback_query(F.data.startswith("back:sizes:"))
async def back_sizes(c):
    pid=c.data.split(":")[2]; p=PRODUCTS[pid]
    await c.message.edit_text(f"<b>{p['name']}</b>\n<i>{p['desc']}</i>\n\nO'lchamni tanlang:",reply_markup=sizes_kb(pid)); await c.answer()
@router.callback_query(F.data.startswith("s:"))
async def choose_size(c):
    _,pid,si=c.data.split(":"); si=int(si); s,pr=PRODUCTS[pid]["sizes"][si]
    await c.message.edit_text(f"<b>{PRODUCTS[pid]['name']}</b> — {s}\nNarxi: {money(pr)}\n\nSonini tanlang:",reply_markup=qty_kb(pid,si,1)); await c.answer()
@router.callback_query(F.data.startswith("q:"))
async def change_qty(c):
    _,pid,si,qty=c.data.split(":"); si,qty=int(si),max(1,min(50,int(qty))); s,pr=PRODUCTS[pid]["sizes"][si]
    await c.message.edit_text(f"<b>{PRODUCTS[pid]['name']}</b> — {s}\nNarxi: {money(pr)} × {qty} = {money(pr*qty)}\n\nSonini tanlang:",reply_markup=qty_kb(pid,si,qty)); await c.answer()
@router.callback_query(F.data.startswith("add:"))
async def add_cart(c, state: FSMContext):
    _,pid,si,qty=c.data.split(":"); si,qty=int(si),int(qty); cart=await get_cart(state)
    for it in cart:
        if it["pid"]==pid and it["si"]==si: it["qty"]+=qty; break
    else: cart.append({"pid":pid,"si":si,"qty":qty})
    await set_cart(state,cart)
    await c.message.edit_text(cart_text(cart)+"\n\n✅ Qo'shildi!", reply_markup=cart_kb(True)); await c.answer("Qo'shildi")
@router.callback_query(F.data=="cart:show")
async def cart_show(c, state: FSMContext):
    cart=await get_cart(state); await c.message.edit_text(cart_text(cart), reply_markup=cart_kb(bool(cart))); await c.answer()
@router.callback_query(F.data=="cart:clear")
async def cart_clear(c, state: FSMContext):
    await set_cart(state,[]); await c.message.edit_text("🧺 Savat tozalandi.", reply_markup=cart_kb(False)); await c.answer("Tozalandi")


# ── buyurtma: to'lov turi → usul (yetkazib berish/olib ketish) → telefon → lokatsiya/hudud ──
@router.callback_query(F.data=="cart:order")
async def cart_order(c, state: FSMContext):
    if not await get_cart(state):
        await c.answer("Savat bo'sh.", show_alert=True); return
    await state.set_state(Order.pay)
    await c.message.answer("💰 <b>To'lov turini tanlang:</b>", reply_markup=pay_kb())
    await c.answer()

@router.callback_query(Order.pay, F.data.startswith("pay:"))
async def choose_pay(c: CallbackQuery, state: FSMContext):
    pay = "Naqd (qabul qilganda)" if c.data=="pay:cash" else "Online (karta)"
    await state.update_data(pay=pay)
    await state.set_state(Order.method)
    await c.message.edit_text("🚚 <b>Buyurtmani qanday olmoqchisiz?</b>", reply_markup=method_kb())
    await c.answer()

@router.callback_query(Order.method, F.data.startswith("method:"))
async def choose_method(c: CallbackQuery, state: FSMContext):
    if c.data == "method:cancel":
        await state.set_state(None)
        await c.message.edit_text("Bekor qilindi.")
        await c.answer(); return
    method = "Yetkazib berish" if c.data=="method:delivery" else "Olib ketish"
    await state.update_data(method=method)
    await state.set_state(Order.phone)
    await c.message.answer("📱 Telefon raqamingizni yuboring:", reply_markup=phone_kb())
    await c.answer()

@router.message(Order.phone, F.contact)
async def phone_c(m: Message, state: FSMContext):
    await state.update_data(phone=m.contact.phone_number); await proceed_after_phone(m, state)
@router.message(Order.phone, F.text)
async def phone_t(m: Message, state: FSMContext):
    if m.text=="◀️ Bekor qilish":
        await state.set_state(None); await m.answer("Bekor qilindi.", reply_markup=main_menu(m.from_user.id)); return
    await state.update_data(phone=m.text); await proceed_after_phone(m, state)

async def proceed_after_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("method") == "Yetkazib berish":
        await ask_location(m, state)
    else:
        await ask_pickup_area(m, state)

async def ask_location(m, state):
    await state.set_state(Order.location)
    await m.answer(
        "📍 <b>Yetkazish manzili</b>\n\n"
        "Pastdagi «📍 Joylashuvni yuborish» tugmasini bosing.\n"
        "<i>Telefon xaritadan aniq joyingizni yuboradi.</i>",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
                      [KeyboardButton(text="◀️ Bekor qilish")]], resize_keyboard=True))

async def ask_pickup_area(m, state):
    await state.set_state(Order.pickup_area)
    await m.answer("📍 <b>Qaysi hududimizdan olib ketasiz?</b>", reply_markup=pickup_kb())

@router.message(Order.location, F.location)
async def got_location(m: Message, state: FSMContext, bot: Bot):
    await state.update_data(lat=m.location.latitude, lon=m.location.longitude)
    data = await state.get_data()
    oid, total = await notify_admins_and_save(bot, m.from_user, data)
    await finish_order_reply(m.answer, m.from_user.id, oid, total, data.get("pay"), state)

@router.message(Order.location, F.text)
async def location_text(m: Message, state: FSMContext):
    if m.text=="◀️ Bekor qilish":
        await state.set_state(None); await m.answer("Bekor qilindi.", reply_markup=main_menu(m.from_user.id)); return
    await m.answer("⚠️ Iltimos, «📍 Joylashuvni yuborish» tugmasini bosing (matn emas).")

@router.callback_query(Order.pickup_area, F.data.startswith("area:"))
async def got_area(c: CallbackQuery, state: FSMContext, bot: Bot):
    if c.data == "area:cancel":
        await state.set_state(None)
        await c.message.edit_text("Bekor qilindi.")
        await c.message.answer("Bosh menyu 👇", reply_markup=main_menu(c.from_user.id))
        await c.answer(); return
    idx = int(c.data.split(":")[1])
    area = CHIRCHIQ_AREAS[idx]
    await state.update_data(area=area)
    data = await state.get_data()
    oid, total = await notify_admins_and_save(bot, c.from_user, data)
    await c.message.edit_text(f"✅ Hudud tanlandi: <b>{area}</b>")
    await finish_order_reply(c.message.answer, c.from_user.id, oid, total, data.get("pay"), state)
    await c.answer()


async def notify_admins_and_save(bot: Bot, user, data: dict):
    cart = data.get("cart", [])
    total = cart_total(cart)
    uname = f"@{user.username}" if user.username else "—"
    method = data.get("method")
    area = data.get("area")
    lat = data.get("lat")
    lon = data.get("lon")

    oid = save_order({"user_id":user.id,"name":user.full_name,"username":uname,
                      "items":cart,"total":total,"phone":data.get("phone"),
                      "lat":lat,"lon":lon,"pay":data.get("pay"),
                      "method":method,"area":area})

    extra = f"\n📍 Hudud: {area}" if area else ""
    head = (f"🛒 <b>YANGI ZAKAZ #{oid}</b>\n\n{items_text(cart)}\n\n"
            f"💰 Jami: <b>{money(total)}</b>\n💳 To'lov: {data.get('pay')}\n"
            f"🚚 Usul: {method}\n"
            f"📱 {data.get('phone')}{extra}\n\n"
            f"👤 {user.full_name} ({uname}) · 🆔 <code>{user.id}</code>")
    for aid in all_admin_ids():
        try:
            await bot.send_message(aid, head, reply_markup=accept_kb(oid))
            if lat is not None:
                await bot.send_location(aid, lat, lon)
        except Exception: pass
    return oid, total

async def finish_order_reply(answer_func, uid, oid, total, pay, state: FSMContext):
    await state.set_data({})
    if pay == "Online (karta)":
        cards=list_cards()
        ctext="\n\n".join(f"💳 <code>{n}</code>\n👤 {h}" for _,n,h in cards) if cards else "💳 <code>xxxx xxxx xxxx xxxx</code>"
        await answer_func(
            f"✅ <b>Buyurtma #{oid} qabul qilindi!</b>\n\n"
            f"💳 <b>Online to'lov uchun karta:</b>\n\n{ctext}\n\n"
            f"💰 Summa: <b>{money(total)}</b>\n\n"
            f"To'lovni qilib, chekni operatorga yuboring: {PHONE}")
    else:
        await answer_func(
            f"✅ <b>Buyurtma #{oid} qabul qilindi!</b>\n\n"
            f"💰 Summa: <b>{money(total)}</b>\n💳 {pay}\n\n"
            f"Tez orada operator bog'lanadi: {PHONE}")
    await answer_func("Bosh menyu 👇", reply_markup=main_menu(uid))


# ── admin: zakazni qabul qilish ───────────────────────
@router.callback_query(F.data.startswith("acc:"))
async def accept(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        await c.answer("Ruxsat yo'q", show_alert=True); return
    oid = int(c.data.split(":")[1])
    row = get_order(oid)
    if not row:
        await c.answer("Zakaz topilmadi", show_alert=True); return
    if row[11] == "accepted":
        await c.answer("Bu zakaz allaqachon qabul qilingan.", show_alert=True)
        try: await c.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        return
    accept_order(oid, c.from_user.id)
    try:
        await c.message.edit_text(c.message.html_text + f"\n\n✅ <b>QABUL QILINDI</b> ({c.from_user.full_name})")
    except Exception:
        pass
    # mijozga xabar
    try:
        await bot.send_message(row[2], f"✅ Buyurtmangiz #{oid} qabul qilindi!\n"
                                       "Tayyorlanmoqda va tez orada yetkaziladi. Rahmat! 🌭")
    except Exception: pass
    await c.answer("Qabul qilindi ✅")


# ══════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════
def admin_kb(uid):
    rows=[[InlineKeyboardButton(text="📋 Zakazlar",callback_data="a:orders")],
          [InlineKeyboardButton(text="💳 Kartalar",callback_data="a:cards")]]
    if is_owner(uid): rows.append([InlineKeyboardButton(text="👤 Adminlar",callback_data="a:admins")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(F.text=="🛠 Admin panel")
async def admin_panel(m: Message):
    if not is_admin(m.from_user.id): return
    await m.answer("🛠 <b>Admin panel</b>", reply_markup=admin_kb(m.from_user.id))

@router.callback_query(F.data=="a:orders")
async def a_orders(c: CallbackQuery):
    if not is_admin(c.from_user.id): await c.answer("Ruxsat yo'q",show_alert=True); return
    rows=recent_orders()
    if not rows:
        await c.message.edit_text("📋 Hali zakaz yo'q.", reply_markup=admin_kb(c.from_user.id)); await c.answer(); return
    out=["📋 <b>So'nggi zakazlar:</b>\n"]
    for oid,ts,name,uname,total,phone,pay,status in rows:
        t=time.strftime("%d.%m %H:%M",time.localtime(ts))
        badge="🆕" if status=="new" else "✅"
        out.append(f"{badge} <b>#{oid}</b> · {t} · {money(total)} · {pay}\n👤 {name} ({uname}) · 📱 {phone}\n")
    out.append("<i>Batafsil: /zakaz raqam</i>")
    await c.message.edit_text("\n".join(out), reply_markup=admin_kb(c.from_user.id)); await c.answer()

@router.message(Command("zakaz"))
async def zakaz_detail(m: Message, bot: Bot):
    if not is_admin(m.from_user.id): return
    p=m.text.split()
    if len(p)<2 or not p[1].isdigit(): await m.answer("Format: /zakaz 5"); return
    row=get_order(int(p[1]))
    if not row: await m.answer("Bunday zakaz yo'q."); return
    oid,ts,uid,name,uname,items,total,phone,lat,lon,pay,status,acc,method,area=row
    extra_line = f"\n🚚 Usul: {method}" if method else ""
    if area: extra_line += f"\n📍 Hudud: {area}"
    lines=[f"📋 <b>ZAKAZ #{oid}</b> {'🆕' if status=='new' else '✅'}\n",
           items_text(json.loads(items)),
           f"\n💰 Jami: <b>{money(total)}</b>\n💳 {pay}{extra_line}\n📱 {phone}",
           f"👤 {name} ({uname}) · 🆔 <code>{uid}</code>",
           f"🕙 {time.strftime('%d.%m.%Y %H:%M',time.localtime(ts))}"]
    await m.answer("\n".join(lines))
    if lat is not None:
        await bot.send_location(m.chat.id, lat, lon)

# ── Kartalar ──────────────────────────────────────────
def cards_kb(uid):
    rows=[[InlineKeyboardButton(text="➕ Karta qo'shish",callback_data="card:add")]]
    for cid,num,holder in list_cards():
        rows.append([InlineKeyboardButton(text=f"🗑 {num}",callback_data=f"card:del:{cid}")])
    rows.append([InlineKeyboardButton(text="◀️ Orqaga",callback_data="a:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data=="a:cards")
async def a_cards(c: CallbackQuery):
    if not is_admin(c.from_user.id): await c.answer("Ruxsat yo'q",show_alert=True); return
    cards=list_cards()
    txt="💳 <b>Online to'lov kartalari</b>\n\n"+("\n".join(f"• <code>{n}</code> — {h}" for _,n,h in cards) if cards else "Hozircha karta yo'q.")
    await c.message.edit_text(txt, reply_markup=cards_kb(c.from_user.id)); await c.answer()

@router.callback_query(F.data=="card:add")
async def card_add(c, state: FSMContext):
    if not is_admin(c.from_user.id): await c.answer("Ruxsat yo'q",show_alert=True); return
    await state.set_state(AdminSt.card_number)
    await c.message.answer("💳 Karta raqamini yuboring (16 xona):"); await c.answer()

@router.message(AdminSt.card_number, F.text)
async def card_num(m: Message, state: FSMContext):
    num=m.text.replace(" ","")
    if not (num.isdigit() and len(num)==16): await m.answer("⚠️ 16 xonali raqam kiriting:"); return
    await state.update_data(card_number=" ".join(num[i:i+4] for i in range(0,16,4)))
    await state.set_state(AdminSt.card_holder); await m.answer("👤 Karta egasi ismini yuboring:")

@router.message(AdminSt.card_holder, F.text)
async def card_hold(m: Message, state: FSMContext):
    d=await state.get_data(); add_card(d["card_number"], m.text.strip().upper())
    await state.set_state(None); await m.answer("✅ Karta qo'shildi.", reply_markup=main_menu(m.from_user.id))

@router.callback_query(F.data.startswith("card:del:"))
async def card_del(c: CallbackQuery):
    if not is_admin(c.from_user.id): await c.answer("Ruxsat yo'q",show_alert=True); return
    del_card(int(c.data.split(":")[2])); cards=list_cards()
    txt="💳 <b>Online to'lov kartalari</b>\n\n"+("\n".join(f"• <code>{n}</code> — {h}" for _,n,h in cards) if cards else "Hozircha karta yo'q.")
    await c.message.edit_text(txt, reply_markup=cards_kb(c.from_user.id)); await c.answer("O'chirildi")

# ── Adminlar ──────────────────────────────────────────
def admins_kb():
    rows=[[InlineKeyboardButton(text="➕ Admin qo'shish",callback_data="adm:add")]]
    for uid,name in list_admins():
        rows.append([InlineKeyboardButton(text=f"🗑 {name or uid}",callback_data=f"adm:del:{uid}")])
    rows.append([InlineKeyboardButton(text="◀️ Orqaga",callback_data="a:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data=="a:admins")
async def a_admins(c: CallbackQuery):
    if not is_owner(c.from_user.id): await c.answer("Faqat bosh admin",show_alert=True); return
    admins=list_admins()
    txt="👤 <b>Adminlar</b>\n\n"+("\n".join(f"• {name or uid} (<code>{uid}</code>)" for uid,name in admins) if admins else "Boshqa admin yo'q.")
    await c.message.edit_text(txt, reply_markup=admins_kb()); await c.answer()

@router.callback_query(F.data=="adm:add")
async def adm_add(c, state: FSMContext):
    if not is_owner(c.from_user.id): await c.answer("Faqat bosh admin",show_alert=True); return
    await state.set_state(AdminSt.new_admin)
    await c.message.answer("👤 Yangi admin Telegram <b>ID</b> raqamini yuboring.\n(U @userinfobot ga yozib ID olsin)"); await c.answer()

@router.message(AdminSt.new_admin, F.text)
async def adm_save(m: Message, state: FSMContext):
    await state.set_state(None)
    if not m.text.strip().isdigit(): await m.answer("⚠️ Faqat raqam.", reply_markup=main_menu(m.from_user.id)); return
    uid=int(m.text.strip()); add_admin(uid, f"admin{uid}")
    await m.answer(f"✅ Admin qo'shildi: <code>{uid}</code>", reply_markup=main_menu(m.from_user.id))

@router.callback_query(F.data.startswith("adm:del:"))
async def adm_del(c: CallbackQuery):
    if not is_owner(c.from_user.id): await c.answer("Faqat bosh admin",show_alert=True); return
    del_admin(int(c.data.split(":")[2])); admins=list_admins()
    txt="👤 <b>Adminlar</b>\n\n"+("\n".join(f"• {name or uid} (<code>{uid}</code>)" for uid,name in admins) if admins else "Boshqa admin yo'q.")
    await c.message.edit_text(txt, reply_markup=admins_kb()); await c.answer("O'chirildi")

@router.callback_query(F.data=="a:back")
async def a_back(c: CallbackQuery):
    await c.message.edit_text("🛠 <b>Admin panel</b>", reply_markup=admin_kb(c.from_user.id)); await c.answer()


# ── boshqa matn ───────────────────────────────────────
@router.message(F.text)
async def fallback(m: Message):
    await m.answer("Pastdagi menyudan tanlang 👇", reply_markup=main_menu(m.from_user.id))


# ── ESLATMA tsikli ────────────────────────────────────
async def reminder_loop():
    await asyncio.sleep(10)
    while True:
        try:
            bot = bot_ref["bot"]
            now = int(time.time())
            for oid, last in pending_orders():
                if now - (last or 0) >= REMIND_SEC:
                    row = get_order(oid)
                    if not row or row[11] != "new":
                        continue
                    total = row[6]
                    for aid in all_admin_ids():
                        try:
                            await bot.send_message(
                                aid,
                                f"⏰ <b>ESLATMA!</b>\n\nZakaz #{oid} ({money(total)}) hali "
                                "qabul qilinmadi. Iltimos, ko'rib chiqing 👇",
                                reply_markup=accept_kb(oid))
                        except Exception: pass
                    touch_remind(oid)
        except Exception as e:
            log.warning("reminder: %s", e)
        await asyncio.sleep(30)


# ── ishga tushirish ───────────────────────────────────
async def set_commands(bot: Bot):
    from aiogram.types import BotCommand
    await bot.set_my_commands([BotCommand(command="start", description="Boshlash")])

async def main():
    if not TOKEN: raise SystemExit("BOT_TOKEN o'rnatilmagan.")
    if OWNER_ID == 0: log.warning("ADMIN_ID sozlanmagan.")
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    bot_ref["bot"] = bot
    dp = Dispatcher(); dp.include_router(router)
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(reminder_loop())
    log.info("Baza: %s", DB_PATH); log.info("Bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): log.info("To'xtatildi")
