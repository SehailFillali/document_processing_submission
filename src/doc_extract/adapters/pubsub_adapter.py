"""Google Cloud Pub/Sub adapter for production."""

import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from doc_extract.core.logging import logger
from doc_extract.ports.queue import QueueMessage, QueuePort, QueueSubscription


@dataclass
class PubSubMessage:
    """Wrapper for Pub/Sub message."""

    message_id: str
    data: dict
    publish_time: datetime


class PubSubAdapter(QueuePort):
    """Google Cloud Pub/Sub implementation of QueuePort.

    Requires:
    - google-cloud-pubsub package
    - GOOGLE_APPLICATION_CREDENTIALS or compute engine service account

    Usage:
        queue = PubSubAdapter(project_id="my-project")
        await queue.publish("document.events", {"submission_id": "123"})
    """

    def __init__(self, project_id: str, dlq_project_id: str | None = None):
        self.project_id = project_id
        self.dlq_project_id = dlq_project_id or project_id
        self._publisher = None
        self._subscriber = None
        self._subscriptions = {}
        logger.info(f"Initialized PubSubAdapter for project: {project_id}")

    def _get_publisher(self):
        """Lazy initialization of Pub/Sub publisher."""
        if self._publisher is None:
            from google.cloud import pubsub_v1

            self._publisher = pubsub_v1.PublisherClient()
        return self._publisher

    def _get_subscriber(self):
        """Lazy initialization of Pub/Sub subscriber."""
        if self._subscriber is None:
            from google.cloud import pubsub_v1

            self._subscriber = pubsub_v1.SubscriberClient()
        return self._subscriber

    async def publish(self, topic: str, message: dict) -> str:
        """Publish message to Pub/Sub topic."""
        topic_path = self._get_publisher().topic_path(self.project_id, topic)

        data = json.dumps(message).encode("utf-8")

        future = self._get_publisher().publish(topic_path, data)
        message_id = future.result()

        logger.info(f"Published message to {topic}: {message_id}")
        return message_id

    async def subscribe(
        self, topic: str, handler: Callable[[QueueMessage], Any], **kwargs
    ) -> QueueSubscription:
        """Subscribe to Pub/Sub topic."""

        subscription_id = f"{topic}-sub-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        subscription_path = self._get_subscriber().subscription_path(
            self.project_id, subscription_id
        )

        topic_path = self._get_publisher().topic_path(self.project_id, topic)

        # Create subscription if not exists
        with contextlib.suppress(Exception):
            self._get_subscriber().create_subscription(
                subscription=subscription_path, topic=topic_path
            )

        # Start listening
        async def callback(message):
            try:
                data = json.loads(message.data.decode("utf-8"))
                queue_msg = QueueMessage(
                    message_id=message.message_id,
                    body=data,
                    timestamp=datetime.now(UTC),
                )
                await handler(queue_msg)
                message.ack()
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                message.nack()

        future = self._get_subscriber().subscribe(subscription_path, callback)

        self._subscriptions[subscription_id] = future

        logger.info(f"Subscribed to {topic} with {subscription_id}")

        return QueueSubscription(subscription_id=subscription_id)

    async def acknowledge(self, message_id: str) -> bool:
        """Acknowledge message (no-op with async callback)."""
        return True

    async def reject(
        self, message_id: str, requeue: bool = False, reason: str | None = None
    ) -> bool:
        """Reject message (no-op with async callback)."""
        return True

    async def publish_to_dlq(self, message: QueueMessage, reason: str) -> str:
        """Publish failed message to Dead Letter Queue."""
        dlq_topic = f"{message.body.get('topic', 'unknown')}-dlq"

        dlq_message = {
            **message.body,
            "dlq_reason": reason,
            "original_timestamp": message.timestamp.isoformat(),
            "dlq_timestamp": datetime.now(UTC).isoformat(),
        }

        return await self.publish(dlq_topic, dlq_message)

    async def close(self):
        """Close all subscriptions."""
        for _sub_id, future in self._subscriptions.items():
            future.cancel()
        self._subscriptions.clear()
        logger.info("Closed all Pub/Sub subscriptions")
