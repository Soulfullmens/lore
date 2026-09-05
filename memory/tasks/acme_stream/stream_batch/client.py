"""Mock Acme Stream Client library with strict protocol enforcement."""
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
        self._pending_acks: set[str] = set()

    async def subscribe(self, topic: str) -> None:
        self._subscribed_topics.add(topic)

    async def stream_events(self, topic: str):
        if topic not in self._subscribed_topics:
            raise UnsubscribedTopicError(
                f"Cannot stream from topic '{topic}' without awaiting client.subscribe('{topic}') first."
            )
        for msg in self._events:
            if msg.requires_ack:
                self._pending_acks.add(msg.id)
            yield msg

    async def ack(self, message_id: str) -> None:
        if message_id not in self._pending_acks:
            raise InvalidAckError(
                f"Cannot ack message '{message_id}': message either does not require ack or is not currently pending."
            )
        self.acked_ids.append(message_id)
        self._pending_acks.remove(message_id)

    async def nack(self, message_id: str, reason: str = "") -> None:
        if message_id in self._pending_acks:
            self._pending_acks.remove(message_id)
        self.nacked_ids.append((message_id, reason))
