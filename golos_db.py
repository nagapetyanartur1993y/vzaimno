"""Хранилище «Голосовалки»: один файл SQLite рядом с приложением.

На Streamlit Community Cloud файл живёт, пока жив контейнер: после
перезапуска или долгого простоя приложения данные обнуляются.
"""

import json
import os
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("GOLOS_DB") or str(Path(__file__).with_name("golos.db"))

# Без 0/O и 1/I — их путают, когда диктуют код вслух.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls (
    code       TEXT PRIMARY KEY,
    question   TEXT NOT NULL,
    options    TEXT NOT NULL,            -- JSON-список вариантов
    admin_key  TEXT NOT NULL,            -- ключ ведущего: завершить голосование
    closed     INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
    poll   TEXT NOT NULL,
    voter  TEXT NOT NULL,                -- случайный токен устройства, не имя
    choice INTEGER NOT NULL,             -- номер варианта
    PRIMARY KEY (poll, voter)
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
    """Транзакция с блокировкой записи: одновременные голоса не затрут друг друга."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def create_poll(question, options):
    admin_key = secrets.token_urlsafe(9)
    with _write() as conn:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if not conn.execute("SELECT 1 FROM polls WHERE code = ?", (code,)).fetchone():
                break
        conn.execute(
            "INSERT INTO polls (code, question, options, admin_key, created_at) VALUES (?, ?, ?, ?, ?)",
            (code, question, json.dumps(options, ensure_ascii=False), admin_key,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return code, admin_key


def get_poll(code):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM polls WHERE code = ?", (code,)).fetchone()
    if row is None:
        return None
    poll = dict(row)
    poll["options"] = json.loads(poll["options"])
    return poll


def is_admin(poll, key):
    # Сравниваем байты: со строками compare_digest падает на кириллице в испорченной ссылке.
    return secrets.compare_digest(key.encode(), poll["admin_key"].encode())


def vote(code, voter, choice):
    """Голос или его замена. False — голосование уже завершено."""
    with _write() as conn:
        poll = conn.execute("SELECT closed FROM polls WHERE code = ?", (code,)).fetchone()
        if poll is None or poll["closed"]:
            return False
        conn.execute("INSERT OR REPLACE INTO votes VALUES (?, ?, ?)", (code, voter, choice))
    return True


def my_vote(code, voter):
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT choice FROM votes WHERE poll = ? AND voter = ?", (code, voter)
        ).fetchone()
    return None if row is None else row["choice"]


def counts(code, n_options):
    """Сколько голосов у каждого варианта, по порядку."""
    result = [0] * n_options
    with closing(_connect()) as conn:
        for row in conn.execute(
            "SELECT choice, COUNT(*) AS n FROM votes WHERE poll = ? GROUP BY choice", (code,)
        ):
            if 0 <= row["choice"] < n_options:
                result[row["choice"]] = row["n"]
    return result


def set_closed(code, closed):
    with _write() as conn:
        conn.execute("UPDATE polls SET closed = ? WHERE code = ?", (int(closed), code))
