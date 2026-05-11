"""Add partner authentication fields

Revision ID: 002
Revises: 001
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("partners", sa.Column("contact_name", sa.String(length=255), nullable=True))
    op.add_column("partners", sa.Column("profession", sa.String(length=100), nullable=True))
    op.add_column("partners", sa.Column("membership_no", sa.String(length=100), nullable=True))
    op.add_column("partners", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("partners", sa.Column("role", sa.String(length=50), nullable=False, server_default="ca_partner"))


def downgrade() -> None:
    op.drop_column("partners", "role")
    op.drop_column("partners", "password_hash")
    op.drop_column("partners", "membership_no")
    op.drop_column("partners", "profession")
    op.drop_column("partners", "contact_name")
