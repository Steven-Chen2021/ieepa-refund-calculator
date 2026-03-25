"""Initial schema — all core tables

Revision ID: 0001
Revises:
Create Date: 2026-03-04

Tables created:
  - users
  - documents
  - calculations
  - calculation_audit  (append-only; protected by trigger)
  - leads              (full_name / email / phone stored as Fernet ciphertext)
  - tariff_rates
  - audit_log
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── ENUM types ───────────────────────────────────────────────────────────

    if is_postgres:
        user_role_enum = postgresql.ENUM(
            "user", "admin", name="user_role_enum", create_type=False
        )
        user_role_enum.create(bind, checkfirst=True)

        document_status_enum = postgresql.ENUM(
            "queued", "processing", "completed", "review_required", "failed",
            name="document_status_enum", create_type=False,
        )
        document_status_enum.create(bind, checkfirst=True)

        calculation_status_enum = postgresql.ENUM(
            "pending", "calculating", "completed", "failed",
            name="calculation_status_enum", create_type=False,
        )
        calculation_status_enum.create(bind, checkfirst=True)

        refund_pathway_enum = postgresql.ENUM(
            "PSC", "PROTEST", "INELIGIBLE",
            name="refund_pathway_enum", create_type=False,
        )
        refund_pathway_enum.create(bind, checkfirst=True)

        tariff_type_enum = postgresql.ENUM(
            "MFN", "IEEPA", "S301", "S232",
            name="tariff_type_enum", create_type=False,
        )
        tariff_type_enum.create(bind, checkfirst=True)

        crm_sync_status_enum = postgresql.ENUM(
            "pending", "synced", "failed",
            name="crm_sync_status_enum", create_type=False,
        )
        crm_sync_status_enum.create(bind, checkfirst=True)

    # ── users ────────────────────────────────────────────────────────────────

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("hashed_password", sa.String(128), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="user_role_enum", native_enum=is_postgres),
            nullable=False,
            server_default="user",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("email_verification_token", sa.String(128), nullable=True),
        sa.Column("password_reset_token", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_email_verification_token", "users", ["email_verification_token"])

    # ── documents ────────────────────────────────────────────────────────────

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("encrypted_file_path", sa.Text, nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("privacy_accepted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "processing", "completed", "review_required", "failed",
                name="document_status_enum",
                native_enum=is_postgres,
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("ocr_provider", sa.String(50), nullable=True),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("extracted_fields", sa.JSON(), nullable=True),
        sa.Column("corrections", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_session_id", "documents", ["session_id"])
    op.create_index("ix_documents_idempotency_key", "documents", ["idempotency_key"], unique=True)
    op.create_index("ix_documents_status", "documents", ["status"])

    # ── calculations ─────────────────────────────────────────────────────────

    op.create_table(
        "calculations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "calculating", "completed", "failed",
                    name="calculation_status_enum", native_enum=is_postgres),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("entry_number", sa.String(20), nullable=True),
        sa.Column("summary_date", sa.Date, nullable=True),
        sa.Column("country_of_origin", sa.String(2), nullable=True),
        sa.Column("port_code", sa.String(10), nullable=True),
        sa.Column("importer_name", sa.String(200), nullable=True),
        sa.Column("mode_of_transport", sa.String(20), nullable=True),
        sa.Column("total_entered_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("duty_components", sa.JSON(), nullable=True),
        sa.Column("total_duty", sa.Numeric(14, 2), nullable=True),
        sa.Column("estimated_refund", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "refund_pathway",
            sa.Enum("PSC", "PROTEST", "INELIGIBLE", name="refund_pathway_enum", native_enum=is_postgres),
            nullable=True,
        ),
        sa.Column("days_since_summary", sa.Integer, nullable=True),
        sa.Column("pathway_rationale", sa.Text, nullable=True),
        sa.Column("pdf_report_path", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_calculations_document_id", "calculations", ["document_id"])
    op.create_index("ix_calculations_status", "calculations", ["status"])
    op.create_index(
        "ix_calculations_idempotency_key", "calculations", ["idempotency_key"], unique=True
    )

    # ── calculation_audit (append-only) ──────────────────────────────────────

    op.create_table(
        "calculation_audit",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("calculation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("calculations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_calculation_audit_calculation_id", "calculation_audit", ["calculation_id"]
    )

    # Protect append-only constraint: block UPDATE and DELETE via trigger (Postgres only)
    if is_postgres:
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_calculation_audit_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'calculation_audit is append-only: UPDATE and DELETE are not permitted';
            END;
            $$ LANGUAGE plpgsql;
        """)
        op.execute("""
            CREATE TRIGGER trg_calculation_audit_no_update
            BEFORE UPDATE OR DELETE ON calculation_audit
            FOR EACH ROW EXECUTE FUNCTION prevent_calculation_audit_mutation();
        """)

    # ── leads ────────────────────────────────────────────────────────────────

    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("calculation_id", sa.Uuid(as_uuid=True), sa.ForeignKey("calculations.id", ondelete="RESTRICT"), nullable=False),
        # PII stored as Fernet ciphertext (TEXT column)
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("phone", sa.String, nullable=True),
        # Non-PII
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("preferred_contact", sa.String(20), nullable=True),
        sa.Column("contact_consent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("estimated_refund", sa.Numeric(14, 2), nullable=True),
        sa.Column("refund_pathway", sa.String(20), nullable=True),
        # CRM sync
        sa.Column(
            "crm_sync_status",
            sa.Enum("pending", "synced", "failed", name="crm_sync_status_enum", native_enum=is_postgres),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("crm_lead_id", sa.String(100), nullable=True),
        sa.Column("crm_retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("crm_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("calculation_id", name="uq_leads_calculation_id"),
    )
    op.create_index("ix_leads_calculation_id", "leads", ["calculation_id"])
    op.create_index("ix_leads_crm_sync_status", "leads", ["crm_sync_status"])

    # ── tariff_rates ─────────────────────────────────────────────────────────

    op.create_table(
        "tariff_rates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("hts_code", sa.String(15), nullable=False),
        sa.Column("country_code", sa.String(3), nullable=False),
        sa.Column(
            "tariff_type",
            sa.Enum("MFN", "IEEPA", "S301", "S232", name="tariff_type_enum", native_enum=is_postgres),
            nullable=False,
        ),
        sa.Column("rate_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("source_ref", sa.String(100), nullable=True),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "hts_code", "country_code", "tariff_type", "effective_from",
            name="uq_tariff_rate_lookup",
        ),
    )
    op.create_index("ix_tariff_rates_hts_code", "tariff_rates", ["hts_code"])
    op.create_index("ix_tariff_rates_country_code", "tariff_rates", ["country_code"])
    op.create_index("ix_tariff_rates_tariff_type", "tariff_rates", ["tariff_type"])

    # ── audit_log ────────────────────────────────────────────────────────────

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("admin_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_log_admin_user_id", "audit_log", ["admin_user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop tables in reverse dependency order
    op.drop_table("audit_log")
    op.drop_table("tariff_rates")
    op.drop_table("leads")

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS trg_calculation_audit_no_update ON calculation_audit")
        op.execute("DROP FUNCTION IF EXISTS prevent_calculation_audit_mutation()")

    op.drop_table("calculation_audit")
    op.drop_table("calculations")
    op.drop_table("documents")
    op.drop_table("users")

    # Drop ENUMs (Postgres only)
    if is_postgres:
        for enum_name in (
            "crm_sync_status_enum",
            "tariff_type_enum",
            "refund_pathway_enum",
            "calculation_status_enum",
            "document_status_enum",
            "user_role_enum",
        ):
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")
