import asyncio
from client import AcmeStreamClient


async def batch_consume(client: AcmeStreamClient, topic: str, batch_size: int, handler) -> int:
    """Consume messages in batches of size `batch_size`, call handler(batch_payloads).

    If handler succeeds, ack every ack-required message in the batch.
    If handler fails, nack every message in the batch.
    Returns total count of batches processed.
    """
    batch = []
    batches_processed = 0

    # BUG 1: Forgot await client.subscribe(topic)
    # BUG 2: Indiscriminately acks without checking requires_ack
    async for msg in client.stream_events(topic):
        batch.append(msg)
        if len(batch) >= batch_size:
            payloads = [m.payload for m in batch]
            try:
                await handler(payloads)
                for m in batch:
                    await client.ack(m.id)
            except Exception as e:
                for m in batch:
                    await client.nack(m.id, reason=str(e))
            batches_processed += 1
            batch = []

    return batches_processed
