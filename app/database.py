from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class ShipmentRecord(Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("user_phone", "tracking_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_phone: Mapped[str] = mapped_column(String(64), index=True)
    tracking_number: Mapped[str] = mapped_column(String(128), index=True)
    carrier: Mapped[str] = mapped_column(String(64))
    item_label: Mapped[str] = mapped_column(String(255), default="Online order")
    status: Mapped[str] = mapped_column(String(128), default="Pending")
    aftership_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    message_sid: Mapped[str] = mapped_column(String(128), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def _database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        return settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)
    path = Path(settings.database_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def database_ready() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def message_processed(message_sid: str) -> bool:
    with SessionLocal() as db:
        return db.get(ProcessedMessage, message_sid) is not None


def mark_message_processed(message_sid: str) -> None:
    with SessionLocal.begin() as db:
        if db.get(ProcessedMessage, message_sid) is None:
            db.add(ProcessedMessage(message_sid=message_sid))


def save_shipment(user_phone: str, tracking_number: str, carrier: str, item_label: str) -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        record = db.scalar(select(ShipmentRecord).where(
            ShipmentRecord.user_phone == user_phone,
            ShipmentRecord.tracking_number == tracking_number,
        ))
        if record is None:
            record = ShipmentRecord(
                user_phone=user_phone,
                tracking_number=tracking_number,
                carrier=carrier,
                item_label=item_label,
            )
            db.add(record)
            db.flush()
        else:
            record.carrier = carrier
            record.item_label = item_label
            record.updated_at = now
        return record.id


def attach_aftership(shipment_id: int, aftership_id: str, status: str) -> None:
    with SessionLocal.begin() as db:
        record = db.get(ShipmentRecord, shipment_id)
        if record:
            record.aftership_id = aftership_id or None
            record.status = status
            record.updated_at = datetime.now(timezone.utc)


def update_status(tracking_number: str, status: str) -> dict | None:
    with SessionLocal.begin() as db:
        record = db.scalar(select(ShipmentRecord).where(
            ShipmentRecord.tracking_number == tracking_number
        ).order_by(ShipmentRecord.id.desc()))
        if not record:
            return None
        record.status = status
        record.updated_at = datetime.now(timezone.utc)
        db.flush()
        return _as_dict(record)


def _as_dict(record: ShipmentRecord) -> dict:
    return {
        "id": record.id,
        "user_phone": record.user_phone,
        "tracking_number": record.tracking_number,
        "carrier": record.carrier,
        "item_label": record.item_label,
        "status": record.status,
        "aftership_id": record.aftership_id,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def list_shipments(phone: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        query = select(ShipmentRecord).order_by(ShipmentRecord.updated_at.desc()).limit(250)
        if phone:
            query = query.where(ShipmentRecord.user_phone == phone)
        return [_as_dict(row) for row in db.scalars(query).all()]


def list_customer_phones() -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(ShipmentRecord.user_phone).distinct()).all())
