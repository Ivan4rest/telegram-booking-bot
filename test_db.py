from datetime import date, datetime

import db

NOW = datetime(2026, 10, 5, 12, 30)
DAY = date(2026, 10, 5)


def make():
    return db.connect(":memory:")


def test_free_slots_skip_past_and_taken():
    conn = make()
    slots = db.free_slots(conn, DAY, NOW)
    assert [slot.hour for slot in slots] == list(range(13, 20))
    assert db.add_booking(conn, 1, "Анна", "+37400000000", "Стрижка", slots[0])
    assert [slot.hour for slot in db.free_slots(conn, DAY, NOW)] == list(range(14, 20))


def test_slot_cannot_be_booked_twice():
    conn = make()
    slot = db.free_slots(conn, DAY, NOW)[0]
    assert db.add_booking(conn, 1, "Анна", "+37400000000", "Стрижка", slot)
    assert not db.add_booking(conn, 2, "Борис", "+37411111111", "Стрижка", slot)


def test_cancel_only_own_booking():
    conn = make()
    db.add_booking(conn, 1, "Анна", "+37400000000", "Стрижка", db.free_slots(conn, DAY, NOW)[0])
    booking_id = db.upcoming(conn, 1, NOW)[0]["id"]
    assert not db.cancel(conn, booking_id, user_id=2)
    assert db.cancel(conn, booking_id, user_id=1)
    assert db.upcoming(conn, now=NOW) == []


def test_reminder_is_sent_once():
    conn = make()
    db.add_booking(conn, 1, "Анна", "+37400000000", "Стрижка", db.free_slots(conn, DAY, NOW)[0])
    assert len(db.due_reminders(conn, NOW)) == 1
    assert db.due_reminders(conn, NOW) == []
