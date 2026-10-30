"""Хранилище «Договорились»: один файл SQLite рядом с приложением.

На Streamlit Community Cloud файл живёт, пока жив контейнер: после
перезапуска или долгого простоя приложения данные обнуляются.
"""

import os
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("DOGOVORILIS_DB") or str(Path(__file__).with_name("dogovorilis.db"))

# Без 0/O и 1/I — их путают, когда диктуют код вслух.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    code       TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    sections   TEXT NOT NULL,            -- через запятую: when,where,what
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    room     TEXT NOT NULL,
    name     TEXT NOT NULL,
    name_key TEXT NOT NULL,              -- casefold: COLLATE NOCASE в SQLite не знает кириллицу
    UNIQUE (room, name_key)
);
CREATE TABLE IF NOT EXISTS options (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    room      TEXT NOT NULL,
    section   TEXT NOT NULL,
    text      TEXT NOT NULL,
    text_key  TEXT NOT NULL,
    link      TEXT,
    sort_key  TEXT NOT NULL,
    author_id INTEGER NOT NULL,
    UNIQUE (room, section, text_key)
);
CREATE TABLE IF NOT EXISTS votes (
    option_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    PRIMARY KEY (option_id, member_id)
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


def _read(sql, params=()):
    with closing(_connect()) as conn:
        return conn.execute(sql, params).fetchall()


@contextmanager
def _write():
    """Транзакция с блокировкой записи: одновременные голоса не затрут друг друга."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(text):
    """«  Петя » и «петя» — одно имя; «Ёлки» и «ёлки» — один вариант."""
    return " ".join(text.split()).casefold()


# --- Встречи ---------------------------------------------------------------


def create_room(title, sections, creator_name):
    with _write() as conn:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if not conn.execute("SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone():
                break
        conn.execute(
            "INSERT INTO rooms VALUES (?, ?, ?, ?)",
            (code, title, ",".join(sections), _now()),
        )
        member_id = _join(conn, code, creator_name)
    return code, member_id


def get_room(code):
    rows = _read("SELECT * FROM rooms WHERE code = ?", (code,))
    if not rows:
        return None
    room = dict(rows[0])
    room["sections"] = room["sections"].split(",")
    return room


def _join(conn, code, name):
    name = " ".join(name.split())
    row = conn.execute(
        "SELECT id FROM members WHERE room = ? AND name_key = ?", (code, normalize(name))
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO members (room, name, name_key) VALUES (?, ?, ?)",
        (code, name, normalize(name)),
    )
    return cur.lastrowid


def join_room(code, name):
    """Возвращает id участника; если такое имя уже есть — это он и есть."""
    with _write() as conn:
        return _join(conn, code, name)


def members(code):
    return [dict(r) for r in _read("SELECT id, name FROM members WHERE room = ? ORDER BY id", (code,))]


def add_option(code, section, text, link, sort_key, author_id):
    """Добавляет вариант и сразу голос автора. False — такой вариант уже есть."""
    text = " ".join(text.split())
    with _write() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO options (room, section, text, text_key, link, sort_key, author_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, section, text, normalize(text), link or None, sort_key, author_id),
            )
        except sqlite3.IntegrityError:
            return False
        conn.execute("INSERT INTO votes VALUES (?, ?)", (cur.lastrowid, author_id))
    return True


def delete_option(option_id, author_id):
    """Удалить можно только свой вариант и только пока за него не голосовал никто другой."""
    with _write() as conn:
        others = conn.execute(
            "SELECT 1 FROM votes WHERE option_id = ? AND member_id != ?", (option_id, author_id)
        ).fetchone()
        if others:
            return False
        deleted = conn.execute(
            "DELETE FROM options WHERE id = ? AND author_id = ?", (option_id, author_id)
        ).rowcount
        conn.execute("DELETE FROM votes WHERE option_id = ?", (option_id,))
    return bool(deleted)


def set_vote(option_id, member_id, on):
    with _write() as conn:
        if on:
            conn.execute("INSERT OR IGNORE INTO votes VALUES (?, ?)", (option_id, member_id))
        else:
            conn.execute(
                "DELETE FROM votes WHERE option_id = ? AND member_id = ?", (option_id, member_id)
            )


def section_options(code, section):
    """Варианты раздела по порядку (время — хронологически) с теми, кто за них."""
    with closing(_connect()) as conn:
        options = [
            dict(r, voters=[], voter_ids=set())
            for r in conn.execute(
                "SELECT id, text, link, author_id FROM options"
                " WHERE room = ? AND section = ? ORDER BY sort_key, id",
                (code, section),
            )
        ]
        by_id = {o["id"]: o for o in options}
        for row in conn.execute(
            "SELECT v.option_id, m.id, m.name FROM votes v"
            " JOIN options o ON o.id = v.option_id"
            " JOIN members m ON m.id = v.member_id"
            " WHERE o.room = ? AND o.section = ? ORDER BY m.id",
            (code, section),
        ):
            by_id[row["option_id"]]["voters"].append(row["name"])
            by_id[row["option_id"]]["voter_ids"].add(row["id"])
    return options

