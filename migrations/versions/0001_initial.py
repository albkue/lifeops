"""initial lifeops schema

Revision ID: 0001
Revises:
Create Date: 2026-11-10

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TSTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "source_connections",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), server_default="live", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ok", nullable=False),
        sa.Column("credentials", postgresql.JSONB(), nullable=True),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("cursor", postgresql.JSONB(), nullable=True),
        sa.Column("last_sync_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('ok','error','expiring','disabled')",
            name=op.f("ck_source_connections_status"),
        ),
        sa.CheckConstraint("mode IN ('live','demo')", name=op.f("ck_source_connections_mode")),
        sa.UniqueConstraint(
            "user_id", "source_name", name=op.f("uq_source_connections_user_source")
        ),
    )

    op.create_table(
        "manual_daily_logs",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("sleep_hours", sa.Numeric(4, 2), nullable=True),
        sa.Column("mood_score", sa.SmallInteger(), nullable=True),
        sa.Column("study_hours", sa.Numeric(4, 2), nullable=True),
        sa.Column("coding_hours", sa.Numeric(4, 2), nullable=True),
        sa.Column("workout_minutes", sa.Integer(), nullable=True),
        sa.Column("soccer_minutes", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "tags", postgresql.ARRAY(sa.String(length=32)), server_default="{}", nullable=False
        ),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "mood_score IS NULL OR mood_score BETWEEN 1 AND 5",
            name=op.f("ck_manual_daily_logs_mood_range"),
        ),
        sa.CheckConstraint(
            "sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 24",
            name=op.f("ck_manual_daily_logs_sleep_range"),
        ),
        sa.CheckConstraint(
            "study_hours IS NULL OR study_hours BETWEEN 0 AND 24",
            name=op.f("ck_manual_daily_logs_study_range"),
        ),
        sa.CheckConstraint(
            "coding_hours IS NULL OR coding_hours BETWEEN 0 AND 24",
            name=op.f("ck_manual_daily_logs_coding_range"),
        ),
        sa.CheckConstraint(
            "workout_minutes IS NULL OR workout_minutes BETWEEN 0 AND 1440",
            name=op.f("ck_manual_daily_logs_workout_range"),
        ),
        sa.CheckConstraint(
            "soccer_minutes IS NULL OR soccer_minutes BETWEEN 0 AND 1440",
            name=op.f("ck_manual_daily_logs_soccer_range"),
        ),
        sa.UniqueConstraint("user_id", "log_date", name=op.f("uq_manual_daily_logs_user_date")),
    )

    op.create_table(
        "expenses",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("payment_method", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_expenses_amount_positive")),
        sa.CheckConstraint("length(currency) = 3", name=op.f("ck_expenses_currency_iso3")),
    )
    op.create_index("ix_expenses_user_date", "expenses", ["user_id", "expense_date"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("started_at", TSTZ, nullable=False),
        sa.Column("finished_at", TSTZ, nullable=True),
        sa.Column("window_start", TSTZ, nullable=True),
        sa.Column("window_end", TSTZ, nullable=True),
        sa.Column("records_extracted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_loaded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trigger", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("run_metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','success','failed','partial')",
            name=op.f("ck_ingestion_runs_status"),
        ),
        sa.CheckConstraint(
            "run_type IN ('manual','scheduled','backfill')", name=op.f("ck_ingestion_runs_run_type")
        ),
        sa.CheckConstraint(
            "records_extracted >= 0", name=op.f("ck_ingestion_runs_records_extracted_nonneg")
        ),
        sa.CheckConstraint(
            "records_loaded >= 0", name=op.f("ck_ingestion_runs_records_loaded_nonneg")
        ),
        sa.CheckConstraint("error_count >= 0", name=op.f("ck_ingestion_runs_error_count_nonneg")),
        sa.CheckConstraint(
            "window_end >= window_start", name=op.f("ck_ingestion_runs_window_valid")
        ),
    )
    op.create_index(
        "ix_ingestion_runs_source_started",
        "ingestion_runs",
        ["source_name", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_ingestion_runs_status_started", "ingestion_runs", ["status", sa.text("started_at DESC")]
    )

    op.create_table(
        "ingestion_errors",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "ingestion_run_id",
            UUID,
            sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("occurred_at", TSTZ, nullable=False),
    )

    op.create_table(
        "raw_source_objects",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "ingestion_run_id",
            UUID,
            sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=False),
        sa.Column("extraction_window_start", TSTZ, nullable=True),
        sa.Column("extraction_window_end", TSTZ, nullable=True),
        sa.Column("schema_version", sa.String(length=16), server_default="v1", nullable=False),
        sa.Column("ingested_at", TSTZ, nullable=False),
        sa.Column("attributes", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.UniqueConstraint(
            "source_name",
            "dataset",
            "payload_sha256",
            "extraction_window_start",
            name=op.f("uq_raw_source_objects_identity"),
        ),
        sa.UniqueConstraint("object_key", name=op.f("uq_raw_source_objects_object_key")),
    )
    op.create_index(
        "ix_raw_source_objects_ingested_at", "raw_source_objects", [sa.text("ingested_at DESC")]
    )
    op.create_index(
        "ix_raw_source_objects_source_day",
        "raw_source_objects",
        ["source_name", "extraction_window_start"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("rule_name", sa.String(length=96), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="warning", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("detected_at", TSTZ, nullable=False),
        sa.Column("resolved_at", TSTZ, nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')", name=op.f("ck_alerts_severity")
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','resolved')", name=op.f("ck_alerts_status")
        ),
        sa.UniqueConstraint(
            "user_id", "rule_name", "detected_at", name=op.f("uq_alerts_rule_detection")
        ),
    )

    op.create_table(
        "notification_channels",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "type IN ('console','telegram','discord','email')",
            name=op.f("ck_notification_channels_type"),
        ),
    )

    op.create_table(
        "report_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", TSTZ, nullable=False),
        sa.UniqueConstraint(
            "user_id", "report_type", "period_start", name=op.f("uq_report_snapshots_period")
        ),
    )

    op.create_table(
        "pipeline_config",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pipeline_config")
    op.drop_table("report_snapshots")
    op.drop_table("notification_channels")
    op.drop_table("alerts")
    op.drop_index("ix_raw_source_objects_source_day", table_name="raw_source_objects")
    op.drop_index("ix_raw_source_objects_ingested_at", table_name="raw_source_objects")
    op.drop_table("raw_source_objects")
    op.drop_table("ingestion_errors")
    op.drop_index("ix_ingestion_runs_status_started", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index("ix_expenses_user_date", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("manual_daily_logs")
    op.drop_table("source_connections")
    op.drop_table("users")
