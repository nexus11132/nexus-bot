import asyncio
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from html import escape


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "784663724"))

DB_NAME = "nexus.db"


# =========================================================
# BOT
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            service TEXT NOT NULL,
            description TEXT NOT NULL,
            budget TEXT,
            contact TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )
    """)

    conn.commit()
    conn.close()


def create_order(
    user_id: int,
    username: str,
    service: str,
    description: str,
    budget: str,
    contact: str
):
    conn = get_db()

    created_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    cursor = conn.execute("""
        INSERT INTO orders
        (
            user_id,
            username,
            service,
            description,
            budget,
            contact,
            created_at,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        service,
        description,
        budget,
        contact,
        created_at,
        "new"
    ))

    order_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return order_id


def get_order(order_id: int):
    conn = get_db()

    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    conn.close()

    return order


def get_orders(
    status=None,
    limit=10,
    offset=0
):
    conn = get_db()

    if status:
        orders = conn.execute("""
            SELECT *
            FROM orders
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (
            status,
            limit,
            offset
        )).fetchall()
    else:
        orders = conn.execute("""
            SELECT *
            FROM orders
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (
            limit,
            offset
        )).fetchall()

    conn.close()

    return orders


def count_orders(status=None):
    conn = get_db()

    if status:
        result = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE status = ?",
            (status,)
        ).fetchone()
    else:
        result = conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()

    conn.close()

    return result[0]


def update_order_status(order_id: int, status: str):
    conn = get_db()

    conn.execute("""
        UPDATE orders
        SET status = ?
        WHERE id = ?
    """, (
        status,
        order_id
    ))

    conn.commit()
    conn.close()


def search_orders(order_id: int):
    return get_order(order_id)


# =========================================================
# HELPERS
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def format_order_number(order_id: int) -> str:
    return f"NEX-{order_id:04d}"


def status_text(status: str) -> str:

    statuses = {
        "new": "🆕 Новая",
        "working": "🟡 В работе",
        "completed": "🔵 Завершена",
        "rejected": "🔴 Отклонена"
    }

    return statuses.get(status, status)


def service_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Telegram-бот",
                    callback_data="service:telegram"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Сайт",
                    callback_data="service:website"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💻 Программирование",
                    callback_data="service:programming"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Дизайн",
                    callback_data="service:design"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Другое",
                    callback_data="service:other"
                )
            ]
        ]
    )


def admin_keyboard():
    new_count = count_orders("new")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📥 Новые заявки ({new_count})",
                    callback_data="admin:new"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Все заказы",
                    callback_data="admin:all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin:stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Найти заказ",
                    callback_data="admin:search"
                )
            ]
        ]
    )


def order_keyboard(order_id: int, status: str):

    buttons = []

    if status == "new":
        buttons.append([
            InlineKeyboardButton(
                text="🟡 Взять в работу",
                callback_data=f"order:working:{order_id}"
            )
        ])

    if status == "working":
        buttons.append([
            InlineKeyboardButton(
                text="🔵 Завершить",
                callback_data=f"order:completed:{order_id}"
            )
        ])

    if status != "rejected":
        buttons.append([
            InlineKeyboardButton(
                text="🔴 Отклонить",
                callback_data=f"order:rejected:{order_id}"
            )
        ])

    if status != "new":
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Вернуть в новые",
                callback_data=f"order:new:{order_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="◀️ В админку",
            callback_data="admin:menu"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pagination_keyboard(
    page: int,
    total: int,
    mode: str
):
    per_page = 5
    total_pages = max(1, (total + per_page - 1) // per_page)

    buttons = []

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"page:{mode}:{page - 1}"
            )
        )

    navigation.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="nothing"
        )
    )

    if page + 1 < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"page:{mode}:{page + 1}"
            )
        )

    buttons.append(navigation)

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Админ-панель",
            callback_data="admin:menu"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_text(order) -> str:

    username = order["username"]

    if username:
        username_text = f"@{escape(username)}"
    else:
        username_text = "нет username"

    return (
        f"📦 <b>{format_order_number(order['id'])}</b>\n\n"
        f"👤 {username_text}\n"
        f"🔢 ID: <code>{order['user_id']}</code>\n\n"
        f"💼 <b>{escape(order['service'])}</b>\n"
        f"💰 {escape(order['budget'] or 'Не указан')}\n\n"
        f"📝 <b>Описание:</b>\n"
        f"{escape(order['description'])}\n\n"
        f"📞 <b>Контакт:</b> {escape(order['contact'] or 'Не указан')}\n"
        f"🕐 {escape(order['created_at'])}\n\n"
        f"📌 <b>{status_text(order['status'])}</b>"
    )


# =========================================================
# FSM
# =========================================================

class OrderForm(StatesGroup):
    service = State()
    description = State()
    budget = State()
    contact = State()


class SearchForm(StatesGroup):
    order_id = State()


