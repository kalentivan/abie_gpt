from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class ConversationRecord(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    chatgpt_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chatgpt_url: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NamedDialogRecord(Base):
    __tablename__ = "named_dialogs"
    __table_args__ = (UniqueConstraint("owner_key", "name", name="uq_named_dialog_owner_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    chatgpt_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chatgpt_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerStateRecord(Base):
    __tablename__ = "worker_states"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(64))
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AutorunRecord(Base):
    __tablename__ = "autoruns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, default=50)
    stop_marker: Mapped[str] = mapped_column(String(255), default="TASK_COMPLETE")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Database:
    def __init__(self, url: str):
        connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.sessions()

    def save_worker_state(self, worker_id: str, status: str, iteration: int,
                          conversation_id: str | None, last_response: str | None,
                          completed: bool) -> None:
        now = datetime.now(timezone.utc)
        with self.session() as db:
            row = db.query(WorkerStateRecord).filter_by(worker_id=worker_id).one_or_none()
            if row is None:
                row = WorkerStateRecord(worker_id=worker_id, status=status, iteration=iteration,
                    conversation_id=conversation_id, last_response=last_response,
                    completed=completed, updated_at=now)
                db.add(row)
            else:
                row.status, row.iteration = status, iteration
                row.conversation_id, row.last_response = conversation_id, last_response
                row.completed, row.updated_at = completed, now
            db.commit()

    def get_conversation(self, external_key: str) -> ConversationRecord | None:
        with self.session() as db:
            row = db.query(ConversationRecord).filter_by(external_key=external_key).one_or_none()
            if row is not None:
                db.expunge(row)
            return row

    def save_conversation(self, external_key: str, chatgpt_id: str | None, chatgpt_url: str) -> None:
        now = datetime.now(timezone.utc)
        with self.session() as db:
            row = db.query(ConversationRecord).filter_by(external_key=external_key).one_or_none()
            if row is None:
                db.add(ConversationRecord(external_key=external_key, chatgpt_id=chatgpt_id,
                                          chatgpt_url=chatgpt_url, updated_at=now))
            else:
                row.chatgpt_id, row.chatgpt_url, row.updated_at = chatgpt_id, chatgpt_url, now
            db.commit()

    def save_named_dialog(self, owner_key: str, name: str, chatgpt_id: str | None,
                          chatgpt_url: str) -> NamedDialogRecord:
        now = datetime.now(timezone.utc)
        with self.session() as db:
            row = db.query(NamedDialogRecord).filter_by(owner_key=owner_key, name=name).one_or_none()
            if row is None:
                row = NamedDialogRecord(owner_key=owner_key, name=name, chatgpt_id=chatgpt_id,
                                        chatgpt_url=chatgpt_url, created_at=now, last_used_at=now)
                db.add(row)
            else:
                row.chatgpt_id, row.chatgpt_url, row.last_used_at = chatgpt_id, chatgpt_url, now
            db.commit()
            db.refresh(row)
            db.expunge(row)
            return row

    def get_named_dialog(self, owner_key: str, name: str) -> NamedDialogRecord | None:
        with self.session() as db:
            row = db.query(NamedDialogRecord).filter_by(owner_key=owner_key, name=name).one_or_none()
            if row is not None:
                db.expunge(row)
            return row

    def list_named_dialogs(self, owner_key: str) -> list[NamedDialogRecord]:
        with self.session() as db:
            rows = (db.query(NamedDialogRecord).filter_by(owner_key=owner_key)
                    .order_by(NamedDialogRecord.last_used_at.desc(), NamedDialogRecord.id.desc()).all())
            for row in rows:
                db.expunge(row)
            return rows

    def next_dialog_name(self, owner_key: str) -> str:
        existing = {row.name.casefold() for row in self.list_named_dialogs(owner_key)}
        number = 1
        while f"диалог {number}".casefold() in existing:
            number += 1
        return f"Диалог {number}"

    def touch_named_dialog(self, owner_key: str, name: str, chatgpt_id: str | None,
                           chatgpt_url: str) -> None:
        self.save_named_dialog(owner_key, name, chatgpt_id, chatgpt_url)

    def set_autorun(self, external_key: str, enabled: bool, *, max_iterations: int = 50,
                    stop_marker: str = "TASK_COMPLETE", reset: bool = False) -> None:
        now = datetime.now(timezone.utc)
        with self.session() as db:
            row = db.query(AutorunRecord).filter_by(external_key=external_key).one_or_none()
            if row is None:
                row = AutorunRecord(external_key=external_key, enabled=enabled, iteration=0,
                    max_iterations=max_iterations, stop_marker=stop_marker, updated_at=now)
                db.add(row)
            else:
                row.enabled, row.max_iterations = enabled, max_iterations
                row.stop_marker, row.updated_at = stop_marker, now
                if reset:
                    row.iteration = 0
            db.commit()

    def get_autorun(self, external_key: str) -> AutorunRecord | None:
        with self.session() as db:
            row = db.query(AutorunRecord).filter_by(external_key=external_key).one_or_none()
            if row is not None:
                db.expunge(row)
            return row

    def advance_autorun(self, external_key: str) -> int:
        with self.session() as db:
            row = db.query(AutorunRecord).filter_by(external_key=external_key).one()
            row.iteration += 1
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            return row.iteration
