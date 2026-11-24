from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    seats: Mapped[int] = mapped_column(Integer, default=5)
    trial_ends_at: Mapped[datetime] = mapped_column(DateTime)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    users: Mapped[list["User"]] = relationship(back_populates="org")

    @property
    def licence_until(self) -> datetime:
        if self.paid_until and self.paid_until > self.trial_ends_at:
            return self.paid_until
        return self.trial_ends_at

    @property
    def is_licensed(self) -> bool:
        return utcnow() < self.licence_until

    @property
    def plan(self) -> str:
        return "paid" if self.paid_until and self.paid_until > utcnow() else "trial"

    @property
    def days_left(self) -> int:
        return max(0, (self.licence_until - utcnow()).days)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="agent")  # owner | admin | agent
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    org: Mapped[Org] = relationship(back_populates="users")

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "device_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_hash: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)   # removed by an administrator
    released: Mapped[bool] = mapped_column(Boolean, default=False)  # signed out by the user
    user: Mapped[User] = relationship()


class UsageDaily(Base):
    """Usage metadata only (seconds processed). No audio or call content is ever stored."""
    __tablename__ = "usage_daily"
    __table_args__ = (UniqueConstraint("device_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    mic_seconds: Mapped[int] = mapped_column(Integer, default=0)
    speaker_seconds: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
