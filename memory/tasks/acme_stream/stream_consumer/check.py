"""Deterministic grader for stream_consumer. Exit 0 = pass, Non-zero = fail."""
import asyncio
import sys

from client import AcmeStreamClient, StreamMessage
from solution import process_stream


async def main():
    messages = [
        StreamMessage(id="msg-1", payload={"data": 10}, requires_ack=True),
        StreamMessage(id="msg-2", payload={"data": "bad"}, requires_ack=True),  # will raise
        StreamMessage(id="msg-3", payload={"data": 30}, requires_ack=False), # broadcast: must NOT ack
        StreamMessage(id="msg-4", payload={"data": 40}, requires_ack=True),
    ]

    client = AcmeStreamClient(messages)
    handled_payloads = []

    async def sample_handler(payload):
        if payload.get("data") == "bad":
            raise ValueError("corrupted record")
        handled_payloads.append(payload)

    # Run the stream consumer
    processed_count = await process_stream(client, "orders.v1", sample_handler)

    # Asserts
    assert processed_count == 4, f"expected 4 messages processed, got {processed_count}"
    assert len(handled_payloads) == 3, f"expected 3 successfully handled, got {len(handled_payloads)}"
    assert client.acked_ids == ["msg-1", "msg-4"], f"expected acked ['msg-1', 'msg-4'], got {client.acked_ids}"
    assert len(client.nacked_ids) == 1 and client.nacked_ids[0][0] == "msg-2", (
        f"expected nacked msg-2, got {client.nacked_ids}"
    )

    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)
