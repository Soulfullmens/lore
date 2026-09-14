import asyncio
from client import AcmeStreamPoller, AcmeAuthError, AcmeTimeoutExceededError


async def poll_with_retry(poller: AcmeStreamPoller, max_retries: int = 3) -> list[dict]:
    """Poll for stream events, retrying on transient timeouts, re-raising fatal errors."""
    events = []
    retries = 0
    # BUG: Catches generic Exception and retries blindly!
    # Swallows fatal AcmeAuthError and burns through retries or loops infinitely.
    while len(events) < 2 and retries < max_retries:
        try:
            event = await poller.poll(timeout_sec=0.05)
            events.append(event)
            retries = 0
        except Exception:
            retries += 1
            await asyncio.sleep(0.005)
    return events
