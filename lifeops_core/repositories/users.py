import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lifeops_core.config import Settings
from lifeops_core.models import User


class UserRepository:
    """Bootstrap + lookup for the (single) application user."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def save(self, user: User) -> User:
        """Persist insert or updates. Safe for reused or fresh objects."""
        self.session.add(user)
        self.session.commit()
        return user

    def save_records(self, records: list) -> list:
        """Bulk insert/upsert helper for demo seeding scripts."""
        self.session.add_all(records)
        self.session.commit()
        return records

    def first_user(self) -> User | None:
        return self.session.query(User).first()

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(User)) or 0

    def ensure_default_user(self, settings: Settings) -> User:
        """Idempotently create the single default user.

        Resolution order:
        1. explicit LIFEOPS_DEFAULT_USER_ID if present + exists,
        2. first existing user row,
        3. create one.
        """
        if settings.default_user_id:
            try:
                wanted = uuid.UUID(settings.default_user_id)
            except ValueError as exc:
                raise ValueError("LIFEOPS_DEFAULT_USER_ID is not a valid UUID") from exc
            existing = self.get(wanted)
            if existing:
                return existing

        existing = self.first_user()
        if existing:
            return existing

        user = User(
            id=uuid.UUID(settings.default_user_id) if settings.default_user_id else uuid.uuid4(),
            email=settings.default_user_email,
            display_name=settings.default_user_display_name,
            timezone=str(ZoneInfo(settings.timezone_name)),
            is_active=True,
        )
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError:
            # Lost a race (e.g. two processes booting); re-read.
            self.session.rollback()
            existing = self.first_user()
            assert existing is not None
            return existing
        return user

    def ensure_user(
        self, email: str, display_name: str | None = None, timezone: str = "Asia/Ho_Chi_Minh"
    ) -> User:
        """For demo seeding: fetch or create by email."""
        for user in self.session.query(User).all():
            if user.email == email:
                return user
        user = User(email=email, display_name=display_name, timezone=timezone)
        self.session.add(user)
        self.session.commit()
        return user
