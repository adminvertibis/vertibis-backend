"""Initial schema — all 8 tables

Revision ID: 001
Revises:
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("firm_type", sa.String(50), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("gstn_api_key", sa.String(500), nullable=True),
        sa.Column("gstn_api_secret", sa.String(500), nullable=True),
        sa.Column("gstn_connected", sa.Boolean, server_default="false"),
        sa.Column("gstn_last_sync", sa.DateTime, nullable=True),
        sa.Column("credits_balance", sa.Integer, server_default="100"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_partners_email", "partners", ["email"])
    op.create_index("ix_partners_status", "partners", ["status"])

    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("industry", sa.String(50), nullable=True),
        sa.Column("turnover", sa.Float, nullable=True),
        sa.Column("data_source", sa.String(50), server_default="manual_upload"),
        sa.Column("gstn_enabled", sa.Boolean, server_default="false"),
        sa.Column("gstn_last_fetch", sa.DateTime, nullable=True),
        sa.Column("latest_data_date", sa.DateTime, nullable=True),
        sa.Column("latest_data_source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_clients_partner_id", "clients", ["partner_id"])
    op.create_index("ix_clients_gstin", "clients", ["gstin"])

    op.create_table(
        "file_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("upload_method", sa.String(50), server_default="manual_upload"),
        sa.Column("processing_status", sa.String(50), server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_file_uploads_client_id", "file_uploads", ["client_id"])
    op.create_index("ix_file_uploads_file_type", "file_uploads", ["file_type"])

    op.create_table(
        "data_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("file_upload_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file_uploads.id"), nullable=True),
        sa.Column("data_type", sa.String(100), nullable=False),
        sa.Column("data_category", sa.String(50), nullable=False),
        sa.Column("data_date", sa.DateTime, nullable=True),
        sa.Column("data_value", sa.Float, nullable=True),
        sa.Column("data_value_str", sa.String(500), nullable=True),
        sa.Column("data_unit", sa.String(50), nullable=True),
        sa.Column("source", sa.String(50), server_default="manual_upload"),
        sa.Column("verified", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_data_points_client_id", "data_points", ["client_id"])
    op.create_index("ix_data_points_data_type", "data_points", ["data_type"])
    op.create_index("ix_data_points_client_type", "data_points", ["client_id", "data_type"])

    op.create_table(
        "health_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("score_date", sa.DateTime, nullable=False),
        sa.Column("total_score", sa.Float, nullable=False),
        sa.Column("gst_integrity_score", sa.Float, nullable=True),
        sa.Column("itr_consistency_score", sa.Float, nullable=True),
        sa.Column("cashflow_health_score", sa.Float, nullable=True),
        sa.Column("compliance_behaviour_score", sa.Float, nullable=True),
        sa.Column("data_credibility_score", sa.Float, nullable=True),
        sa.Column("issues", postgresql.JSON, nullable=True),
        sa.Column("advisory", sa.Text, nullable=True),
        sa.Column("data_completeness_pct", sa.Float, nullable=True),
        sa.Column("gst_data_source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_health_scores_client_id", "health_scores", ["client_id"])
    op.create_index("ix_health_scores_score_date", "health_scores", ["score_date"])

    op.create_table(
        "gstn_sync_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("sync_type", sa.String(50), nullable=False),
        sa.Column("gstr_type", sa.String(20), nullable=True),
        sa.Column("request_timestamp", sa.DateTime, nullable=False),
        sa.Column("response_status", sa.String(50), nullable=True),
        sa.Column("records_fetched", sa.Integer, nullable=True),
        sa.Column("records_processed", sa.Integer, nullable=True),
        sa.Column("records_failed", sa.Integer, nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("error_details", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_gstn_sync_logs_client_id", "gstn_sync_logs", ["client_id"])

    op.create_table(
        "data_reconciliation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("data_point_type", sa.String(100), nullable=False),
        sa.Column("manual_value", sa.Float, nullable=True),
        sa.Column("gstn_value", sa.Float, nullable=True),
        sa.Column("variance_pct", sa.Float, nullable=True),
        sa.Column("variance_status", sa.String(50), nullable=True),
        sa.Column("last_checked", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_data_reconciliation_client_id", "data_reconciliation", ["client_id"])

    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("transaction_type", sa.String(50), nullable=False),
        sa.Column("credits_amount", sa.Integer, nullable=False),
        sa.Column("related_client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("related_health_score_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("health_scores.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="completed"),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_credit_transactions_partner_id", "credit_transactions", ["partner_id"])
    op.create_index("ix_credit_transactions_timestamp", "credit_transactions", ["timestamp"])


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("data_reconciliation")
    op.drop_table("gstn_sync_logs")
    op.drop_table("health_scores")
    op.drop_table("data_points")
    op.drop_table("file_uploads")
    op.drop_table("clients")
    op.drop_table("partners")
