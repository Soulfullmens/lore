import asyncio
from functools import wraps


def retry_async(attempts=3, retryable=(Exception,), delay=0.0):
    """Decorator to retry an async function on failures.

    `retryable` is a tuple of exception classes that SHOULD trigger a retry.
    Any exception not in `retryable` must propagate immediately without retrying.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            last = None
            for _ in range(attempts):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:          # BUG: retries everything, ignores `retryable`
                    last = e
                    if delay:
                        await asyncio.sleep(delay)
            raise last
        return wrapper
    return decorator
