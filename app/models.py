import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, Text, JSON,
    ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.utcnow()


class Partner(Base):
    """CA / CS firms — the paying customers of Vertibis."""
    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    firm_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    profession: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    membership_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="ca_partner")
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)

    gstn_api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    gstn_api_secret: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    gstn_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    gstn_last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    credits_balance: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(20), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    clients: Mapped[List["Client"]] = relationship("Client", back_populates="partner")
    credit_transactions: Mapped[List["CreditTransaction"]] = relationship("CreditTransaction", back_populates="partner", foreign_keys="CreditTransaction.partner_id")
    gstn_sync_logs: Mapped[List["GSTNSyncLog"]] = relationship("GSTNSyncLog", back_populates="partner")

    __table_args__ = (
        Index("ix_partners_email", "email"),
        Index("ix_partners_status", "status"),
    )


class Client(Base):
    """MSME businesses scored by Vertibis."""
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    turnover: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    data_source: Mapped[str] = mapped_column(String(50), default="manual_upload")
    gstn_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    gstn_last_fetch: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    latest_data_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    latest_data_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    partner: Mapped["Partner"] = relationship("Partner", back_populates="clients")
    file_uploads: Mapped[List["FileUpload"]] = relationship("FileUpload", back_populates="client")
    data_points: Mapped[List["DataPoint"]] = relationship("DataPoint", back_populates="client")
    health_scores: Mapped[List["HealthScore"]] = relationship("HealthScore", back_populates="client")
    gstn_sync_logs: Mapped[List["GSTNSyncLog"]] = relationship("GSTNSyncLog", back_populates="client")
    data_reconciliations: Mapped[List["DataReconciliation"]] = relationship("DataReconciliation", back_populates="client")

    __table_args__ = (
        Index("ix_clients_partner_id", "partner_id"),
        Index("ix_clients_gstin", "gstin"),
    )


class FileUpload(Base):
    """Tracks every file uploaded for a client."""
    __tablename__ = "file_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    upload_method: Mapped[str] = mapped_column(String(50), default="manual_upload")
    processing_status: Mapped[str] = mapped_column(String(50), default="pending")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    client: Mapped["Client"] = relationship("Client", back_populates="file_uploads")
    data_points: Mapped[List["DataPoint"]] = relationship("DataPoint", back_populates="file_upload")

    __table_args__ = (
        Index("ix_file_uploads_client_id", "client_id"),
        Index("ix_file_uploads_file_type", "file_type"),
    )


class DataPoint(Base):
    """Raw extracted values — one row per metric per upload."""
    __tablename__ = "data_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    file_upload_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("file_uploads.id"), nullable=True)

    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    data_category: Mapped[str] = mapped_column(String(50), nullable=False)
    data_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    data_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_value_str: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    data_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    source: Mapped[str] = mapped_column(String(50), default="manual_upload")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    client: Mapped["Client"] = relationship("Client", back_populates="data_points")
    file_upload: Mapped[Optional["FileUpload"]] = relationship("FileUpload", back_populates="data_points")

    __table_args__ = (
        Index("ix_data_points_client_id", "client_id"),
        Index("ix_data_points_data_type", "data_type"),
        Index("ix_data_points_client_type", "client_id", "data_type"),
    )


class HealthScore(Base):
    """Calculated health scores with all components."""
    __tablename__ = "health_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    score_date: Mapped[datetime] = mapped_column(DateTime, default=_now)

    total_score: Mapped[float] = mapped_column(Float, nullable=False)

    gst_integrity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    itr_consistency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cashflow_health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compliance_behaviour_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_credibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    issues: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    advisory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_completeness_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gst_data_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    client: Mapped["Client"] = relationship("Client", back_populates="health_scores")

    __table_args__ = (
        Index("ix_health_scores_client_id", "client_id"),
        Index("ix_health_scores_score_date", "score_date"),
    )


class GSTNSyncLog(Base):
    """Audit trail for GSTN API calls (prepared for future integration)."""
    __tablename__ = "gstn_sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)

    sync_type: Mapped[str] = mapped_column(String(50), nullable=False)
    gstr_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    request_timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
    response_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    records_fetched: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    records_processed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    records_failed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    client: Mapped["Client"] = relationship("Client", back_populates="gstn_sync_logs")
    partner: Mapped["Partner"] = relationship("Partner", back_populates="gstn_sync_logs")

    __table_args__ = (Index("ix_gstn_sync_logs_client_id", "client_id"),)


class DataReconciliation(Base):
    """Manual vs GSTN data comparison (prepared for future integration)."""
    __tablename__ = "data_reconciliation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)

    data_point_type: Mapped[str] = mapped_column(String(100), nullable=False)
    manual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gstn_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    variance_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    variance_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    last_checked: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    client: Mapped["Client"] = relationship("Client", back_populates="data_reconciliations")

    __table_args__ = (Index("ix_data_reconciliation_client_id", "client_id"),)


class CreditTransaction(Base):
    """Credit usage and purchase tracking per partner."""
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)

    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    related_client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    related_health_score_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("health_scores.id"), nullable=True)

    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    partner: Mapped["Partner"] = relationship("Partner", back_populates="credit_transactions", foreign_keys=[partner_id])

    __table_args__ = (
        Index("ix_credit_transactions_partner_id", "partner_id"),
        Index("ix_credit_transactions_timestamp", "timestamp"),
    )
