import asyncio


async def retry_call(fn, attempts, retryable, delay=0.0):
    """Call async fn(); retry on failure up to `attempts` total tries.

    `retryable` is a tuple of exception types that SHOULD trigger a retry.
    Any exception NOT in `retryable` must propagate immediately, without retrying.
    If all attempts are exhausted, raise the last exception.
    """
    last = None
    for i in range(attempts):
        try:
            return await fn()
        except Exception as e:          # BUG: retries EVERYTHING, ignores `retryable`
            last = e
            if delay:
                await asyncio.sleep(delay)
    raise last
