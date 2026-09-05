"""Mock Acme Stream Client library with strict protocol enforcement.

Protocol rules:
1. `client.subscribe(topic)` MUST be awaited before `client.stream_events(topic)` is called. Calling stream_events without subscribe raises `UnsubscribedTopicError`.
2. For messages where `msg.requires_ack` is True, `await client.ack(msg.id)` must be called. Calling `ack()` on a message with `requires_ack=False` raises `InvalidAckError`.
3. If processing a message fails, `await client.nack(msg.id, reason=...)` must be called.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass


class UnsubscribedTopicError(Exception):
    """Raised when streaming from a topic without prior subscription."""
    pass


class InvalidAckError(Exception):
    """Raised when calling ack() on a message that does not require ack (e.g. broadcast)."""
    pass


class UnacknowledgedMessageError(Exception):
    """Raised when the next message is read while an ack-required message is still pending."""
    pass


@dataclass(slots=True)
class StreamMessage:
    id: str
    payload: dict
    requires_ack: bool = True


class AcmeStreamClient:
    def __init__(self, events: list[StreamMessage]) -> None:
        self._events = list(events)
        self._subscribed_topics: set[str] = set()
        self.acked_ids: list[str] = []
        self.nacked_ids: list[tuple[str, str]] = []
        self._pending_ack: str | None = None

    async def subscribe(self, topic: str) -> None:
        self._subscribed_topics.add(topic)

    async def stream_events(self, topic: str):
        if topic not in self._subscribed_topics:
            raise UnsubscribedTopicError(
                f"Cannot stream from topic '{topic}' without awaiting client.subscribe('{topic}') first."
            )
        for msg in self._events:
            if self._pending_ack is not None:
                raise UnacknowledgedMessageError(
                    f"Message '{self._pending_ack}' was not acked or nacked before reading next message."
                )
            if msg.requires_ack:
                self._pending_ack = msg.id
            yield msg

    async def ack(self, message_id: str) -> None:
        if self._pending_ack != message_id:
            # Check if it was non-ackable or already handled
            raise InvalidAckError(
                f"Cannot ack message '{message_id}': message either does not require ack or is not currently pending."
            )
        self.acked_ids.append(message_id)
        self._pending_ack = None

    async def nack(self, message_id: str, reason: str = "") -> None:
        if self._pending_ack == message_id:
            self._pending_ack = None
        self.nacked_ids.append((message_id, reason))
