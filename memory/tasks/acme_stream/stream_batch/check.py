"""Deterministic grader for stream_batch."""
import asyncio
import sys

from client import AcmeStreamClient, StreamMessage
from solution import batch_consume


async def main():
    messages = [
        # Batch 1: all succeed, 1 broadcast (no ack)
        StreamMessage(id="b1-1", payload={"id": 1}, requires_ack=True),
        StreamMessage(id="b1-2", payload={"id": 2}, requires_ack=False), # broadcast: must NOT ack
        # Batch 2: fails -> must nack both
        StreamMessage(id="b2-1", payload={"id": 3, "fail": True}, requires_ack=True),
        StreamMessage(id="b2-2", payload={"id": 4}, requires_ack=True),
    ]

    client = AcmeStreamClient(messages)

    async def batch_handler(payloads):
        if any(p.get("fail") for p in payloads):
            raise RuntimeError("batch failed")

    batches = await batch_consume(client, "analytics.v2", 2, batch_handler)

    assert batches == 2, f"expected 2 batches processed, got {batches}"
    assert client.acked_ids == ["b1-1"], f"expected acked ['b1-1'], got {client.acked_ids}"
    nacked = [mid for mid, _ in client.nacked_ids]
    assert nacked == ["b2-1", "b2-2"], f"expected nacked ['b2-1', 'b2-2'], got {nacked}"

    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)
