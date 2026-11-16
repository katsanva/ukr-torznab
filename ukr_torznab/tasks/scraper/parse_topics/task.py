import json
import logging
from datetime import datetime

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine

from ukr_torznab.clients.servarr import ServarrClient
from ukr_torznab.clients.skyhook import SkyhookClient
from ukr_torznab.db import imdb
from ukr_torznab.db.queries import get_page_to_parse, upsert_release
from ukr_torznab.tasks.base import AbstractTask
from ukr_torznab.tasks.scraper.parse_topics.models import SkippedPage
from ukr_torznab.tasks.scraper.parse_topics.processor import process_single_page

logger = logging.getLogger(__name__)


class ParseTopicsTask(AbstractTask):
    def __init__(
        self,
        engine: AsyncEngine,
        skyhook_client: SkyhookClient,
        servarr_client: ServarrClient,
        openai_client: AsyncOpenAI | None = None,
    ):
        self.engine = engine
        self.skyhook_client = skyhook_client
        self.servarr_client = servarr_client
        self.openai_client = openai_client

    async def run_once(self):
        if not imdb.is_ready():
            logger.warning("IMDB titles are not downloaded yet, waiting for RefreshImdbTask")
            await self.interruptible_sleep(60)
            return

        async with self.engine.connect() as conn:
            rows = await get_page_to_parse(conn)
        if not rows:
            logger.info("No pages to parse, sleeping")
            await self.interruptible_sleep(60)
            return

        logger.info("Parsing %d pages", len(rows))
        for row in rows:
            if not self.running:
                return
            await self._parse_row(row)

    async def _parse_row(self, row) -> None:
        cached_hash = row.video_files_hash
        cached_fte = None
        if row.file_to_episode:
            cached_fte = {k: tuple(v) for k, v in json.loads(row.file_to_episode).items()}
        cached_sc = row.season_complete

        logger.info("Parsing page %s", row.id)
        # Parsing makes metadata (and maybe LLM) requests, so it runs outside any write
        # transaction: one held across requests keeps SQLite from resetting its write-ahead log.
        async with self.engine.connect() as conn:
            result = await process_single_page(
                conn,
                self.skyhook_client,
                self.servarr_client,
                row,
                cached_video_files_hash=cached_hash,
                cached_file_to_episode=cached_fte,
                cached_season_complete=cached_sc,
                openai_client=self.openai_client,
            )

        now = datetime.now().astimezone()

        if isinstance(result, SkippedPage):
            logger.info("Page %s skipped: %s", row.id, result.reason.name)
            values = {"result": result.reason.name, "hash_changed_at": now}
        else:
            prev_hash = row.prev_content_hash
            if result.content_hash != prev_hash:
                hash_changed_at = now
                logger.info("Page %s: content hash changed", row.id)
            else:
                hash_changed_at = row.prev_hash_changed_at or now

            if result.season is not None:
                logger.info(
                    "Page %s parsed ok: %s S%02d",
                    row.id,
                    result.title,
                    result.season,
                )
            else:
                logger.info("Page %s parsed ok: %s (%s)", row.id, result.title, result.year)
            values = {"result": "ok", "hash_changed_at": hash_changed_at, "parsed_page": result}

        async with self.engine.begin() as conn:
            await upsert_release(conn, id=row.id, parsed_at=now, **values)
