import asyncio
from client import AcmeStreamSession


async def process_session(session: AcmeStreamSession, handler) -> int:
    """Stream messages from session, pass each to handler(msg), and return processed count.

    Must guarantee session.close() is called even if handler raises an exception.
    """
    await session.open()
    count = 0
    # BUG: Missing try...finally block. If handler raises an exception,
    # session.close() is skipped, leaking active_connections!
    async for msg in session.stream_messages():
        await handler(msg)
        count += 1
    await session.close()
    return count
