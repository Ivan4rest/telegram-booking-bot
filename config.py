"""Настройки бота. Секреты — в файле .env, остальное меняется здесь."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "bookings.db")

BUSINESS_NAME = "Барбершоп «Демо»"
SERVICES = [
    {"name": "Стрижка", "price": "1 500 ₽"},
    {"name": "Стрижка + борода", "price": "2 200 ₽"},
    {"name": "Детская стрижка", "price": "1 000 ₽"},
]
OPEN_HOUR = 10   # первая запись в 10:00
CLOSE_HOUR = 20  # последняя запись в 19:00
DAYS_AHEAD = 7   # на сколько дней вперёд открыта запись
REMIND_HOURS = 2  # за сколько часов напоминать клиенту