# =========================================================
# USER START
# =========================================================

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):

    await state.clear()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Создать заявку",
                    callback_data="user:create"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Моя заявка",
                    callback_data="user:my_order"
                )
            ]
        ]
    )

    await message.answer(
        "👋 <b>Добро пожаловать в Nexus</b>\n\n"
        "Мы поможем реализовать ваш проект.\n\n"
        "Выберите нужное действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# =========================================================
# CREATE ORDER
# =========================================================

@dp.callback_query(F.data == "user:create")
async def create_order_start(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.set_state(OrderForm.service)

    await callback.message.answer(
        "💼 <b>Выберите тип проекта:</b>",
        reply_markup=service_keyboard(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("service:"),
    StateFilter(OrderForm.service)
)
async def choose_service(
    callback: CallbackQuery,
    state: FSMContext
):

    services = {
        "telegram": "Telegram-бот",
        "website": "Сайт",
        "programming": "Программирование",
        "design": "Дизайн",
        "other": "Другое"
    }

    service_key = callback.data.split(":")[1]

    service = services.get(
        service_key,
        "Другое"
    )

    await state.update_data(
        service=service
    )

    await state.set_state(
        OrderForm.description
    )

    await callback.message.answer(
        "📝 <b>Опишите ваш проект.</b>\n\n"
        "Что нужно сделать, какие функции нужны "
        "и какой результат вы хотите получить?",
        parse_mode="HTML"
    )

    await callback.answer()


@dp.message(StateFilter(OrderForm.description))
async def order_description(
    message: Message,
    state: FSMContext
):

    await state.update_data(
        description=message.text
    )

    await state.set_state(
        OrderForm.budget
    )

    await message.answer(
        "💰 <b>Какой у вас бюджет?</b>\n\n"
        "Например: 200₴, 500₴, 1000₴.\n"
        "Если пока не определились — напишите «не знаю».",
        parse_mode="HTML"
    )


@dp.message(StateFilter(OrderForm.budget))
async def order_budget(
    message: Message,
    state: FSMContext
):

    await state.update_data(
        budget=message.text
    )

    await state.set_state(
        OrderForm.contact
    )

    await message.answer(
        "📞 <b>Оставьте контакт для связи.</b>\n\n"
        "Например: @username или номер телефона.",
        parse_mode="HTML"
    )


@dp.message(StateFilter(OrderForm.contact))
async def order_contact(
    message: Message,
    state: FSMContext
):

    data = await state.get_data()

    username = (
        message.from_user.username
        or ""
    )

    order_id = create_order(
        user_id=message.from_user.id,
        username=username,
        service=data["service"],
        description=data["description"],
        budget=data["budget"],
        contact=message.text
    )

    await state.clear()

    await message.answer(
        "✅ <b>Заявка успешно создана!</b>\n\n"
        f"📦 Номер заявки: <b>{format_order_number(order_id)}</b>\n\n"
        "Мы получили вашу заявку и свяжемся с вами.",
        parse_mode="HTML"
    )

    # Уведомление администратора

    order = get_order(order_id)

    try:
        await bot.send_message(
            ADMIN_ID,
            "🔔 <b>НОВАЯ ЗАЯВКА</b>\n\n"
            + order_text(order),
            parse_mode="HTML",
            reply_markup=order_keyboard(
                order_id,
                "new"
            )
        )
    except Exception as e:
        print(
            f"Не удалось уведомить администратора: {e}"
        )


# =========================================================
# MY ORDER
# =========================================================

@dp.callback_query(F.data == "user:my_order")
async def my_order(callback: CallbackQuery):

    conn = get_db()

    order = conn.execute("""
        SELECT *
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (
        callback.from_user.id,
    )).fetchone()

    conn.close()

    if not order:
        await callback.message.answer(
            "📭 У вас пока нет заявок."
        )
        await callback.answer()
        return

    await callback.message.answer(
        order_text(order),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# ADMIN MENU
# =========================================================

@dp.message(Command("admin"))
async def admin_command(message: Message):

    if not is_admin(message.from_user.id):
        await message.answer(
            "⛔ У вас нет доступа."
        )
        return

    await message.answer(
        "🛡 <b>NEXUS ADMIN</b>\n\n"
        "Панель управления заказами:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin:menu")
async def admin_menu(callback: CallbackQuery):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    await callback.message.answer(
        "🛡 <b>NEXUS ADMIN</b>\n\n"
        "Панель управления заказами:",
        reply_markup=admin_keyboard(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# ADMIN NEW ORDERS
# =========================================================

@dp.callback_query(F.data == "admin:new")
async def admin_new_orders(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    await show_orders(
        callback,
        status="new",
        page=0
    )

    await callback.answer()


# =========================================================
# ADMIN ALL ORDERS
# =========================================================

@dp.callback_query(F.data == "admin:all")
async def admin_all_orders(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    await show_orders(
        callback,
        status=None,
        page=0
    )

    await callback.answer()


# =========================================================
# SHOW ORDERS
# =========================================================

async def show_orders(
    callback: CallbackQuery,
    status=None,
    page=0
):

    per_page = 5
    offset = page * per_page

    total = count_orders(status)

    if total == 0:

        if status == "new":
            text = "✅ <b>Новых заявок нет.</b>"
        else:
            text = "📭 <b>Заказов пока нет.</b>"

        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="admin:menu"
                        )
                    ]
                ]
            )
        )

        return

    orders = get_orders(
        status=status,
        limit=per_page,
        offset=offset
    )

    for order in orders:

        await callback.message.answer(
            order_text(order),
            parse_mode="HTML",
            reply_markup=order_keyboard(
                order["id"],
                order["status"]
            )
        )

    mode = "new" if status == "new" else "all"

    await callback.message.answer(
        f"📦 Показано: {offset + 1}-{min(offset + len(orders), total)} "
        f"из {total}",
        reply_markup=pagination_keyboard(
            page,
            total,
            mode
        )
    )


# =========================================================
# PAGINATION
# =========================================================

@dp.callback_query(F.data.startswith("page:"))
async def pagination(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    _, mode, page = callback.data.split(":")

    page = int(page)

    status = "new" if mode == "new" else None

    await show_orders(
        callback,
        status=status,
        page=page
    )

    await callback.answer()


# =========================================================
# ORDER STATUS
# =========================================================

@dp.callback_query(
    F.data.startswith("order:")
)
async def change_order_status(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    _, status, order_id = callback.data.split(":")

    order_id = int(order_id)

    allowed_statuses = {
        "new",
        "working",
        "completed",
        "rejected"
    }

    if status not in allowed_statuses:
        await callback.answer(
            "❌ Неверный статус",
            show_alert=True
        )
        return

    order = get_order(order_id)

    if not order:
        await callback.answer(
            "❌ Заказ не найден",
            show_alert=True
        )
        return

    update_order_status(
        order_id,
        status
    )

    new_order = get_order(order_id)

    try:
        await callback.message.edit_text(
            order_text(new_order),
            parse_mode="HTML",
            reply_markup=order_keyboard(
                order_id,
                status
            )
        )
    except Exception:
        pass

    await callback.answer(
        f"Статус изменён: {status_text(status)}"
    )

    # Сообщаем клиенту

    user_messages = {
        "working":
            "🟡 Ваша заявка взята в работу.",
        "completed":
            "🔵 Ваша заявка завершена.",
        "rejected":
            "🔴 Ваша заявка была отклонена.",
        "new":
            "🔄 Ваша заявка снова находится в статусе «Новая»."
    }

    try:
        await bot.send_message(
            order["user_id"],
            f"📦 <b>{format_order_number(order_id)}</b>\n\n"
            f"{user_messages[status]}",
            parse_mode="HTML"
        )
    except Exception as e:
        print(
            f"Не удалось отправить сообщение клиенту: {e}"
        )


# =========================================================
# STATISTICS
# =========================================================

@dp.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    total = count_orders()
    new = count_orders("new")
    working = count_orders("working")
    completed = count_orders("completed")
    rejected = count_orders("rejected")

    text = (
        "📊 <b>СТАТИСТИКА NEXUS</b>\n\n"
        f"📦 Всего заказов: <b>{total}</b>\n\n"
        f"🆕 Новых: <b>{new}</b>\n"
        f"🟡 В работе: <b>{working}</b>\n"
        f"🔵 Завершено: <b>{completed}</b>\n"
        f"🔴 Отклонено: <b>{rejected}</b>"
    )

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Админ-панель",
                        callback_data="admin:menu"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# =========================================================
# SEARCH
# =========================================================

@dp.callback_query(F.data == "admin:search")
async def admin_search_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Нет доступа",
            show_alert=True
        )
        return

    await state.set_state(
        SearchForm.order_id
    )

    await callback.message.answer(
        "🔍 <b>Поиск заказа</b>\n\n"
        "Введите номер заказа.\n\n"
        "Например:\n"
        "<code>NEX-0025</code>\n"
        "или\n"
        "<code>25</code>",
        parse_mode="HTML"
    )

    await callback.answer()


@dp.message(StateFilter(SearchForm.order_id))
async def admin_search(
    message: Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        await state.clear()
        return

    value = message.text.strip()

    value = value.upper()

    if value.startswith("NEX-"):
        value = value.replace(
            "NEX-",
            ""
        )

    try:
        order_id = int(value)
    except ValueError:

        await message.answer(
            "❌ Неверный номер заказа.\n\n"
            "Пример: <code>NEX-0025</code>",
            parse_mode="HTML"
        )
        return

    order = search_orders(order_id)

    if not order:

        await message.answer(
            "❌ Заказ не найден."
        )

        await state.clear()

        return

    await state.clear()

    await message.answer(
        order_text(order),
        parse_mode="HTML",
        reply_markup=order_keyboard(
            order["id"],
            order["status"]
        )
    )


# =========================================================
# NOTHING BUTTON
# =========================================================

@dp.callback_query(F.data == "nothing")
async def nothing(
    callback: CallbackQuery
):
    await callback.answer()


# =========================================================
# ERROR-LIKE FALLBACK
# =========================================================

@dp.message()
async def fallback(message: Message):

    await message.answer(
        "🤖 Используйте /start для начала работы с Nexus."
    )


# =========================================================
# RUN
# =========================================================

async def main():

    init_db()

    print("================================")
    print("       NEXUS BOT STARTED")
    print("================================")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())