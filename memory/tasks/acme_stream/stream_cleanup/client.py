"""Simulated client session for acme-stream-cleanup."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import AsyncIterator


@dataclass
class StreamMessage:
    id: str
    payload: dict


class AcmeStreamSession:
    """Represents a connection session to an Acme stream broker."""

    def __init__(self, messages: list[StreamMessage]) -> None:
        self._messages = list(messages)
        self.is_opened = False
        self.is_closed = False
        self.active_connections = 0

    async def open(self) -> None:
        if self.is_opened:
            raise RuntimeError("Session is already open")
        self.is_opened = True
        self.active_connections += 1

    async def close(self) -> None:
        if not self.is_opened:
            return
        if self.is_closed:
            return
        self.is_closed = True
        self.active_connections = max(0, self.active_connections - 1)

    async def stream_messages(self) -> AsyncIterator[StreamMessage]:
        if not self.is_opened or self.is_closed:
            raise RuntimeError("Cannot stream from unopened or closed session")
        for msg in self._messages:
            yield msg
