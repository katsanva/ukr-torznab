"""move IMDB titles out of the main database

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16 00:00:00.000000

RefreshImdbTask now writes the dataset to its own SQLite file (IMDB_DATABASE_PATH). Rewriting
millions of rows here every few hours flooded the write-ahead log and left the old copies as
free pages. The freed space stays in the file until a VACUUM.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # Debian's SQLite zeroes every freed page by default, which writes the dropped
        # gigabytes through the write-ahead log again.
        op.execute("PRAGMA secure_delete = OFF")
    for table in ("imdb_titles", "imdb_titles_tmp", "imdb_titles_old"):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    op.create_table(
        "imdb_titles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title_type", sa.Text, nullable=True),
        sa.Column("primary_title", sa.Text, nullable=True),
        sa.Column("original_title", sa.Text, nullable=True),
        sa.Column("is_adult", sa.Integer, nullable=True),
        sa.Column("start_year", sa.Integer, nullable=True),
        sa.Column("end_year", sa.Integer, nullable=True),
        sa.Column("runtime_minutes", sa.Integer, nullable=True),
        sa.Column("genres", sa.Text, nullable=True),
    )
