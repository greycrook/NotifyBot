import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bot.config import DB_PATH


@dataclass
class DutyUser:
    username: str
    display_name: str | None
    user_id: int | None
    position: int


def _ensure_db_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS duty_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT,
                user_id INTEGER,
                position INTEGER NOT NULL
            );
            """
        )
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'duty_index'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('duty_index', '0')"
            )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_chat_id() -> int | None:
    val = get_setting("chat_id", "")
    if not val:
        from bot.config import CHAT_ID
        return CHAT_ID or None
    return int(val)


def set_chat_id(chat_id: int) -> None:
    set_setting("chat_id", str(chat_id))


def get_duty_index() -> int:
    return int(get_setting("duty_index", "0"))


def set_duty_index(index: int) -> None:
    set_setting("duty_index", str(index))


def get_evening_advanced_on() -> date | None:
    val = get_setting("evening_advanced_on", "")
    if not val:
        return None
    return date.fromisoformat(val)


def set_evening_advanced_on(on_date: date) -> None:
    set_setting("evening_advanced_on", on_date.isoformat())


def list_duty_users() -> list[DutyUser]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT username, display_name, user_id, position
            FROM duty_users ORDER BY position
            """
        ).fetchall()
    return [
        DutyUser(
            username=r["username"],
            display_name=r["display_name"],
            user_id=r["user_id"],
            position=r["position"],
        )
        for r in rows
    ]


def add_duty_user(
    username: str, display_name: str | None = None, user_id: int | None = None
) -> str:
    return add_duty_users([(username, display_name, user_id)])


def add_duty_users(
    users: list[tuple[str, str | None, int | None]],
) -> str:
    if not users:
        return "Никого не добавить."

    added: list[tuple[str, int]] = []
    skipped: list[str] = []
    seen_in_batch: set[str] = set()

    with get_conn() as conn:
        max_pos = conn.execute("SELECT MAX(position) FROM duty_users").fetchone()[0]
        pos = 0 if max_pos is None else max_pos + 1

        for username, display_name, user_id in users:
            username = username.lower().lstrip("@")
            if username in seen_in_batch:
                skipped.append(f"@{username} — дубликат в команде, пропущен")
                continue
            seen_in_batch.add(username)

            if conn.execute(
                "SELECT 1 FROM duty_users WHERE username = ?", (username,)
            ).fetchone():
                skipped.append(f"@{username} уже в списке")
                continue

            conn.execute(
                """
                INSERT INTO duty_users (username, display_name, user_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (username, display_name, user_id, pos),
            )
            added.append((username, pos + 1))
            pos += 1

    if not added:
        if skipped:
            return "\n".join(skipped)
        return "Никого не добавлено."

    lines = [f"{i}. @{name} (позиция {position})" for i, (name, position) in enumerate(added, 1)]
    result = "Добавлены в очередь:\n" + "\n".join(lines)
    if skipped:
        result += "\n\n" + "\n".join(skipped)
    return result


def remove_duty_user(username: str) -> str:
    return remove_duty_users([username])


def remove_duty_users(usernames: list[str]) -> str:
    if not usernames:
        return "Никого не удалить."

    removed: list[str] = []
    skipped: list[str] = []
    seen_in_batch: set[str] = set()

    for raw in usernames:
        username = raw.lower().lstrip("@")
        if username in seen_in_batch:
            skipped.append(f"@{username} — дубликат в команде, пропущен")
            continue
        seen_in_batch.add(username)

        result = _remove_duty_user_once(username)
        if result.startswith("Удалён"):
            removed.append(username)
        elif "не найден" in result:
            skipped.append(f"@{username} не найден в списке")
        else:
            skipped.append(result)
            break

    if not removed:
        if skipped:
            return "\n".join(skipped)
        return "Никого не удалено."

    lines = [f"{i}. @{name}" for i, name in enumerate(removed, 1)]
    result = "Удалены из очереди:\n" + "\n".join(lines)
    if skipped:
        result += "\n\n" + "\n".join(skipped)
    return result


def _remove_duty_user_once(username: str) -> str:
    username = username.lower().lstrip("@")
    users = list_duty_users()
    if not users:
        return "Список дежурных пуст."
    target = next((u for u in users if u.username == username), None)
    if not target:
        return f"@{username} не найден в списке."

    with get_conn() as conn:
        conn.execute("DELETE FROM duty_users WHERE username = ?", (username,))
        remaining = conn.execute(
            "SELECT id FROM duty_users ORDER BY position"
        ).fetchall()
        for i, row in enumerate(remaining):
            conn.execute(
                "UPDATE duty_users SET position = ? WHERE id = ?", (i, row["id"])
            )

    idx = get_duty_index()
    if not remaining:
        set_duty_index(0)
    else:
        removed_pos = target.position
        new_len = len(remaining)
        if removed_pos < idx:
            set_duty_index((idx - 1) % new_len)
        elif idx >= new_len:
            set_duty_index(idx % new_len)

    return f"Удалён @{username}."


def update_user_meta(
    username: str, display_name: str | None, user_id: int | None
) -> None:
    username = username.lower().lstrip("@")
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE duty_users
            SET display_name = COALESCE(?, display_name),
                user_id = COALESCE(?, user_id)
            WHERE username = ?
            """,
            (display_name, user_id, username),
        )
