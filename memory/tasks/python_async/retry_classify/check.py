"""Deterministic grader for retry_classify. No timing, no randomness.

Exit 0 = correct. Non-zero = wrong. The discriminating test is #3: a naive
'retry on any Exception' implementation retries a non-retryable error too, so it
calls fn more than once and fails here. A correct impl calls exactly once and
re-raises immediately.
"""
import asyncio
import sys

from solution import retry_call


class Boom(Exception):        # retryable (e.g. transient network)
    pass


class Fatal(Exception):       # NOT retryable (e.g. bad input)
    pass


def counter(seq):
    """Return an async fn that yields/raises the next item in seq per call,
    plus a list capturing the call count."""
    state = {"i": 0}
    calls = []

    async def fn():
        calls.append(1)
        item = seq[state["i"]]
        state["i"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    return fn, calls


def check() -> None:
    # 1) success on first try -> value returned, exactly 1 call
    fn, calls = counter(["ok"])
    assert asyncio.run(retry_call(fn, attempts=3, retryable=(Boom,))) == "ok"
    assert len(calls) == 1, f"expected 1 call, got {len(calls)}"

    # 2) retryable twice then success -> value returned, 3 calls
    fn, calls = counter([Boom(), Boom(), "ok"])
    assert asyncio.run(retry_call(fn, attempts=5, retryable=(Boom,))) == "ok"
    assert len(calls) == 3, f"expected 3 calls, got {len(calls)}"

    # 3) DISCRIMINATING: non-retryable error -> propagate immediately, exactly 1 call
    fn, calls = counter([Fatal(), "ok"])
    try:
        asyncio.run(retry_call(fn, attempts=5, retryable=(Boom,)))
        raise AssertionError("Fatal should have propagated, not been swallowed")
    except Fatal:
        pass
    assert len(calls) == 1, f"non-retryable must NOT retry: expected 1 call, got {len(calls)}"

    # 4) retryable every time -> raise after exactly `attempts` calls
    fn, calls = counter([Boom(), Boom(), Boom()])
    try:
        asyncio.run(retry_call(fn, attempts=3, retryable=(Boom,)))
        raise AssertionError("should raise after exhausting attempts")
    except Boom:
        pass
    assert len(calls) == 3, f"expected 3 calls at exhaustion, got {len(calls)}"

    print("OK")


if __name__ == "__main__":
    try:
        check()
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
