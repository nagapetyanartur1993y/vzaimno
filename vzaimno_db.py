"""Хранилище «Взаимно?»: один файл SQLite рядом с приложением.

На Streamlit Community Cloud файл живёт, пока жив контейнер: после
перезапуска или долгого простоя приложения данные обнуляются.
"""

import os
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("VZAIMNO_DB") or str(Path(__file__).with_name("vzaimno.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs (
    id         TEXT PRIMARY KEY,
    question   TEXT NOT NULL,
    name_a     TEXT NOT NULL,
    name_b     TEXT NOT NULL,
    key_a      TEXT NOT NULL,
    key_b      TEXT NOT NULL,
    answered_a INTEGER NOT NULL DEFAULT 0,
    answered_b INTEGER NOT NULL DEFAULT 0,
    pending    INTEGER,                  -- ответ первого, пока второй не ответил
    result     INTEGER,                  -- 1 — оба «да», 0 — хотя бы одно «нет»
    created_at TEXT NOT NULL
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
    """Транзакция с блокировкой записи: два одновременных ответа не затрут друг друга."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def create_pair(question, name_a, name_b):
    pair = {
        "id": secrets.token_urlsafe(6),
        "key_a": secrets.token_urlsafe(9),
        "key_b": secrets.token_urlsafe(9),
    }
    with _write() as conn:
        conn.execute(
            "INSERT INTO pairs (id, question, name_a, name_b, key_a, key_b, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pair["id"], question, name_a, name_b, pair["key_a"], pair["key_b"],
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return pair


def get_pair(pair_id):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
    return dict(row) if row else None


def pair_role(pair, key):
    """'a' — создатель, 'b' — партнёр, None — чужая ссылка."""
    # Сравниваем байты: со строками compare_digest падает на кириллице в испорченной ссылке.
    key = key.encode()
    if secrets.compare_digest(key, pair["key_a"].encode()):
        return "a"
    if secrets.compare_digest(key, pair["key_b"].encode()):
        return "b"
    return None


def answer_pair(pair_id, role, yes):
    """Записывает ответ. Как только ответили оба, остаётся только итог — сами ответы стираются.

    Возвращает False, если с этой ссылки уже отвечали.
    """
    assert role in ("a", "b")
    other = "b" if role == "a" else "a"
    with _write() as conn:
        pair = conn.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
        if pair is None or pair[f"answered_{role}"]:
            return False
        if pair[f"answered_{other}"]:
            result = int(yes and pair["pending"] == 1)
            conn.execute(
                f"UPDATE pairs SET answered_{role} = 1, pending = NULL, result = ? WHERE id = ?",
                (result, pair_id),
            )
        else:
            conn.execute(
                f"UPDATE pairs SET answered_{role} = 1, pending = ? WHERE id = ?",
                (int(yes), pair_id),
            )
    return True
