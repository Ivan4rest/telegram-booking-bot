"""Хранилище записей на SQLite."""
import sqlite3
from datetime import datetime, timedelta

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    service TEXT NOT NULL,
    starts_at TEXT NOT NULL UNIQUE,
    reminded INTEGER NOT NULL DEFAULT 0
)
"""


def connect(path=config.DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def free_slots(conn, day, now=None):
    """Свободные времена начала на дату day, без прошедших."""
    now = now or datetime.now()
    taken = {
        row["starts_at"]
        for row in conn.execute("SELECT starts_at FROM bookings WHERE starts_at LIKE ?", (f"{day}%",))
    }
    slots = []
    for hour in range(config.OPEN_HOUR, config.CLOSE_HOUR):
        start = datetime.combine(day, datetime.min.time()).replace(hour=hour)
        if start > now and start.isoformat() not in taken:
            slots.append(start)
    return slots


def add_booking(conn, user_id, user_name, phone, service, starts_at):
    """Создаёт запись. Возвращает False, если время уже заняли."""
    try:
        with conn:
            conn.execute(
                "INSERT INTO bookings (user_id, user_name, phone, service, starts_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, user_name, phone, service, starts_at.isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def upcoming(conn, user_id=None, now=None):
    now = (now or datetime.now()).isoformat()
    query = "SELECT * FROM bookings WHERE starts_at > ?"
    params = [now]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    return conn.execute(query + " ORDER BY starts_at", params).fetchall()


def cancel(conn, booking_id, user_id):
    with conn:
        return conn.execute(
            "DELETE FROM bookings WHERE id = ? AND user_id = ?", (booking_id, user_id)
        ).rowcount > 0


def due_reminders(conn, now=None):
    """Записи, до которых осталось меньше REMIND_HOURS и напоминание ещё не отправлено."""
    now = now or datetime.now()
    rows = conn.execute(
        "SELECT * FROM bookings WHERE reminded = 0 AND starts_at > ? AND starts_at <= ?",
        (now.isoformat(), (now + timedelta(hours=config.REMIND_HOURS)).isoformat()),
    ).fetchall()
    with conn:
        conn.executemany("UPDATE bookings SET reminded = 1 WHERE id = ?", [(row["id"],) for row in rows])
    return rows
