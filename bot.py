import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession # تم إضافة هذا السطر

# الإعدادات
API_TOKEN = '8771398928:AAGvnrVFiTk5q5eymrvVhuVpA8sX2cDI-zY'
OWNER_ID = 6916258079
logging.basicConfig(level=logging.INFO)

# إعداد الجلسة عبر البروكسي لتجاوز حظر PythonAnywhere
session = AiohttpSession(proxy="http://user:password@proxy_host:proxy_port") # ضع هنا بيانات البروكسي الخاص بك
bot = Bot(token=API_TOKEN, session=session) # تم دمج الجلسة هنا
dp = Dispatcher(storage=MemoryStorage())

# --- الحالات ---
class UserStates(StatesGroup):
    choosing_service = State()
    entering_amount = State()
    sending_receipt = State()

class AdminStates(StatesGroup):
    add_country = State()
    add_service = State()
    add_rate = State()
    add_agent = State()

# --- تهيئة القاعدة (محدثة) ---
def init_db():
    with sqlite3.connect('monzoma_pro.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY, country TEXT, service_name TEXT, rate REAL, agent_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, amount REAL, photo_id TEXT, status TEXT DEFAULT 'PENDING')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS ratings (order_id INTEGER, rating INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS blocked_users (user_id INTEGER PRIMARY KEY)''')
        conn.commit()
init_db()

# --- نظام التذكير ---
async def auto_reminder(order_id, agent_id):
    await asyncio.sleep(900)
    with sqlite3.connect('monzoma_pro.db') as conn:
        status = conn.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if status and status[0] == 'PENDING':
            await bot.send_message(agent_id, f"⚠️ تنبيه: الطلب رقم #{order_id} لا يزال معلقاً، يرجى سرعة الرد!")

# --- القائمة الرئيسية ---
async def show_main_menu(message_or_callback):
    user_id = message_or_callback.from_user.id
    with sqlite3.connect('monzoma_pro.db') as conn:
        if conn.execute("SELECT 1 FROM blocked_users WHERE user_id = ?", (user_id,)).fetchone():
            return await (message_or_callback.answer("❌ أنت محظور.") if isinstance(message_or_callback, types.Message) else callback_answer_wrapper(message_or_callback, "❌ أنت محظور."))
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💰 تحويل جديد", callback_data="new_order"),
                types.InlineKeyboardButton(text="📊 طلباتي", callback_data="my_orders"))
    builder.row(types.InlineKeyboardButton(text="🎧 دعم فني", callback_data="support"))
    
    if user_id == OWNER_ID:
        builder.row(types.InlineKeyboardButton(text="👑 لوحة التحكم", callback_data="adm_panel"),
                    types.InlineKeyboardButton(text="📈 الإحصائيات", callback_data="adm_stats"))
    
    text = "أهلاً بك في منصة التحويلات الذكية 🚀\nاختر الخدمة المطلوبة:"
    if isinstance(message_or_callback, types.Message): await message_or_callback.answer(text, reply_markup=builder.as_markup())
    else: await message_or_callback.message.edit_text(text, reply_markup=builder.as_markup())

async def callback_answer_wrapper(callback, text): await callback.answer(text)

@dp.message(Command("start"))
async def start(message: types.Message): await show_main_menu(message)

