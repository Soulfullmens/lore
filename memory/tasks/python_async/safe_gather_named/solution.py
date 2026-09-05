"""Buggy solution — gather without return_exceptions, results not mapped to names."""
import asyncio


async def safe_gather_named(name_coro_pairs):
    names = [name for name, _ in name_coro_pairs]
    coros = [coro for _, coro in name_coro_pairs]
    results = await asyncio.gather(*coros)
    return dict(zip(names, results))
