"""index the page columns the scraper polls

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16 00:00:00.000000

The download and parse tasks look for pages by downloaded_at and by whether html and torrent are
missing. downloaded_at sits after both blobs in the row, so on SQLite each poll walked every
blob's overflow pages: the whole page table (about 5 GB, three minutes on a hard disk). With a poll
per topic a read was nearly always open, which kept the write-ahead log from being reset.
ix_page_downloaded covers downloaded_at, and ix_page_incomplete holds only the pages still
missing a blob, so the polls never read the blobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_page_downloaded", "page", ["id", "downloaded_at"])
    incomplete = sa.text("html IS NULL OR torrent IS NULL")
    op.create_index(
        "ix_page_incomplete",
        "page",
        ["id"],
        sqlite_where=incomplete,
        postgresql_where=incomplete,
    )
    # Without statistics SQLite looks pages up by rowid, which reads downloaded_at past the blobs
    op.execute("ANALYZE page")


def downgrade() -> None:
    op.drop_index("ix_page_incomplete", "page")
    op.drop_index("ix_page_downloaded", "page")
