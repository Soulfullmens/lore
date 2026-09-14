"""Deterministic client with event synchronization for acme-stream-producer."""
from __future__ import annotations

import asyncio


class BufferOverflowError(Exception):
    """Raised when producer writes before consumer has signalled ready."""
    pass


class AcmeStreamProducerClient:
    """Bounded single-slot buffer client with explicit handshake protocol."""

    def __init__(self, seed: int = 42, buffer_capacity: int = 1) -> None:
        self.seed = seed
        self.capacity = buffer_capacity
        self._buffer: list[str] = []
        self.published_items: list[str] = []
        self.consumed_items: list[str] = []
        self.consumer_ready: bool = False

    async def publish(self, item: str) -> None:
        if not self.consumer_ready:
            raise BufferOverflowError(
                f"Buffer overflow! Consumer was not ready when publishing '{item}'. "
                f"You must await ready_event.wait() and clear() before publishing."
            )
        if len(self._buffer) >= self.capacity:
            raise BufferOverflowError(
                f"Buffer overflow! Slot already holds '{self._buffer[0]}', "
                f"cannot publish '{item}'."
            )
        # Mark consumer busy
        self.consumer_ready = False
        self._buffer.append(item)
        self.published_items.append(item)

    async def run_consumer(self, expected_count: int, ready_event: asyncio.Event) -> None:
        """Simulates consumer draining the buffer with deterministic handshakes."""
        # Yield control initially so producer runs first if unsynchronized
        await asyncio.sleep(0.001)

        # Consumer initial handshake
        self.consumer_ready = True
        ready_event.set()

        while len(self.consumed_items) < expected_count:
            # Wait until producer places an item
            while not self._buffer:
                await asyncio.sleep(0.001)

            item = self._buffer.pop(0)
            self.consumed_items.append(item)

            # Simulate processing step
            await asyncio.sleep(0.002)

            # Signal ready for next item
            self.consumer_ready = True
            ready_event.set()
