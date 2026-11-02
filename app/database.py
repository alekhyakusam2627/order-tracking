import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import get_settings


def _path() -> Path:
    path = Path(get_settings().database_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect():
    conn = sqlite3.connect(_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT NOT NULL,
                tracking_number TEXT NOT NULL,
                carrier TEXT NOT NULL,
                item_label TEXT NOT NULL DEFAULT 'Online order',
                status TEXT NOT NULL DEFAULT 'Pending',
                aftership_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_phone, tracking_number)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_sid TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def message_processed(message_sid: str) -> bool:
    with connect() as db:
        return db.execute(
            "SELECT 1 FROM processed_messages WHERE message_sid=?", (message_sid,)
        ).fetchone() is not None


def mark_message_processed(message_sid: str) -> None:
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO processed_messages (message_sid) VALUES (?)", (message_sid,)
        )


def save_shipment(user_phone: str, tracking_number: str, carrier: str, item_label: str) -> int:
    with connect() as db:
        db.execute("""
            INSERT INTO shipments (user_phone, tracking_number, carrier, item_label)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_phone, tracking_number) DO UPDATE SET
              carrier=excluded.carrier, item_label=excluded.item_label, updated_at=CURRENT_TIMESTAMP
        """, (user_phone, tracking_number, carrier, item_label))
        row = db.execute(
            "SELECT id FROM shipments WHERE user_phone=? AND tracking_number=?",
            (user_phone, tracking_number),
        ).fetchone()
        return int(row["id"])


def attach_aftership(shipment_id: int, aftership_id: str, status: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE shipments SET aftership_id=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (aftership_id, status, shipment_id),
        )


def update_status(tracking_number: str, status: str) -> sqlite3.Row | None:
    with connect() as db:
        db.execute(
            "UPDATE shipments SET status=?, updated_at=CURRENT_TIMESTAMP WHERE tracking_number=?",
            (status, tracking_number),
        )
        return db.execute(
            "SELECT * FROM shipments WHERE tracking_number=? ORDER BY id DESC LIMIT 1",
            (tracking_number,),
        ).fetchone()


def list_shipments(phone: str | None = None) -> list[dict]:
    with connect() as db:
        if phone:
            rows = db.execute(
                "SELECT * FROM shipments WHERE user_phone=? ORDER BY updated_at DESC", (phone,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM shipments ORDER BY updated_at DESC LIMIT 250").fetchall()
        return [dict(row) for row in rows]
