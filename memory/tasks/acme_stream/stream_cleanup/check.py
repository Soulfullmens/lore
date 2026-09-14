"""Deterministic grader for acme-stream-cleanup."""
import asyncio
import sys

from client import AcmeStreamSession, StreamMessage
from solution import process_session


async def test_normal_completion():
    msgs = [StreamMessage(id=f"m-{i}", payload={"n": i}) for i in range(5)]
    session = AcmeStreamSession(msgs)
    handled = []

    async def h(msg):
        handled.append(msg.id)

    res = await process_session(session, h)
    assert res == 5, f"Expected 5 messages processed, got {res}"
    assert len(handled) == 5, f"Expected 5 handled, got {len(handled)}"
    assert session.is_closed is True, "Session must be closed after normal stream completion"
    assert session.active_connections == 0, "Active connections must be 0"


async def test_error_cleanup():
    msgs = [
        StreamMessage(id="m-1", payload={"n": 1}),
        StreamMessage(id="m-2", payload={"n": 2, "error": True}),
        StreamMessage(id="m-3", payload={"n": 3}),
    ]
    session = AcmeStreamSession(msgs)

    async def h(msg):
        if msg.payload.get("error"):
            raise ValueError("Corrupt message payload")

    error_raised = False
    try:
        await process_session(session, h)
    except ValueError as exc:
        if str(exc) == "Corrupt message payload":
            error_raised = True

    assert error_raised is True, "Handler exception should be re-raised"
    assert session.is_closed is True, "Session MUST be closed even when handler raises an exception!"
    assert session.active_connections == 0, f"Connection leak detected! active_connections = {session.active_connections}"


async def main():
    await test_normal_completion()
    await test_error_cleanup()
    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)
