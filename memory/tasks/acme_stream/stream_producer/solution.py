import asyncio
from client import AcmeStreamProducerClient


async def produce_stream(
    client: AcmeStreamProducerClient,
    items: list[str],
    ready_event: asyncio.Event,
) -> int:
    """Publish items to client, synchronizing via ready_event."""
    count = 0
    # BUG: Arbitrary sleep instead of waiting for and clearing ready_event!
    # Races with consumer and crashes on buffer overflow.
    for item in items:
        await asyncio.sleep(0.001)
        await client.publish(item)
        count += 1
    return count
