from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine
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
