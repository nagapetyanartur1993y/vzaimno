"""Хранилище «Когда гуляем?»: один файл SQLite рядом с приложением.

На Streamlit Community Cloud файл живёт, пока жив контейнер: после
перезапуска или долгого простоя приложения данные обнуляются.
"""

import os
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("KOGDA_DB") or str(Path(__file__).with_name("kogda.db"))

# Без 0/O и 1/I — их путают, когда диктуют код вслух.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    code       TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    first_day  TEXT NOT NULL,            -- 2026-11-02
    days       INTEGER NOT NULL,
    start_hour INTEGER NOT NULL,
    end_hour   INTEGER NOT NULL,         -- последний час, который можно отметить, — end_hour - 1
    duration   INTEGER NOT NULL,         -- сколько часов гуляем
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    plan     TEXT NOT NULL,
    name     TEXT NOT NULL,
    name_key TEXT NOT NULL,              -- casefold: COLLATE NOCASE в SQLite не знает кириллицу
    slots    TEXT,                       -- свободные часы через запятую: 2026-11-02T18,…; NULL — ещё не отмечал
    UNIQUE (plan, name_key)
);
"""

_schema_ready = False


def _connect():
    global _schema_ready
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    if not _schema_ready:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _schema_ready = True
    return conn


@contextmanager
def _write():
    """Транзакция с блокировкой записи: одновременные ответы не затрут друг друга."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def normalize(name):
    """«  Петя » и «петя» — одно имя."""
    return " ".join(name.split()).casefold()


def create_plan(title, first_day, days, start_hour, end_hour, duration, creator_name):
    with _write() as conn:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if not conn.execute("SELECT 1 FROM plans WHERE code = ?", (code,)).fetchone():
                break
        conn.execute(
            "INSERT INTO plans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, title, first_day.isoformat(), days, start_hour, end_hour, duration,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        member_id = _join(conn, code, creator_name)
    return code, member_id


def get_plan(code):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM plans WHERE code = ?", (code,)).fetchone()
    if row is None:
        return None
    plan = dict(row)
    plan["first_day"] = date.fromisoformat(plan["first_day"])
    return plan


def _join(conn, code, name):
    name = " ".join(name.split())
    row = conn.execute(
        "SELECT id FROM members WHERE plan = ? AND name_key = ?", (code, normalize(name))
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO members (plan, name, name_key) VALUES (?, ?, ?)",
        (code, name, normalize(name)),
    )
    return cur.lastrowid


def join(code, name):
    """Возвращает id участника; если такое имя уже есть — это он и есть."""
    with _write() as conn:
        return _join(conn, code, name)


def members(code):
    """Участники по порядку; slots — множество свободных часов или None, если ещё не отмечал."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, name, slots FROM members WHERE plan = ? ORDER BY id", (code,)
        ).fetchall()
    return [
        {"id": r["id"], "name": r["name"],
         "slots": None if r["slots"] is None else set(filter(None, r["slots"].split(",")))}
        for r in rows
    ]


def save_slots(member_id, slots):
    with _write() as conn:
        conn.execute(
            "UPDATE members SET slots = ? WHERE id = ?", (",".join(sorted(slots)), member_id)
        )
