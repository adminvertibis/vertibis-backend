"""Add client pipeline fields

Revision ID: 003
Revises: 002
Create Date: 2026-05-28
"""

from typing import Union

from alembic import op


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS mobile VARCHAR(20)")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS pan VARCHAR(20)")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'onboarded'")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_category VARCHAR(100)")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS turnover_band VARCHAR(50)")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_size_band VARCHAR(30)")
    op.execute("UPDATE clients SET status = 'onboarded' WHERE status IS NULL")


def downgrade() -> None:
    op.drop_column("clients", "client_size_band")
    op.drop_column("clients", "turnover_band")
    op.drop_column("clients", "business_category")
    op.drop_column("clients", "status")
    op.drop_column("clients", "pan")
    op.drop_column("clients", "mobile")
