from flask import Flask
import threading
import asyncio, logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, delete
from config import BOT_TOKEN, ADMIN_IDS, TIMEZONE
from database import init_db, async_session, User, Reminder, Task, Expense, Medicine

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

class ReminderForm(StatesGroup):
    text = State()
    time = State()

class TaskForm(StatesGroup):
    title = State()
    deadline = State()

class ExpenseForm(StatesGroup):
    amount = State()
    category = State()
    comment = State()

class MedicineForm(StatesGroup):
    name = State()
    dose = State()
    time = State()

# --- Клавиатуры ---
def main_menu(user_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Напоминания", callback_data="menu_reminders")],
        [InlineKeyboardButton(text="✅ Задачи", callback_data="menu_tasks")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="menu_finance")],
        [InlineKeyboardButton(text="💊 Здоровье", callback_data="menu_health")],
        [InlineKeyboardButton(text="🔓 Премиум", callback_data="menu_premium")],
    ])
    return kb

# --- Команда /start ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    async with async_session() as session:
        user = await session.execute(select(User).where(User.user_id == message.from_user.id))
        if not user.scalar():
            session.add(User(user_id=message.from_user.id, full_name=message.from_user.full_name))
            await session.commit()
    await message.answer(f"Привет, {message.from_user.full_name}! Я TechLife Assistant. Выбери действие:", reply_markup=main_menu(message.from_user.id))

# --- Напоминания (FSM + клавиатура)[reference:3]---
@dp.callback_query(F.data == "menu_reminders")
async def reminders_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="reminder_add")],
        [InlineKeyboardButton(text="📋 Мои напоминания", callback_data="reminder_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("⏰ Управление напоминаниями:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "reminder_add")
async def reminder_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderForm.text)
    await callback.message.edit_text("📝 Введите текст напоминания:")
    await callback.answer()

@dp.message(ReminderForm.text)
async def reminder_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(ReminderForm.time)
    await message.answer("⏰ Введите время в формате ЧЧ:ММ (например, 15:30)")

@dp.message(ReminderForm.time)
async def reminder_time(message: Message, state: FSMContext):
    try:
        hour, minute = map(int, message.text.split(":"))
        now = datetime.now()
        remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_at <= now:
            remind_at += timedelta(days=1)
        data = await state.get_data()
        async with async_session() as session:
            reminder = Reminder(user_id=message.from_user.id, text=data["text"], remind_at=remind_at)
            session.add(reminder)
            await session.commit()
            scheduler.add_job(send_reminder, "date", run_date=remind_at, args=[message.from_user.id, data["text"]], id=f"remind_{reminder.id}")
        await message.answer(f"✅ Напоминание установлено на {remind_at.strftime('%d.%m.%Y %H:%M')}")
        await state.clear()
    except:
        await message.answer("❌ Неверный формат. Используйте ЧЧ:ММ")

async def send_reminder(user_id: int, text: str):
    await bot.send_message(user_id, f"🔔 Напоминание: {text}")

