"""Webhook queue service for asynchronous message processing."""

import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from app.services.redis import redis_service
from app.core.logging import logger
from app.core.metrics import (
    chatwoot_webhooks_total,
)


class WebhookQueueService:
    """Service for managing webhook processing queue using Redis."""

    QUEUE_KEY = "chatwoot:webhook:queue"
    PROCESSING_KEY = "chatwoot:webhook:processing"
    FAILED_KEY = "chatwoot:webhook:failed"
    PROCESSED_KEY = "chatwoot:webhook:processed"  # Track processed message IDs
    MAX_RETRY_COUNT = 3
    PROCESSING_TIMEOUT = 60  # seconds
    DEDUP_TTL = 300  # 5 minutes TTL for processed message tracking

    def __init__(self):
        """Initialize the webhook queue service."""
        self.redis = redis_service
        self._processing_lock = asyncio.Lock()

    async def enqueue(self, webhook_data: Dict[str, Any]) -> bool:
        """Add a webhook to the processing queue with deduplication.

        Args:
            webhook_data: The webhook payload to process

        Returns:
            True if successfully queued, False if already processed or error
        """
        try:
            message_id = webhook_data.get("id")
            if not message_id:
                logger.error("webhook_missing_message_id")
                return False
                
            # Check if message was recently processed (deduplication)
            async with self.redis.get_client() as client:
                if client:
                    # Check if message was already processed
                    dedup_key = f"{self.PROCESSED_KEY}:{message_id}"
                    already_processed = await client.exists(dedup_key)
                    
                    if already_processed:
                        logger.info(
                            "webhook_duplicate_skipped",
                            message_id=message_id,
                            event_type=webhook_data.get("event", "unknown"),
                        )
                        return False  # Skip duplicate
                    
                    # Add timestamp and retry count
                    queue_item = {
                        "data": webhook_data,
                        "timestamp": datetime.utcnow().isoformat(),
                        "retry_count": 0,
                        "id": f"{message_id}_{datetime.utcnow().timestamp()}",
                    }

                    # Use Redis list as queue (RPUSH for enqueue)
                    await client.rpush(self.QUEUE_KEY, json.dumps(queue_item))
                    
                    # Mark as being processed with TTL
                    await client.setex(dedup_key, self.DEDUP_TTL, "processing")

                    # Track metrics
                    event_type = webhook_data.get("event", "unknown")
                    chatwoot_webhooks_total.labels(event_type=event_type, status="queued").inc()

                    logger.debug("webhook_queued", webhook_id=message_id, event_type=event_type)
                    return True
                else:
                    logger.error("webhook_queue_redis_unavailable")
                    return False

        except Exception as e:
            logger.error("webhook_enqueue_failed", error=str(e))
            return False

    async def dequeue(self, timeout: int = 1) -> Optional[Dict[str, Any]]:
        """Retrieve and remove a webhook from the queue.

        Args:
            timeout: Blocking timeout in seconds

        Returns:
            The webhook queue item or None if queue is empty
        """
        try:
            async with self.redis.get_client() as client:
                if not client:
                    return None

                # Use blocking pop with timeout (BLPOP)
                result = await client.blpop(self.QUEUE_KEY, timeout=timeout)

                if result:
                    _, item_json = result
                    queue_item = json.loads(item_json)

                    # Move to processing set with expiration
                    processing_key = f"{self.PROCESSING_KEY}:{queue_item['id']}"
                    await client.setex(processing_key, self.PROCESSING_TIMEOUT, item_json)

                    logger.debug(
                        "webhook_dequeued",
                        webhook_id=queue_item.get("id"),
                        retry_count=queue_item.get("retry_count", 0),
                    )

                    return queue_item

                return None

        except asyncio.TimeoutError:
            # Normal timeout, queue is empty
            return None
        except Exception as e:
            logger.error("webhook_dequeue_failed", error=str(e))
            return None

    async def mark_completed(self, queue_item_id: str) -> bool:
        """Mark a webhook as successfully processed.

        Args:
            queue_item_id: The queue item ID

        Returns:
            True if successfully marked
        """
        try:
            async with self.redis.get_client() as client:
                if client:
                    # Remove from processing set
                    processing_key = f"{self.PROCESSING_KEY}:{queue_item_id}"
                    await client.delete(processing_key)

                    logger.debug("webhook_marked_completed", queue_item_id=queue_item_id)
                    return True

            return False

        except Exception as e:
            logger.error("webhook_mark_completed_failed", error=str(e))
            return False

    async def mark_failed(self, queue_item: Dict[str, Any], error: str) -> bool:
        """Mark a webhook as failed and potentially retry.

        Args:
            queue_item: The queue item that failed
            error: Error message

        Returns:
            True if handled (either requeued or moved to failed)
        """
        try:
            queue_item_id = queue_item.get("id")
            retry_count = queue_item.get("retry_count", 0)

            async with self.redis.get_client() as client:
                if not client:
                    return False

                # Remove from processing
                processing_key = f"{self.PROCESSING_KEY}:{queue_item_id}"
                await client.delete(processing_key)

                if retry_count < self.MAX_RETRY_COUNT:
                    # Increment retry count and requeue
                    queue_item["retry_count"] = retry_count + 1
                    queue_item["last_error"] = error
                    queue_item["last_retry"] = datetime.utcnow().isoformat()

                    # Add exponential backoff delay
                    delay = 2**retry_count  # 1s, 2s, 4s
                    await asyncio.sleep(delay)

                    # Requeue for retry
                    await client.rpush(self.QUEUE_KEY, json.dumps(queue_item))

                    logger.warning(
                        "webhook_requeued_for_retry",
                        queue_item_id=queue_item_id,
                        retry_count=retry_count + 1,
                        error=error,
                    )
                else:
                    # Move to failed queue
                    queue_item["final_error"] = error
                    queue_item["failed_at"] = datetime.utcnow().isoformat()

                    await client.rpush(self.FAILED_KEY, json.dumps(queue_item))

                    logger.error(
                        "webhook_permanently_failed", queue_item_id=queue_item_id, retry_count=retry_count, error=error
                    )

                return True

        except Exception as e:
            logger.error("webhook_mark_failed_error", error=str(e))
            return False

    async def get_queue_size(self) -> int:
        """Get the current queue size.

        Returns:
            Number of items in queue
        """
        try:
            async with self.redis.get_client() as client:
                if client:
                    return await client.llen(self.QUEUE_KEY)
            return 0
        except Exception:
            return 0

    async def get_processing_count(self) -> int:
        """Get the number of items currently being processed.

        Returns:
            Number of items being processed
        """
        try:
            async with self.redis.get_client() as client:
                if client:
                    keys = await client.keys(f"{self.PROCESSING_KEY}:*")
                    return len(keys) if keys else 0
            return 0
        except Exception:
            return 0

    async def recover_stale_items(self) -> int:
        """Recover items that have been processing too long.

        Returns:
            Number of items recovered
        """
        recovered = 0
        try:
            async with self.redis.get_client() as client:
                if not client:
                    return 0

                # Find all processing items
                keys = await client.keys(f"{self.PROCESSING_KEY}:*")

                for key in keys:
                    # Check if item has expired (handled by Redis TTL)
                    # If we can still get it, check its age
                    item_json = await client.get(key)
                    if item_json:
                        queue_item = json.loads(item_json)
                        timestamp = datetime.fromisoformat(queue_item["timestamp"])

                        # If older than timeout, requeue
                        if datetime.utcnow() - timestamp > timedelta(seconds=self.PROCESSING_TIMEOUT * 2):
                            await self.mark_failed(queue_item, "Processing timeout")
                            recovered += 1

                if recovered > 0:
                    logger.info("webhook_stale_items_recovered", count=recovered)

        except Exception as e:
            logger.error("webhook_recovery_failed", error=str(e))

        return recovered

    async def clear_failed_queue(self) -> int:
        """Clear the failed queue.

        Returns:
            Number of items cleared
        """
        try:
            async with self.redis.get_client() as client:
                if client:
                    count = await client.llen(self.FAILED_KEY)
                    await client.delete(self.FAILED_KEY)
                    logger.info("webhook_failed_queue_cleared", count=count)
                    return count
            return 0
        except Exception as e:
            logger.error("webhook_clear_failed_queue_error", error=str(e))
            return 0


# Global webhook queue service instance
webhook_queue_service = WebhookQueueService()
