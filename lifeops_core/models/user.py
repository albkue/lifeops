from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from lifeops_core.db.base import Base, TimestampedColumns, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, TimestampedColumns):
    """Single-user deployment (v1): one seeded row per instance.

    Kept as a real table from day one so every fact table carries a user_id
    FK and the schema is multi-user ready without a migration crisis later.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    # IANA timezone; used as the reporting timezone fallback in future phases.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
