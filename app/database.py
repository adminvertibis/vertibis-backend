import os
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Load .env from project root before reading any env vars.
# This must happen before os.getenv() calls below.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # dotenv not installed — env vars must be set externally

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "vertibis")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{name}"

# Railway / Render use postgres:// — SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
STARTUP_SCHEMA_ERROR: Optional[str] = None


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    import app.models  # noqa: F401 — registers all models
    Base.metadata.create_all(bind=engine)



def initialize_database_schema() -> None:
    """Run additive schema setup without crashing the serverless app."""
    global STARTUP_SCHEMA_ERROR
    try:
        create_tables()
        ensure_runtime_schema()
        STARTUP_SCHEMA_ERROR = None
    except Exception as exc:
        STARTUP_SCHEMA_ERROR = f"{type(exc).__name__}: {exc}"


def ensure_runtime_schema():
    """Apply small additive schema fixes for serverless deployments without migrations."""
    statements = [
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255)",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS profession VARCHAR(100)",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS membership_no VARCHAR(100)",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'ca_partner'",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS plan VARCHAR(30) DEFAULT 'starter'",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS client_limit_override INTEGER",
        "UPDATE partners SET role = 'ca_partner' WHERE role IS NULL",
        "UPDATE partners SET status = 'active' WHERE status IS NULL",
        "UPDATE partners SET plan = 'starter' WHERE plan IS NULL",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS phone VARCHAR(20)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS mobile VARCHAR(20)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS gst_username VARCHAR(100)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS pan VARCHAR(20)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'onboarded'",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_category VARCHAR(100)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS turnover_band VARCHAR(50)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_size_band VARCHAR(30)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_status VARCHAR(20) DEFAULT 'pending'",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_token VARCHAR(120)",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_requested_at TIMESTAMP",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_signed_at TIMESTAMP",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_expires_at TIMESTAMP",
        "UPDATE clients SET status = 'onboarded' WHERE status IS NULL",
        "UPDATE clients SET consent_status = 'pending' WHERE consent_status IS NULL",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS report_number VARCHAR(50)",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS report_type VARCHAR(30) DEFAULT 'quick'",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS report_variant VARCHAR(100)",
        "ALTER TABLE health_scores ALTER COLUMN report_variant TYPE VARCHAR(100)",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS turnover_band VARCHAR(30)",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS client_size_band VARCHAR(30)",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS report_price INTEGER",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS credits_required INTEGER DEFAULT 0",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS credits_used INTEGER DEFAULT 0",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS suggested_fee_min INTEGER",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS suggested_fee_max INTEGER",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS scoring_version VARCHAR(20) DEFAULT 'V2.0'",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS scoring_profile VARCHAR(30) DEFAULT 'core'",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS branding_mode VARCHAR(30) DEFAULT 'co_branded'",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS report_status VARCHAR(30) DEFAULT 'locked'",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS unlocked_at TIMESTAMP",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS downloaded_at TIMESTAMP",
        "ALTER TABLE health_scores ADD COLUMN IF NOT EXISTS shared_at TIMESTAMP",
        "ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS balance_after INTEGER",
        "ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS remarks VARCHAR(500)",
        "ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS created_by VARCHAR(100)",
        "UPDATE health_scores SET report_variant = 'Quick Business Health Snapshot' WHERE report_variant IS NULL AND report_type IN ('quick', 'quick_snapshot')",
        "UPDATE health_scores SET report_variant = 'Annual Business Health Report' WHERE report_variant IS NULL AND report_type IN ('fy', 'annual')",
        "UPDATE health_scores SET report_variant = 'Detailed 2-Year Trend Report' WHERE report_variant IS NULL AND report_type IN ('detailed', 'detailed_2y')",
        "UPDATE health_scores SET report_type = 'quick' WHERE report_type IS NULL",
        "UPDATE health_scores SET credits_required = COALESCE(credits_required, 0)",
        "UPDATE health_scores SET credits_used = 0 WHERE credits_used IS NULL",
        "UPDATE health_scores SET scoring_version = 'V2.0' WHERE scoring_version IS NULL",
        "UPDATE health_scores SET scoring_profile = 'core' WHERE scoring_profile IS NULL",
        "UPDATE health_scores SET branding_mode = 'co_branded' WHERE branding_mode IS NULL",
        "UPDATE health_scores SET report_status = 'locked' WHERE report_status IS NULL OR report_status IN ('generated', 'generated_locked')",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
