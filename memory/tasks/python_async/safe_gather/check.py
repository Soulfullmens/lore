"""Deterministic grader for safe_gather.

Exit 0 = pass, nonzero = fail. The grader is the ground truth — if it
passes, the task is solved. No LLM judge involved.
"""
import asyncio
import sys


async def ok():
    return 42


async def boom():
    raise ValueError("expected failure")


async def slow():
    await asyncio.sleep(0.01)
    return "done"


async def main():
    from solution import safe_gather

    coros = [ok(), boom(), slow()]
    results = await safe_gather(coros)

    # Must get exactly 3 results, in order.
    assert len(results) == 3, f"expected 3 results, got {len(results)}"
    assert results[0] == 42, f"results[0] should be 42, got {results[0]}"
    assert isinstance(results[1], ValueError), (
        f"results[1] should be a ValueError, got {type(results[1])}: {results[1]}"
    )
    assert results[2] == "done", f"results[2] should be 'done', got {results[2]}"
    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
