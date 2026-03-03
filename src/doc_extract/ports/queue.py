"""Queue port - abstraction for message queue operations."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class QueueMessage:
    """A message in the queue."""

    message_id: str
    body: dict
    timestamp: datetime
    attempts: int = 0
    metadata: dict | None = None


@dataclass
class QueueSubscription:
    """Subscription handle for cleanup."""

    subscription_id: str

    async def unsubscribe(self) -> None:
        """Unsubscribe from the queue."""
        pass


class QueuePort(ABC):
    """Port for message queue operations.

    This enables decoupled, event-driven architecture.

    Implementations:
        - AsyncMemoryQueueAdapter: In-memory queue for local dev
        - GooglePubSubAdapter: Google Pub/Sub for production
    """

    @abstractmethod
    async def publish(self, topic: str, message: dict) -> str:
        """Publish a message to a topic.

        Args:
            topic: Topic/channel name
            message: Message payload (must be JSON-serializable)

        Returns:
            Message ID
        """
        pass

    @abstractmethod
    async def subscribe(
        self, topic: str, handler: Callable[[QueueMessage], Any], **kwargs
    ) -> QueueSubscription:
        """Subscribe to a topic.

        Args:
            topic: Topic to subscribe to
            handler: Callback function for messages
            **kwargs: Implementation-specific options

        Returns:
            Subscription handle
        """
        pass

    @abstractmethod
    async def acknowledge(self, message_id: str) -> bool:
        """Acknowledge successful message processing.

        Args:
            message_id: ID of the message to ack

        Returns:
            True if acknowledged
        """
        pass

    @abstractmethod
    async def reject(
        self, message_id: str, requeue: bool = False, reason: str | None = None
    ) -> bool:
        """Reject a message (negative acknowledge).

        Args:
            message_id: ID of the message
            requeue: Whether to requeue for retry
            reason: Rejection reason for logging

        Returns:
            True if rejected
        """
        pass

    @abstractmethod
    async def publish_to_dlq(self, message: QueueMessage, reason: str) -> str:
        """Publish message to Dead Letter Queue after max retries.

        Args:
            message: The failed message
            reason: Why it failed

        Returns:
            DLQ message ID
        """
        pass
