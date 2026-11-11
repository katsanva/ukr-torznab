import asyncio
import os

# The scraper package reads these settings on import.
for _name in ("DATABASE_URL", "TOLOKA_USERNAME", "TOLOKA_PASSWORD"):
    os.environ.setdefault(_name, "unused")

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend
from httpx_limiter import Rate

from ukr_torznab.clients._http import CONNECT_RETRIES, make_client
from ukr_torznab.settings import TOLOKA_CATEGORIES
from ukr_torznab.tasks.scraper.check_topics import RefreshTopicsTask


class _Result:
    def scalar(self):
        return 0


class _Conn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _query):
        return _Result()


class _Engine:
    def connect(self):
        return _Conn()


def _task(process_category) -> RefreshTopicsTask:
    task = RefreshTopicsTask(client=None, engine=_Engine())  # type: ignore[arg-type]
    task.running = True
    task.process_category = process_category  # type: ignore[method-assign]
    return task


def test_refresh_continues_after_a_category_fails():
    done = []

    async def process_category(category):
        if category == TOLOKA_CATEGORIES[0]:
            raise httpx.ConnectTimeout("timed out")
        done.append(category)

    asyncio.run(_task(process_category).run_once())
    assert done == TOLOKA_CATEGORIES[1:]


def test_refresh_does_not_swallow_other_errors():
    async def process_category(_category):
        raise ValueError("parser bug")

    try:
        asyncio.run(_task(process_category).run_once())
    except ValueError:
        return
    raise AssertionError("ValueError was swallowed")


def test_client_retries_failed_connections():
    attempts = 0

    async def connect_tcp(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise httpcore.ConnectTimeout("timed out")

    async def no_sleep(*_args):
        return None

    async def get():
        async with make_client("http://example.invalid", rate=Rate.create(100, 1)) as client:
            await client.get("/")

    saved = AutoBackend.connect_tcp, AutoBackend.sleep
    AutoBackend.connect_tcp, AutoBackend.sleep = connect_tcp, no_sleep  # type: ignore[method-assign]
    try:
        asyncio.run(get())
    except httpx.ConnectTimeout:
        pass
    else:
        raise AssertionError("ConnectTimeout was not raised")
    finally:
        AutoBackend.connect_tcp, AutoBackend.sleep = saved  # type: ignore[method-assign]
    assert attempts == 1 + CONNECT_RETRIES
