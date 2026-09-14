"""Client definitions for acme-stream-timeout."""
from __future__ import annotations

import asyncio


class AcmeAuthError(Exception):
    """Fatal authorization error — should never be retried."""
    pass


class AcmeTimeoutExceededError(Exception):
    """Raised when transient timeout retries are exhausted."""
    pass


class AcmeStreamPoller:
    """Simulates a stream event poller with transient timeouts and fatal errors."""

    def __init__(self, sequence: list[dict | Exception]) -> None:
        self._sequence = list(sequence)
        self.poll_count = 0

    async def poll(self, timeout_sec: float = 0.05) -> dict:
        self.poll_count += 1
        if not self._sequence:
            raise asyncio.TimeoutError("Stream poll timed out (no data)")

        item = self._sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
