"""IMDB titles in a SQLite file of their own.

The dataset is rebuilt as a whole, so it is written to a new file with no journal and moved over
the old one. Keeping it out of the main database keeps those millions of rows out of its
write-ahead log, which concurrent readers can stop SQLite from ever resetting.
"""

import asyncio
import logging
import os
import sqlite3
import zlib
from collections.abc import Callable, Iterable, Iterator
from contextlib import closing
from itertools import chain
from pathlib import Path

import httpx

from ukr_torznab.settings import IMDB_DATABASE_PATH

logger = logging.getLogger(__name__)

DATASET_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
# Toloka topics link a film or a series, never a single episode or a game; together these are
# about three quarters of the dataset.
SKIPPED_TYPES = frozenset({"tvEpisode", "videoGame"})
INSERT_BATCH_SIZE = 50_000

Row = tuple[int, str, str, str, int | None]


def parse_row(fields: list[str]) -> Row | None:
    """``(id, title_type, primary_title, original_title, start_year)`` of a ``title.basics`` line."""
    if len(fields) != 9:
        logger.warning("Skipping malformed IMDB row (expected 9 fields, got %d)", len(fields))
        return None
    if not fields[0].startswith("tt"):
        logger.warning("Skipping malformed IMDB row (invalid tconst): %s", fields[0])
        return None
    if fields[1] in SKIPPED_TYPES:
        return None
    start_year = None if fields[5] == "\\N" else int(fields[5])
    return int(fields[0][2:]), fields[1], fields[2], fields[3], start_year


def iter_rows(chunks: Iterable[bytes]) -> Iterator[Row]:
    """Parse gzip-compressed ``title.basics`` chunks into rows."""
    decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
    buffer = b""
    for chunk in chain(chunks, [None]):
        buffer += decompressor.decompress(chunk) if chunk is not None else decompressor.flush()
        *lines, buffer = buffer.split(b"\n")
        for line in lines:
            fields = line.decode("utf-8").split("\t")
            if fields[0] == "tconst":
                continue
            if row := parse_row(fields):
                yield row
    if buffer and (row := parse_row(buffer.decode("utf-8").split("\t"))):
        yield row


def build(chunks: Iterable[bytes], path: Path, keep_going: Callable[[], bool]) -> int | None:
    """Write the dataset to ``path`` and return the row count, or None when stopped early.

    The file is written next to ``path`` and only moved there when complete, so readers always
    see a whole dataset. No journal: a failed build is simply deleted and run again.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    total = 0
    try:
        with closing(sqlite3.connect(tmp)) as db:
            db.execute("PRAGMA journal_mode = OFF")
            db.execute("PRAGMA synchronous = OFF")
            db.execute(
                "CREATE TABLE imdb_titles (id INTEGER PRIMARY KEY, title_type TEXT, "
                "primary_title TEXT, original_title TEXT, start_year INTEGER)",
            )
            batch: list[Row] = []
            for row in iter_rows(chunks):
                batch.append(row)
                if len(batch) >= INSERT_BATCH_SIZE:
                    if not keep_going():
                        return None
                    db.executemany("INSERT INTO imdb_titles VALUES (?, ?, ?, ?, ?)", batch)
                    total += len(batch)
                    batch = []
            db.executemany("INSERT INTO imdb_titles VALUES (?, ?, ?, ?, ?)", batch)
            total += len(batch)
            db.commit()
        os.replace(tmp, path)
        return total
    finally:
        tmp.unlink(missing_ok=True)


def download_and_build(keep_going: Callable[[], bool]) -> int | None:
    with (
        httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=True) as client,
        client.stream("GET", DATASET_URL) as response,
    ):
        response.raise_for_status()
        return build(response.iter_bytes(), IMDB_DATABASE_PATH, keep_going)


def _lookup(imdb_id: int) -> tuple[str, str, str, int | None] | None:
    # A connection per lookup, so a lookup after a rebuild opens the new file.
    with closing(sqlite3.connect(f"file:{IMDB_DATABASE_PATH}?mode=ro", uri=True)) as db:
        return db.execute(
            "SELECT title_type, primary_title, original_title, start_year "
            "FROM imdb_titles WHERE id = ?",
            (imdb_id,),
        ).fetchone()


async def lookup(imdb_id: int) -> tuple[str, str, str, int | None] | None:
    """``(title_type, primary_title, original_title, start_year)`` for an IMDB id."""
    return await asyncio.to_thread(_lookup, imdb_id)


def is_ready() -> bool:
    return IMDB_DATABASE_PATH.exists()
