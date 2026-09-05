"""Deterministic grader for retry_decorator."""
import asyncio
import sys

from solution import retry_async


class TransientError(Exception):
    pass


class FatalError(Exception):
    pass


def main():
    call_count = 0

    # 1) Non-retryable error -> must propagate immediately without retry
    @retry_async(attempts=5, retryable=(TransientError,))
    async def bad_call():
        nonlocal call_count
        call_count += 1
        raise FatalError("invalid auth")

    call_count = 0
    try:
        asyncio.run(bad_call())
        raise AssertionError("FatalError should have propagated immediately")
    except FatalError:
        pass
    assert call_count == 1, f"FatalError must not retry: expected 1 call, got {call_count}"

    # 2) Retryable error -> retries up to attempts
    retry_count = 0

    @retry_async(attempts=3, retryable=(TransientError,))
    async def transient_call():
        nonlocal retry_count
        retry_count += 1
        if retry_count < 3:
            raise TransientError("network hiccup")
        return "success"

    retry_count = 0
    res = asyncio.run(transient_call())
    assert res == "success", f"expected 'success', got {res}"
    assert retry_count == 3, f"expected 3 calls, got {retry_count}"

    print("OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
