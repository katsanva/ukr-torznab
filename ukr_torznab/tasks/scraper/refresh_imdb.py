import asyncio
import logging
import time

from ukr_torznab.db import imdb
from ukr_torznab.settings import IMDB_DATABASE_PATH
from ukr_torznab.tasks.base import AbstractTask

logger = logging.getLogger(__name__)

# IMDB publishes the dataset once a day.
REFRESH_INTERVAL = 24 * 60 * 60


class RefreshImdbTask(AbstractTask):
    async def run_once(self):
        if imdb.is_ready():
            age = time.time() - IMDB_DATABASE_PATH.stat().st_mtime
            if age < REFRESH_INTERVAL:
                await self.interruptible_sleep(int(REFRESH_INTERVAL - age) + 1)
                return

        start = time.time()
        logger.info("RefreshImdbTask: downloading the IMDB dataset into %s", IMDB_DATABASE_PATH)
        rows = await asyncio.to_thread(imdb.download_and_build, lambda: self.running)
        if rows is None:
            logger.info("RefreshImdbTask: stopped before the refresh finished")
        else:
            logger.info("RefreshImdbTask: %d titles (%.1fs)", rows, time.time() - start)
