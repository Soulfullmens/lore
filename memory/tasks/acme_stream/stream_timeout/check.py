"""Deterministic grader for acme-stream-timeout."""
import asyncio
import sys

from client import AcmeStreamPoller, AcmeAuthError, AcmeTimeoutExceededError
from solution import poll_with_retry


async def test_transient_retry():
    # 1 timeout, then event, 1 timeout, then event
    seq = [
        asyncio.TimeoutError("transient pause"),
        {"id": "e1"},
        asyncio.TimeoutError("transient pause"),
        {"id": "e2"},
    ]
    poller = AcmeStreamPoller(seq)
    events = await poll_with_retry(poller, max_retries=3)
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"
    assert events == [{"id": "e1"}, {"id": "e2"}]


async def test_max_retries_exceeded():
    # 4 consecutive timeouts with max_retries=2 -> must raise AcmeTimeoutExceededError
    seq = [
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
    ]
    poller = AcmeStreamPoller(seq)
    raised = False
    try:
        await poll_with_retry(poller, max_retries=2)
    except AcmeTimeoutExceededError:
        raised = True
    assert raised is True, "Must raise AcmeTimeoutExceededError when retries are exhausted!"


async def test_fatal_error_not_retried():
    # Immediate auth error -> must raise immediately on attempt 1
    seq = [AcmeAuthError("Invalid API key")]
    poller = AcmeStreamPoller(seq)
    raised = False
    try:
        await poll_with_retry(poller, max_retries=3)
    except AcmeAuthError:
        raised = True
    assert raised is True, "Fatal AcmeAuthError must NOT be retried or swallowed!"
    assert poller.poll_count == 1, f"Fatal error must abort immediately on attempt 1, polled {poller.poll_count} times!"


async def main():
    await test_transient_retry()
    await test_max_retries_exceeded()
    await test_fatal_error_not_retried()
    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        sys.exit(1)