# --- لوحة التحكم والإحصائيات ---
@dp.callback_query(F.data == "adm_stats")
async def show_stats(callback: types.CallbackQuery):
    with sqlite3.connect('monzoma_pro.db') as conn:
        total = conn.execute("SELECT SUM(amount) FROM orders WHERE status='APPROVED'").fetchone()[0] or 0
        pending = conn.execute("SELECT COUNT(*) FROM orders WHERE status='PENDING'").fetchone()[0]
    await callback.message.edit_text(f"📈 الإحصائيات:\nإجمالي المبالغ: {total}\nالطلبات المعلقة: {pending}", reply_markup=InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_main")).as_markup())

@dp.callback_query(F.data == "adm_panel")
async def admin_panel(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة خدمة", callback_data="adm_add_s1"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_main"))
    await callback.message.edit_text("👑 لوحة تحكم المالك:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "adm_add_s1")
async def start_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل اسم الدولة:")
    await state.set_state(AdminStates.add_country)

@dp.message(AdminStates.add_country)
async def get_c(m: types.Message, state: FSMContext):
    await state.update_data(country=m.text); await m.answer("أرسل اسم الخدمة:"); await state.set_state(AdminStates.add_service)

@dp.message(AdminStates.add_service)
async def get_s(m: types.Message, state: FSMContext):
    await state.update_data(service=m.text); await m.answer("أرسل سعر الصرف:"); await state.set_state(AdminStates.add_rate)

@dp.message(AdminStates.add_rate)
async def get_r(m: types.Message, state: FSMContext):
    await state.update_data(rate=m.text); await m.answer("أرسل ID الوكيل:"); await state.set_state(AdminStates.add_agent)

@dp.message(AdminStates.add_agent)
async def finish_add(m: types.Message, state: FSMContext):
    data = await state.get_data()
    with sqlite3.connect('monzoma_pro.db') as conn:
        conn.execute("INSERT INTO services (country, service_name, rate, agent_id) VALUES (?, ?, ?, ?)", (data['country'], data['service'], float(data['rate']), int(m.text)))
    await m.answer("✅ تم الإضافة!"); await state.clear(); await show_main_menu(m)

# --- عمليات الطلب ---
@dp.callback_query(F.data == "new_order")
async def new_order(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    with sqlite3.connect('monzoma_pro.db') as conn:
        countries = conn.execute("SELECT DISTINCT country FROM services").fetchall()
    for c in countries: builder.row(types.InlineKeyboardButton(text=f"📍 {c[0]}", callback_data=f"sel_c_{c[0]}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_main"))
    await callback.message.edit_text("اختر الدولة:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("sel_c_"))
async def select_country(callback: types.CallbackQuery, state: FSMContext):
    country = callback.data.split("_")[2]
    builder = InlineKeyboardBuilder()
    with sqlite3.connect('monzoma_pro.db') as conn:
        services = conn.execute("SELECT service_name, rate FROM services WHERE country = ?", (country,)).fetchall()
    for s in services: builder.row(types.InlineKeyboardButton(text=f"{s[0]} ({s[1]})", callback_data=f"buy_{s[0]}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="new_order"))
    await callback.message.edit_text(f"خدمات {country}:", reply_markup=builder.as_markup()); await state.set_state(UserStates.choosing_service)

@dp.callback_query(F.data.startswith("buy_"))
async def service_selected(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(service=callback.data.split("_")[1]); await callback.message.answer("أرسل المبلغ:"); await state.set_state(UserStates.entering_amount)

@dp.message(UserStates.entering_amount)
async def process_amount(message: types.Message, state: FSMContext):
    await state.update_data(amount=message.text); await message.answer("أرسل صورة الإيصال:"); await state.set_state(UserStates.sending_receipt)

# --- التوزيع (محدث) ---
@dp.message(UserStates.sending_receipt, F.photo)
async def process_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    with sqlite3.connect('monzoma_pro.db') as conn:
        agent = conn.execute("SELECT agent_id FROM services WHERE service_name = ?", (data['service'],)).fetchone()
        agent_id = agent[0] if agent else OWNER_ID
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, service, amount, photo_id) VALUES (?, ?, ?, ?)", (message.from_user.id, data['service'], data['amount'], message.photo[-1].file_id))
        order_id = cursor.lastrowid
    
    asyncio.create_task(auto_reminder(order_id, agent_id))
    await message.answer("✅ تم توجيه طلبك.")
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ تأكيد", callback_data=f"app_{order_id}"))
    builder.row(types.InlineKeyboardButton(text="🚫 حظر العميل", callback_data=f"ban_{message.from_user.id}"))
    await bot.send_photo(agent_id, photo=message.photo[-1].file_id, caption=f"📦 طلب #{order_id}", reply_markup=builder.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("ban_"))
async def ban_user(callback: types.CallbackQuery):
    with sqlite3.connect('monzoma_pro.db') as conn: conn.execute("INSERT OR IGNORE INTO blocked_users VALUES (?)", (callback.data.split("_")[1],))
    await callback.answer("تم الحظر")

@dp.callback_query(F.data.startswith("app_"))
async def admin_approve(callback: types.CallbackQuery):
    oid = callback.data.split("_")[1]
    with sqlite3.connect('monzoma_pro.db') as conn:
        uid = conn.execute("SELECT user_id FROM orders WHERE order_id = ?", (oid,)).fetchone()[0]
        conn.execute("UPDATE orders SET status = 'APPROVED' WHERE order_id = ?", (oid,))
    builder = InlineKeyboardBuilder()
    for i in range(1, 6): builder.add(types.InlineKeyboardButton(text=str(i), callback_data=f"rate_{oid}_{i}"))
    await bot.send_message(uid, "⭐ كيف تقيم الخدمة؟", reply_markup=builder.as_markup())
    await callback.answer("تم التأكيد")

@dp.callback_query(F.data.startswith("rate_"))
async def save_rating(callback: types.CallbackQuery):
    _, oid, val = callback.data.split("_")
    with sqlite3.connect('monzoma_pro.db') as conn: conn.execute("INSERT INTO ratings VALUES (?, ?)", (oid, val))
    await callback.message.edit_text("شكراً!")

@dp.callback_query(F.data == "my_orders")
async def my_orders(callback: types.CallbackQuery):
    with sqlite3.connect('monzoma_pro.db') as conn: orders = conn.execute("SELECT order_id, status FROM orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 5", (callback.from_user.id,)).fetchall()
    text = "📜 طلباتك:\n" + "\n".join([f"#{o[0]} - {o[1]}" for o in orders])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="🔙", callback_data="back_main")).as_markup())

@dp.callback_query(F.data == "back_main")
async def back(callback: types.CallbackQuery): await show_main_menu(callback)

async def main(): await dp.start_polling(bot)
if __name__ == '__main__': asyncio.run(main())
