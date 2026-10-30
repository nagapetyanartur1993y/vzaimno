"""Хранилище «Конверта»: один файл SQLite рядом с приложением.

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

import konvert_mechanisms as mechanisms

DB_PATH = os.environ.get("KONVERT_DB") or str(Path(__file__).with_name("konvert.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS envelopes (
    id         TEXT PRIMARY KEY,
    mech       TEXT NOT NULL,
    question   TEXT NOT NULL,
    params     TEXT NOT NULL,            -- JSON
    size       INTEGER NOT NULL,         -- сколько участников ждём
    result     TEXT,                     -- JSON; NULL, пока конверт не вскрыт
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope   TEXT NOT NULL,
    name       TEXT NOT NULL,
    name_key   TEXT NOT NULL,            -- casefold: COLLATE NOCASE в SQLite не знает кириллицу
    key        TEXT NOT NULL UNIQUE,     -- личная ссылка участника
    role       TEXT,                     -- для зоны сделки: seller / buyer
    is_creator INTEGER NOT NULL DEFAULT 0,
    UNIQUE (envelope, name_key)
);
CREATE TABLE IF NOT EXISTS answers (
    envelope  TEXT NOT NULL,
    member_id INTEGER NOT NULL,
    value     TEXT NOT NULL,             -- JSON; удаляется при вскрытии
    PRIMARY KEY (envelope, member_id)
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
    """Транзакция с блокировкой записи: одновременные ответы не затрут друг друга."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def normalize(text):
    return " ".join(text.split()).casefold()


def _envelope(row):
    env = dict(row)
    env["params"] = json.loads(env["params"])
    env["result"] = json.loads(env["result"]) if env["result"] else None
    return env


def _add_member(conn, env_id, name, role=None, is_creator=False):
    key = secrets.token_urlsafe(9)
    name = " ".join(name.split())
    conn.execute(
        "INSERT INTO members (envelope, name, name_key, key, role, is_creator) VALUES (?, ?, ?, ?, ?, ?)",
        (env_id, name, normalize(name), key, role, int(is_creator)),
    )
    return key


def create_envelope(mech, question, params, size, creator_name, creator_role=None):
    """Возвращает (id конверта, личный ключ создателя)."""
    env_id = secrets.token_urlsafe(6)
    with _write() as conn:
        conn.execute(
            "INSERT INTO envelopes (id, mech, question, params, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (env_id, mech, question, json.dumps(params, ensure_ascii=False), size,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        key = _add_member(conn, env_id, creator_name, creator_role, is_creator=True)
    return env_id, key


def get_envelope(env_id):
    rows = _read("SELECT * FROM envelopes WHERE id = ?", (env_id,))
    return _envelope(rows[0]) if rows else None


def members(env_id):
    """Участники без их ключей: ключ — это личная ссылка, его знает только сам участник."""
    rows = _read("SELECT id, name, role, is_creator FROM members WHERE envelope = ? ORDER BY id", (env_id,))
    return [dict(r) for r in rows]


def member_by_key(env_id, key):
    rows = _read("SELECT * FROM members WHERE envelope = ? AND key = ?", (env_id, key))
    return dict(rows[0]) if rows else None


def join(env_id, name):
    """Возвращает (статус, ключ): 'ok', 'taken' — имя занято, 'full' — мест нет, 'closed' — уже вскрыт."""
    with _write() as conn:
        env = conn.execute("SELECT * FROM envelopes WHERE id = ?", (env_id,)).fetchone()
        if env is None or env["result"] is not None:
            return "closed", None
        rows = conn.execute("SELECT name_key, role FROM members WHERE envelope = ?", (env_id,)).fetchall()
        if len(rows) >= env["size"]:
            return "full", None
        if normalize(name) in {r["name_key"] for r in rows}:
            return "taken", None
        # Если у механизма есть роли (зона сделки), новичку достаётся свободная.
        roles = json.loads(env["params"]).get("roles", {})
        role = next((r for r in roles if r not in {row["role"] for row in rows}), None)
        return "ok", _add_member(conn, env_id, name, role)


def answered_ids(env_id):
    return {r["member_id"] for r in _read("SELECT member_id FROM answers WHERE envelope = ?", (env_id,))}


def get_answer(env_id, member_id):
    rows = _read("SELECT value FROM answers WHERE envelope = ? AND member_id = ?", (env_id, member_id))
    return json.loads(rows[0]["value"]) if rows else None


def save_answer(env_id, member_id, value):
    """Кладёт или меняет ответ. Когда ответили все, конверт вскрывается сам. False — уже вскрыт."""
    with _write() as conn:
        env = conn.execute("SELECT * FROM envelopes WHERE id = ?", (env_id,)).fetchone()
        if env is None or env["result"] is not None:
            return False
        conn.execute(
            "INSERT INTO answers VALUES (?, ?, ?)"
            " ON CONFLICT (envelope, member_id) DO UPDATE SET value = excluded.value",
            (env_id, member_id, json.dumps(value, ensure_ascii=False)),
        )
        answered = conn.execute("SELECT COUNT(*) FROM answers WHERE envelope = ?", (env_id,)).fetchone()[0]
        if answered >= env["size"]:
            _reveal(conn, env)
    return True


def open_envelope(env_id):
    """Досрочное вскрытие по решению создателя: итог считается по тем, кто успел ответить."""
    with _write() as conn:
        env = conn.execute("SELECT * FROM envelopes WHERE id = ?", (env_id,)).fetchone()
        if env is not None and env["result"] is None:
            _reveal(conn, env)


def _reveal(conn, env):
    members_ = {
        r["id"]: {"name": r["name"], "role": r["role"]}
        for r in conn.execute("SELECT id, name, role FROM members WHERE envelope = ?", (env["id"],))
    }
    answers = {
        r["member_id"]: json.loads(r["value"])
        for r in conn.execute("SELECT member_id, value FROM answers WHERE envelope = ?", (env["id"],))
    }
    result = mechanisms.reveal(env["mech"], json.loads(env["params"]), members_, answers)
    conn.execute("UPDATE envelopes SET result = ? WHERE id = ?", (json.dumps(result, ensure_ascii=False), env["id"]))
    conn.execute("DELETE FROM answers WHERE envelope = ?", (env["id"],))
