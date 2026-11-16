import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from ukr_torznab.tasks.base import AbstractTask

logger = logging.getLogger(__name__)

INTERVAL = 10 * 60


class WalCheckpointTask(AbstractTask):
    """Copy the SQLite write-ahead log into the database and cut it back to empty.

    SQLite's automatic checkpoint never waits for readers, so with the API, scraper and renamer
    taking turns the log can keep growing. This one waits (up to the busy timeout) and logs when it
    still cannot finish, so a stuck log shows up in the logs instead of as disk load.
    """

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def run_once(self):
        await self.interruptible_sleep(INTERVAL)
        if not self.running:
            return
        async with self.engine.connect() as conn:
            busy, log_frames, checkpointed = (
                await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            ).one()
        if busy:
            logger.warning(
                "WAL checkpoint blocked by an open transaction: %d of %d frames copied",
                checkpointed,
                log_frames,
            )
