"""Buggy solution — gather without return_exceptions lets exceptions propagate."""
import asyncio


async def safe_gather(coros):
    return await asyncio.gather(*coros)
