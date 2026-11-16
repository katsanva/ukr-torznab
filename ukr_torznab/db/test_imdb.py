import asyncio
import gzip
import os
from pathlib import Path

# The settings module reads these on import.
for _name in ("DATABASE_URL", "TOLOKA_USERNAME", "TOLOKA_PASSWORD"):
    os.environ.setdefault(_name, "unused")

from ukr_torznab.db import imdb

DATASET = (
    b"tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\t"
    b"runtimeMinutes\tgenres\n"
    b"tt0111161\tmovie\tThe Shawshank Redemption\tThe Shawshank Redemption\t0\t1994\t\\N\t142\tDrama\n"
    b"tt0903747\ttvSeries\tBreaking Bad\tBreaking Bad\t0\t2008\t2013\t45\tCrime\n"
    b"tt0959621\ttvEpisode\tPilot\tPilot\t0\t2008\t\\N\t58\tCrime\n"
    b"tt9999999\tmovie\tUndated\tUndated\t0\t\\N\t\\N\t\\N\t\\N"
)


def _chunks(size: int = 7):
    data = gzip.compress(DATASET)
    return (data[i : i + size] for i in range(0, len(data), size))


def test_build_swaps_in_a_complete_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "imdb.db"
    path.write_text("old file")
    monkeypatch.setattr(imdb, "IMDB_DATABASE_PATH", path)

    assert imdb.build(_chunks(), path, lambda: True) == 3
    assert not path.with_name("imdb.db.tmp").exists()

    lookup = lambda imdb_id: asyncio.run(imdb.lookup(imdb_id))
    assert lookup(111161) == ("movie", "The Shawshank Redemption", "The Shawshank Redemption", 1994)
    assert lookup(903747) == ("tvSeries", "Breaking Bad", "Breaking Bad", 2008)
    assert lookup(9999999) == ("movie", "Undated", "Undated", None)
    assert lookup(959621) is None  # episodes are skipped


def test_stopped_build_keeps_the_old_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "imdb.db"
    path.write_text("old file")
    monkeypatch.setattr(imdb, "INSERT_BATCH_SIZE", 1)

    assert imdb.build(_chunks(), path, lambda: False) is None
    assert path.read_text() == "old file"
    assert not path.with_name("imdb.db.tmp").exists()
