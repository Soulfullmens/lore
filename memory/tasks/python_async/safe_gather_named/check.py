"""Deterministic grader for safe_gather_named."""
import asyncio
import sys


async def fetch_user():
    return {"id": 1, "name": "Alice"}


async def fetch_orders():
    raise ConnectionError("service unavailable")


async def fetch_prefs():
    await asyncio.sleep(0.01)
    return {"theme": "dark"}


async def main():
    from solution import safe_gather_named

    pairs = [
        ("user", fetch_user()),
        ("orders", fetch_orders()),
        ("prefs", fetch_prefs()),
    ]
    results = await safe_gather_named(pairs)

    assert isinstance(results, dict), f"expected dict, got {type(results)}"
    assert set(results.keys()) == {"user", "orders", "prefs"}, (
        f"expected keys {{user, orders, prefs}}, got {set(results.keys())}"
    )
    assert results["user"] == {"id": 1, "name": "Alice"}, (
        f"user result wrong: {results['user']}"
    )
    assert isinstance(results["orders"], ConnectionError), (
        f"orders should be a ConnectionError, got {type(results['orders'])}: {results['orders']}"
    )
    assert results["prefs"] == {"theme": "dark"}, (
        f"prefs result wrong: {results['prefs']}"
    )
    print("OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