@dp.callback_query(F.data == "reminder_list")
async def reminder_list(callback: CallbackQuery):
    async with async_session() as session:
        reminders = await session.execute(select(Reminder).where(Reminder.user_id == callback.from_user.id, Reminder.is_active == True))
        reminders = reminders.scalars().all()
        if not reminders:
            await callback.message.edit_text("📭 Нет активных напоминаний", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_reminders")]]))
        else:
            text = "📋 Ваши напоминания:\n" + "\n".join([f"• {r.text} — {r.remind_at.strftime('%d.%m.%Y %H:%M')}" for r in reminders])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_reminders")]]))
    await callback.answer()

# --- Задачи[reference:4]---
@dp.callback_query(F.data == "menu_tasks")
async def tasks_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="task_add")],
        [InlineKeyboardButton(text="📋 Мои задачи", callback_data="task_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="task_stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("✅ Управление задачами:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "task_add")
async def task_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskForm.title)
    await callback.message.edit_text("✍️ Введите название задачи:")
    await callback.answer()

@dp.message(TaskForm.title)
async def task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(TaskForm.deadline)
    await message.answer("⏰ Введите дедлайн в формате ДД.ММ.ГГГГ ЧЧ:ММ или пропустите (0):")

@dp.message(TaskForm.deadline)
async def task_deadline(message: Message, state: FSMContext):
    data = await state.get_data()
    deadline = None
    if message.text != "0":
        try:
            deadline = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        except:
            await message.answer("❌ Неверный формат. Попробуйте снова или введите 0")
            return
    async with async_session() as session:
        task = Task(user_id=message.from_user.id, title=data["title"], deadline=deadline)
        session.add(task)
        await session.commit()
    await message.answer(f"✅ Задача '{data['title']}' добавлена!")
    await state.clear()

@dp.callback_query(F.data == "task_list")
async def task_list(callback: CallbackQuery):
    async with async_session() as session:
        tasks = await session.execute(select(Task).where(Task.user_id == callback.from_user.id, Task.is_done == False))
        tasks = tasks.scalars().all()
        if not tasks:
            await callback.message.edit_text("📭 Нет активных задач", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_tasks")]]))
        else:
            text = "📋 Активные задачи:\n" + "\n".join([f"• {t.title}" + (f" (до {t.deadline.strftime('%d.%m.%Y')})" if t.deadline else "") for t in tasks])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_tasks")]]))
    await callback.answer()

# --- Финансы ---
@dp.callback_query(F.data == "menu_finance")
async def finance_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        month_ago = datetime.now() - timedelta(days=30)
        expenses = await session.execute(select(Expense).where(Expense.user_id == callback.from_user.id, Expense.date >= month_ago))
        total = sum(e.amount for e in expenses.scalars().all())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить расход", callback_data="expense_add")],
        [InlineKeyboardButton(text="📊 Статистика за месяц", callback_data="expense_stats")],
        [InlineKeyboardButton(text=f"💰 За месяц: {total:.2f} руб", callback_data="expense_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("💰 Финансы:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "expense_add")
async def expense_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExpenseForm.amount)
    await callback.message.edit_text("💰 Введите сумму расхода:")
    await callback.answer()

@dp.message(ExpenseForm.amount)
async def expense_amount(message: Message, state: FSMContext):
    try:
        await state.update_data(amount=float(message.text))
        await state.set_state(ExpenseForm.category)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🍔 Еда", callback_data="cat_food"), InlineKeyboardButton(text="🚕 Транспорт", callback_data="cat_transport")],
            [InlineKeyboardButton(text="💡 ЖКХ", callback_data="cat_utilities"), InlineKeyboardButton(text="🎬 Развлечения", callback_data="cat_entertainment")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_finance")]
        ])
        await message.answer("📂 Выберите категорию:", reply_markup=kb)
    except:
        await message.answer("❌ Введите число")

@dp.callback_query(F.data.startswith("cat_"))
async def expense_category(callback: CallbackQuery, state: FSMContext):
    category_map = {"cat_food":"Еда","cat_transport":"Транспорт","cat_utilities":"ЖКХ","cat_entertainment":"Развлечения"}
    await state.update_data(category=category_map[callback.data])
    await state.set_state(ExpenseForm.comment)
    await callback.message.edit_text("📝 Добавьте комментарий (или введите 0 для пропуска):")
    await callback.answer()

@dp.message(ExpenseForm.comment)
async def expense_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    comment = message.text if message.text != "0" else None
    async with async_session() as session:
        expense = Expense(user_id=message.from_user.id, amount=data["amount"], category=data["category"], comment=comment)
        session.add(expense)
        await session.commit()
    await message.answer(f"✅ Расход {data['amount']} руб ({data['category']}) добавлен")
    await state.clear()

# --- Здоровье (напоминалка лекарств)[reference:5]---
@dp.callback_query(F.data == "menu_health")
async def health_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💊 Добавить лекарство", callback_data="medicine_add")],
        [InlineKeyboardButton(text="📋 Мои лекарства", callback_data="medicine_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("💊 Трекер здоровья:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "medicine_add")
async def medicine_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MedicineForm.name)
    await callback.message.edit_text("💊 Введите название лекарства:")
    await callback.answer()

@dp.message(MedicineForm.name)
async def medicine_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(MedicineForm.dose)
    await message.answer("💊 Введите дозировку:")

@dp.message(MedicineForm.dose)
async def medicine_dose(message: Message, state: FSMContext):
    await state.update_data(dose=message.text)
    await state.set_state(MedicineForm.time)
    await message.answer("⏰ Введите время приема (ЧЧ:ММ):")

@dp.message(MedicineForm.time)
async def medicine_time(message: Message, state: FSMContext):
    try:
        hour, minute = map(int, message.text.split(":"))
        time_str = f"{hour:02d}:{minute:02d}"
        data = await state.get_data()
        async with async_session() as session:
            med = Medicine(user_id=message.from_user.id, name=data["name"], dose=data["dose"], time=time_str)
            session.add(med)
            await session.commit()
        # Ежедневное напоминание
        scheduler.add_job(send_medicine_reminder, "cron", hour=hour, minute=minute, args=[message.from_user.id, data["name"], data["dose"]], id=f"med_{message.from_user.id}_{data['name']}")
        await message.answer(f"✅ Лекарство '{data['name']}' добавлено, напоминание в {time_str}")
        await state.clear()
    except:
        await message.answer("❌ Неверный формат времени. Используйте ЧЧ:ММ")

async def send_medicine_reminder(user_id: int, name: str, dose: str):
    await bot.send_message(user_id, f"💊 Время приема! {name} — {dose}")

# --- Премиум (Telegram Stars)[reference:6][reference:7]---
@dp.callback_query(F.data == "menu_premium")
async def premium_menu(callback: CallbackQuery):
    async with async_session() as session:
        user = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = user.scalar()
        status = "✅ Активен" if user and user.is_premium and user.premium_until > datetime.now() else "❌ Неактивен"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить Premium (1 месяц / 50 Stars)", callback_data="buy_premium_50")],
        [InlineKeyboardButton(text="⭐ Купить Premium (3 месяца / 120 Stars)", callback_data="buy_premium_120")],
        [InlineKeyboardButton(text=f"📊 Статус: {status}", callback_data="premium_status")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text("🔓 Premium-доступ:\n"
                                    "▸ Напоминания с повторами\n"
                                    "▸ Расширенная аналитика расходов\n"
                                    "▸ Неограниченное количество задач\n\n"
                                    "Цена: 50 Stars/мес или 120 Stars/3 мес", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_premium_"))
async def buy_premium(callback: CallbackQuery):
    stars = 50 if "50" in callback.data else 120
    months = 1 if "50" in callback.data else 3
    await bot.send_invoice(callback.message.chat.id,
        title="Premium доступ",
        description=f"Активация Premium на {months} месяц(ев)",
        payload=f"premium_{months}_{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[{"label":"Premium","amount":stars}])
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    months = int(payload.split("_")[1])
    user_id = int(payload.split("_")[2])
    async with async_session() as session:
        user = await session.execute(select(User).where(User.user_id == user_id))
        user = user.scalar()
        if user:
            user.is_premium = True
            if user.premium_until and user.premium_until > datetime.now():
                user.premium_until += timedelta(days=30*months)
            else:
                user.premium_until = datetime.now() + timedelta(days=30*months)
            await session.commit()
    await message.answer(f"✅ Premium активирован на {months} месяц(ев)! Спасибо за покупку!")

# --- Админ панель (рассылка)[reference:8]---
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats")]
    ])
    await message.answer("🛠️ Админ панель:", reply_markup=kb)

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступ запрещен")
        return
    await state.set_state("waiting_broadcast")
    await callback.message.edit_text("📢 Введите текст для рассылки (бот отправит его ВСЕМ пользователям):")
    await callback.answer()

@dp.message(State("waiting_broadcast"))
async def send_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Доступ запрещен")
        return
    async with async_session() as session:
        users = await session.execute(select(User))
        users = users.scalars().all()
        sent = 0
        for user in users:
            try:
                await bot.send_message(user.user_id, f"📢 Админ: {message.text}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await message.answer(f"✅ Рассылка завершена. Отправлено {sent} пользователям.")
    await state.clear()

# --- Назад и прочее ---
@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

app = Flask(__name__)

@app.route('/')
def health():
    return 'OK', 200

def run_web():
    app.run(host='0.0.0.0', port=10000)

async def main():
    await init_db()
    scheduler.start()
    threading.Thread(target=run_web, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
