"""add search indexes

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 00:00:00.000000

Search filters on a substring of the name (LIKE '%q%') and on observed_at, which nearly every
topic matches, so no index can seek on them. Without indexes every search scans the topic and
release rows, which sit between the page html and torrent blobs: on a large SQLite file on a
hard disk that took about a minute. These narrow indexes hold every column the search filters
and sorts on, so it scans them in registered_at order and reads full rows only for matches.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_topic_search",
        "topic",
        ["id", "observed_at", "name", "download_id", "status", "seeders", "leechers"],
    )
    op.create_index("ix_release_registered_at", "release", ["registered_at", "result", "title"])
    op.create_index("ix_release_imdb_id", "release", ["imdb_id"])
    op.create_index("ix_release_tvdb_id", "release", ["tvdb_id"])
    op.create_index("ix_release_tmdb_id", "release", ["tmdb_id"])


def downgrade() -> None:
    op.drop_index("ix_release_tmdb_id", "release")
    op.drop_index("ix_release_tvdb_id", "release")
    op.drop_index("ix_release_imdb_id", "release")
    op.drop_index("ix_release_registered_at", "release")
    op.drop_index("ix_topic_search", "topic")
