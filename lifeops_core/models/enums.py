"""Loosely-coupled string enums that match database CHECK constraints.

These are also reused by Pydantic schemas, so DB and API can never drift
apart for these value sets.
"""

from enum import StrEnum


class SourceName(StrEnum):
    GITHUB = "github"
    CALENDAR = "calendar"
    SPOTIFY = "spotify"
    WEATHER = "weather"
    MANUAL_LOGS = "manual_logs"
    EXPENSES = "expenses"

    @classmethod
    def extractable(cls) -> tuple["SourceName", ...]:
        """Sources with an extraction pipeline (adapters arrive Phase 6+)."""
        return (cls.GITHUB, cls.CALENDAR, cls.SPOTIFY, cls.WEATHER)

    @classmethod
    def all_values(cls) -> tuple[str, ...]:
        return tuple(m.value for m in cls)


class ConnectionMode(StrEnum):
    LIVE = "live"
    DEMO = "demo"


class ConnectionStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    EXPIRING = "expiring"
    DISABLED = "disabled"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class RunType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    BACKFILL = "backfill"


class ErrorStage(StrEnum):
    EXTRACT = "extract"
    VALIDATE = "validate"
    LOAD = "load"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ChannelType(StrEnum):
    CONSOLE = "console"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"


class ReportType(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
