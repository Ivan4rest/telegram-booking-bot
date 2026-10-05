"""Telegram-бот записи на услуги: выбор услуги, дня и времени, уведомление
администратору, напоминание клиенту, отмена записи.

Запуск: python bot.py
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, F
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
    ReplyKeyboardRemove,
)

import config
import db

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

dp = Dispatcher()
conn = db.connect()


class Booking(StatesGroup):
    phone = State()


def keyboard(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows]
    )


def main_menu():
    return keyboard([[("📅 Записаться", "book")], [("🗒 Мои записи", "mine")]])


def human(starts_at):
    moment = datetime.fromisoformat(starts_at) if isinstance(starts_at, str) else starts_at
    return f"{moment:%d.%m} ({WEEKDAYS[moment.weekday()]}) в {moment:%H:%M}"


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Здравствуйте! Это бот записи в {config.BUSINESS_NAME}.", reply_markup=main_menu())


@dp.callback_query(F.data == "book")
async def choose_service(call: CallbackQuery):
    rows = [[(f"{s['name']} — {s['price']}", f"svc:{i}")] for i, s in enumerate(config.SERVICES)]
    await call.message.edit_text("Выберите услугу:", reply_markup=keyboard(rows))
    await call.answer()


@dp.callback_query(F.data.startswith("svc:"))
async def choose_day(call: CallbackQuery):
    service = call.data.split(":")[1]
    rows = []
    for offset in range(config.DAYS_AHEAD):
        day = date.today() + timedelta(days=offset)
        if db.free_slots(conn, day):
            rows.append([(f"{day:%d.%m} ({WEEKDAYS[day.weekday()]})", f"day:{service}:{day.isoformat()}")])
    rows.append([("« Назад", "book")])
    await call.message.edit_text("Выберите день:", reply_markup=keyboard(rows))
    await call.answer()


@dp.callback_query(F.data.startswith("day:"))
async def choose_time(call: CallbackQuery):
    _, service, day = call.data.split(":")
    slots = db.free_slots(conn, date.fromisoformat(day))
    buttons = [(f"{slot:%H:%M}", f"time:{service}:{day}:{slot.hour}") for slot in slots]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([("« Назад", f"svc:{service}")])
    await call.message.edit_text("Выберите время:", reply_markup=keyboard(rows))
    await call.answer()


@dp.callback_query(F.data.startswith("time:"))
async def ask_phone(call: CallbackQuery, state: FSMContext):
    _, service, day, hour = call.data.split(":")
    starts_at = datetime.fromisoformat(day).replace(hour=int(hour))
    await state.set_state(Booking.phone)
    await state.update_data(service=config.SERVICES[int(service)]["name"], starts_at=starts_at.isoformat())
    await call.message.edit_text(f"{config.SERVICES[int(service)]['name']}, {human(starts_at)}.")
    await call.message.answer(
        "Оставьте номер телефона для связи — нажмите кнопку или напишите его сообщением.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    await call.answer()


@dp.message(Booking.phone, F.contact | F.text)
async def finish(message: Message, state: FSMContext, bot: Bot):
    phone = message.contact.phone_number if message.contact else message.text.strip()
    if sum(char.isdigit() for char in phone) < 7:
        await message.answer("Не похоже на номер телефона. Попробуйте ещё раз.")
        return
    data = await state.get_data()
    await state.clear()
    starts_at = datetime.fromisoformat(data["starts_at"])
    saved = db.add_booking(
        conn, message.from_user.id, message.from_user.full_name, phone, data["service"], starts_at
    )
    if not saved:
        await message.answer("Это время только что заняли 😔", reply_markup=ReplyKeyboardRemove())
        await message.answer("Выберите другое:", reply_markup=main_menu())
        return
    await message.answer(
        f"✅ Вы записаны: {data['service']}, {human(starts_at)}.\n"
        f"Напомню за {config.REMIND_HOURS} ч. до визита.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Что дальше?", reply_markup=main_menu())
    if config.ADMIN_ID:
        await bot.send_message(
            config.ADMIN_ID,
            f"🆕 Новая запись\n{data['service']}, {human(starts_at)}\n{message.from_user.full_name}, {phone}",
        )


@dp.callback_query(F.data == "mine")
async def my_bookings(call: CallbackQuery):
    bookings = db.upcoming(conn, call.from_user.id)
    if not bookings:
        await call.message.edit_text("У вас нет предстоящих записей.", reply_markup=main_menu())
    else:
        text = "Ваши записи:\n" + "\n".join(f"• {b['service']}, {human(b['starts_at'])}" for b in bookings)
        rows = [[(f"❌ Отменить {human(b['starts_at'])}", f"cancel:{b['id']}")] for b in bookings]
        rows.append([("📅 Записаться ещё", "book")])
        await call.message.edit_text(text, reply_markup=keyboard(rows))
    await call.answer()


@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_booking(call: CallbackQuery, bot: Bot):
    booking_id = int(call.data.split(":")[1])
    booking = next((b for b in db.upcoming(conn, call.from_user.id) if b["id"] == booking_id), None)
    if booking and db.cancel(conn, booking_id, call.from_user.id):
        await call.answer("Запись отменена")
        if config.ADMIN_ID:
            await bot.send_message(
                config.ADMIN_ID,
                f"🚫 Отмена записи\n{booking['service']}, {human(booking['starts_at'])}\n"
                f"{booking['user_name']}, {booking['phone']}",
            )
    await my_bookings(call)


@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    bookings = db.upcoming(conn)
    if not bookings:
        await message.answer("Предстоящих записей нет.")
        return
    await message.answer(
        "Предстоящие записи:\n"
        + "\n".join(f"• {human(b['starts_at'])} — {b['service']}, {b['user_name']}, {b['phone']}" for b in bookings)
    )


async def remind(bot: Bot):
    while True:
        for booking in db.due_reminders(conn):
            try:
                await bot.send_message(
                    booking["user_id"],
                    f"⏰ Напоминаем: {booking['service']}, {human(booking['starts_at'])}. Ждём вас!",
                )
            except Exception:
                logging.exception("Не удалось отправить напоминание %s", booking["id"])
        await asyncio.sleep(60)


async def main():
    logging.basicConfig(level=logging.INFO)
    if not config.BOT_TOKEN:
        raise SystemExit("Укажите BOT_TOKEN в файле .env (см. .env.example)")
    bot = Bot(config.BOT_TOKEN)
    reminder = asyncio.create_task(remind(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminder.cancel()


if __name__ == "__main__":
    asyncio.run(main())
