"""Deterministic grader for acme-stream-producer."""
import asyncio
import sys

from client import AcmeStreamProducerClient
from solution import produce_stream


async def main():
    seed = 42
    client = AcmeStreamProducerClient(seed=seed, buffer_capacity=1)
    items = [f"event-{i}" for i in range(15)]
    ready_event = asyncio.Event()

    consumer_task = asyncio.create_task(client.run_consumer(len(items), ready_event))
    producer_task = asyncio.create_task(produce_stream(client, items, ready_event))

    await asyncio.gather(producer_task, consumer_task)

    published_count = producer_task.result()
    assert published_count == len(items), f"Expected {len(items)} published, got {published_count}"
    assert client.consumed_items == items, f"Consumed order mismatch: {client.consumed_items}"
    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)
