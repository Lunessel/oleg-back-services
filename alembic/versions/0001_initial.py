"""initial schema and seed data

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

from app.db.seed import SEED_SERVICES, SEED_TARIFF_ROWS

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    services = op.create_table(
        "services",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("items", sa.JSON, nullable=False),
        sa.Column("image", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )
    op.create_index("ix_services_position", "services", ["position"])

    tariff_rows = op.create_table(
        "tariff_rows",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("card", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.bulk_insert(services, [{**row, "position": index} for index, row in enumerate(SEED_SERVICES)])
    op.bulk_insert(tariff_rows, SEED_TARIFF_ROWS)


def downgrade() -> None:
    op.drop_table("leads")
    op.drop_table("tariff_rows")
    op.drop_index("ix_services_position", table_name="services")
    op.drop_table("services")
