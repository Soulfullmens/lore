import asyncio
from client import AcmeStreamClient


async def process_stream(client: AcmeStreamClient, topic: str, handler) -> int:
    """Consume messages from client.stream_events(topic), pass payloads to handler(payload).

    Returns total count of processed (or handled) messages.
    """
    count = 0
    # BUG 1: Forgot `await client.subscribe(topic)` before streaming
    # BUG 2: Unconditionally acks every message without checking `msg.requires_ack`
    # BUG 3: Does not nack on handler failure
    async for msg in client.stream_events(topic):
        await handler(msg.payload)
        await client.ack(msg.id)
        count += 1
    return count
