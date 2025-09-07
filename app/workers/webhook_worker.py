"""Background worker for processing Chatwoot webhooks from queue."""

import asyncio
import time
from typing import Dict, Any, Optional

from app.services.webhook_queue import webhook_queue_service
from app.services.chatwoot import chatwoot_service
from app.services.agent import agent_service
from app.core.logging import logger
from app.core.metrics import (
    chatwoot_message_processing_duration_seconds,
    chatwoot_messages_sent_total,
)
from app.schemas.chatwoot import (
    ChatwootMessageWebhook,
    ChatwootEventType,
    MessageMapping,
)


class WebhookWorker:
    """Worker for processing queued webhooks asynchronously."""

    def __init__(self, worker_id: int = 0, max_concurrent_tasks: int = 5):
        """Initialize the webhook worker.

        Args:
            worker_id: Unique identifier for this worker
            max_concurrent_tasks: Maximum number of concurrent webhook processing tasks
        """
        self.worker_id = worker_id
        self.max_concurrent_tasks = max_concurrent_tasks
        self.queue_service = webhook_queue_service
        self._running = False
        self._tasks: set = set()
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the worker processing loop."""
        self._running = True
        logger.info("webhook_worker_started", worker_id=self.worker_id, max_concurrent_tasks=self.max_concurrent_tasks)

        # Start recovery task
        asyncio.create_task(self._recovery_loop())

        # Main processing loop
        while self._running:
            try:
                # Clean up completed tasks
                self._tasks = {task for task in self._tasks if not task.done()}

                # Check if we can process more tasks
                if len(self._tasks) < self.max_concurrent_tasks:
                    # Try to get item from queue (with short timeout)
                    queue_item = await self.queue_service.dequeue(timeout=1)

                    if queue_item:
                        # Process webhook asynchronously
                        task = asyncio.create_task(self._process_webhook(queue_item))
                        self._tasks.add(task)
                else:
                    # At capacity, wait a bit
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info("webhook_worker_cancelled", worker_id=self.worker_id)
                break
            except Exception as e:
                logger.error("webhook_worker_loop_error", worker_id=self.worker_id, error=str(e))
                await asyncio.sleep(1)

        # Wait for remaining tasks to complete
        if self._tasks:
            logger.info("webhook_worker_waiting_for_tasks", worker_id=self.worker_id, task_count=len(self._tasks))
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("webhook_worker_stopped", worker_id=self.worker_id)

    async def stop(self):
        """Stop the worker gracefully."""
        logger.info("webhook_worker_stopping", worker_id=self.worker_id)
        self._running = False
        self._shutdown_event.set()

    async def _recovery_loop(self):
        """Periodically recover stale processing items."""
        while self._running:
            try:
                # Wait 30 seconds between recovery attempts
                await asyncio.sleep(30)

                # Recover stale items
                recovered = await self.queue_service.recover_stale_items()
                if recovered > 0:
                    logger.info("webhook_worker_recovered_items", worker_id=self.worker_id, count=recovered)

            except Exception as e:
                logger.error("webhook_worker_recovery_error", worker_id=self.worker_id, error=str(e))

    async def _process_webhook(self, queue_item: Dict[str, Any]):
        """Process a single webhook from the queue.

        Args:
            queue_item: The queue item containing webhook data
        """
        start_time = time.time()
        processing_status = "failed"
        queue_item_id = queue_item.get("id")
        webhook_data = queue_item.get("data", {})

        try:
            event_type = webhook_data.get("event")

            logger.debug(
                "webhook_worker_processing",
                worker_id=self.worker_id,
                queue_item_id=queue_item_id,
                event_type=event_type,
                retry_count=queue_item.get("retry_count", 0),
            )

            # Process based on event type
            if event_type == ChatwootEventType.MESSAGE_CREATED:
                # Parse webhook data
                webhook = ChatwootMessageWebhook(**webhook_data)

                # Only process incoming messages
                if webhook.message_type == "incoming":
                    await self._process_message(webhook)
                    processing_status = "success"
                else:
                    logger.debug("webhook_worker_skipped_outgoing", worker_id=self.worker_id, message_id=webhook.id)
                    processing_status = "skipped"
            else:
                # Other event types can be handled here if needed
                logger.debug("webhook_worker_unhandled_event", worker_id=self.worker_id, event_type=event_type)
                processing_status = "skipped"

            # Mark as completed
            await self.queue_service.mark_completed(queue_item_id)

        except Exception as e:
            logger.error(
                "webhook_worker_processing_error",
                worker_id=self.worker_id,
                queue_item_id=queue_item_id,
                error=str(e),
                exc_info=True,
            )

            # Mark as failed (will retry if under limit)
            await self.queue_service.mark_failed(queue_item, str(e))

        finally:
            # Track processing duration
            duration = time.time() - start_time
            chatwoot_message_processing_duration_seconds.labels(status=processing_status).observe(duration)

            logger.debug(
                "webhook_worker_processing_complete",
                worker_id=self.worker_id,
                queue_item_id=queue_item_id,
                status=processing_status,
                duration=duration,
            )

    async def _process_message(self, webhook: ChatwootMessageWebhook):
        """Process an incoming message webhook.

        Args:
            webhook: The parsed message webhook
        """
        # Extract message details
        message_id = webhook.id
        conversation = webhook.conversation
        sender = webhook.sender
        message_content = webhook.content

        # Skip empty messages
        if not message_content or not message_content.strip():
            logger.debug("webhook_worker_empty_message", worker_id=self.worker_id, message_id=message_id)
            return

        # Use simplified phone-based user identification
        from app.services.user_identification import user_identification_service

        # Check if we need to request phone number from user
        if user_identification_service.requires_phone_number(sender):
            # First, check if the message contains a phone number
            extracted_phone = user_identification_service.extract_phone_from_message(message_content)

            if extracted_phone:
                # Phone number provided, try to update contact and create user
                logger.info(
                    "webhook_worker_phone_extracted",
                    worker_id=self.worker_id,
                    contact_id=sender.id,
                    phone=extracted_phone,
                )

                # Store the phone number mapping for future messages
                mapping_stored = user_identification_service.store_contact_phone_mapping(sender.id, extracted_phone)

                if not mapping_stored:
                    logger.error(
                        "webhook_worker_invalid_phone_extracted",
                        worker_id=self.worker_id,
                        contact_id=sender.id,
                        phone=extracted_phone,
                    )
                    # Fall through to phone request
                else:
                    # Update the sender contact with the phone number
                    sender.phone = extracted_phone

                    # Now create user with the phone number
                    user = user_identification_service.find_or_create_user_from_chatwoot(sender)

                    if user:
                        # Send confirmation message
                        from app.schemas.chat import Message

                        confirm_msg = Message(
                            role="assistant",
                            content=f"Great! I've registered your phone number {extracted_phone}. How can I help you today?",
                        )
                        confirm_message = MessageMapping.internal_to_chatwoot(confirm_msg)
                        await self._send_message_safe(conversation.id, confirm_message)

                        # Mark conversation as read (fire-and-forget)
                        asyncio.create_task(self._mark_read_safe(conversation.id))

                        # Don't process the phone number message through the agent
                        # Just return after sending confirmation
                        return
                    else:
                        logger.error(
                            "webhook_worker_user_creation_failed_after_phone",
                            worker_id=self.worker_id,
                            contact_id=sender.id,
                            phone=extracted_phone,
                        )

            # No valid phone number found, request it
            logger.info(
                "webhook_worker_requesting_phone",
                worker_id=self.worker_id,
                contact_id=sender.id,
                conversation_id=conversation.id,
            )

            # Send phone number request message
            from app.schemas.chat import Message

            phone_request_msg = Message(
                role="assistant",
                content="Hi! To better assist you, could you please share your phone number? Please provide it in the format +60XXXXXXXXX (Malaysian format).",
            )
            phone_request_message = MessageMapping.internal_to_chatwoot(phone_request_msg)
            await self._send_message_safe(conversation.id, phone_request_message)

            # Don't process further, just wait for phone number
            return
        else:
            # Find or create user based on phone number
            user = user_identification_service.find_or_create_user_from_chatwoot(sender)

            if not user:
                logger.error(
                    "webhook_worker_user_creation_failed",
                    worker_id=self.worker_id,
                    contact_id=sender.id,
                    phone=sender.phone,
                )
                return

            # Generate session ID and user ID
            session_id = user_identification_service.get_user_session_id(user.id, conversation.id)
            user_id = f"user_{user.id}"

        # Convert to internal format
        internal_message = MessageMapping.chatwoot_to_internal(webhook)

        logger.debug(
            "webhook_worker_invoking_agent",
            worker_id=self.worker_id,
            session_id=session_id,
            conversation_id=conversation.id,
        )

        # Get response from agent
        agent = agent_service.get_agent()
        response = await agent.get_response(messages=[internal_message], session_id=session_id, user_id=user_id)

        # Send responses back to Chatwoot concurrently
        send_tasks = []
        for agent_msg in response.get("new_messages", []):
            if agent_msg.role == "assistant" and agent_msg.content:
                chatwoot_message = MessageMapping.internal_to_chatwoot(agent_msg)
                send_tasks.append(self._send_message_safe(conversation.id, chatwoot_message))

        # Mark conversation as read (fire-and-forget)
        asyncio.create_task(self._mark_read_safe(conversation.id))

        # Execute all message sending tasks
        if send_tasks:
            results = await asyncio.gather(*send_tasks, return_exceptions=True)

            # Log any errors
            for _i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "webhook_worker_send_error",
                        worker_id=self.worker_id,
                        conversation_id=conversation.id,
                        error=str(result),
                    )

    async def _send_message_safe(self, conversation_id: int, message):
        """Send message to Chatwoot with error handling.

        Args:
            conversation_id: Conversation ID
            message: Message to send
        """
        try:
            response = await chatwoot_service.send_message(conversation_id=conversation_id, message=message)

            chatwoot_messages_sent_total.labels(status="success").inc()

            logger.debug(
                "webhook_worker_message_sent",
                worker_id=self.worker_id,
                conversation_id=conversation_id,
                message_id=response.id,
            )

            return response

        except Exception as e:
            chatwoot_messages_sent_total.labels(status="failed").inc()
            logger.error(
                "webhook_worker_send_failed", worker_id=self.worker_id, conversation_id=conversation_id, error=str(e)
            )
            raise

    async def _mark_read_safe(self, conversation_id: int):
        """Mark conversation as read with error handling.

        Args:
            conversation_id: Conversation ID
        """
        try:
            await chatwoot_service.mark_conversation_as_read(conversation_id)
            logger.debug("webhook_worker_marked_read", worker_id=self.worker_id, conversation_id=conversation_id)
        except Exception as e:
            # Non-critical, just log warning
            logger.warning(
                "webhook_worker_mark_read_failed",
                worker_id=self.worker_id,
                conversation_id=conversation_id,
                error=str(e),
            )


class WebhookWorkerPool:
    """Manages a pool of webhook workers."""

    def __init__(self, num_workers: int = 5, max_concurrent_per_worker: int = 5):
        """Initialize the worker pool.

        Args:
            num_workers: Number of workers in the pool
            max_concurrent_per_worker: Max concurrent tasks per worker
        """
        self.num_workers = num_workers
        self.max_concurrent_per_worker = max_concurrent_per_worker
        self.workers: list[WebhookWorker] = []
        self.worker_tasks: list[asyncio.Task] = []

    async def start(self):
        """Start all workers in the pool."""
        logger.info(
            "webhook_worker_pool_starting",
            num_workers=self.num_workers,
            max_concurrent_per_worker=self.max_concurrent_per_worker,
        )

        for i in range(self.num_workers):
            worker = WebhookWorker(worker_id=i, max_concurrent_tasks=self.max_concurrent_per_worker)
            self.workers.append(worker)

            # Start worker task
            task = asyncio.create_task(worker.start())
            self.worker_tasks.append(task)

        logger.info("webhook_worker_pool_started", num_workers=self.num_workers)

    async def stop(self):
        """Stop all workers gracefully."""
        logger.info("webhook_worker_pool_stopping")

        # Signal all workers to stop
        for worker in self.workers:
            await worker.stop()

        # Wait for all worker tasks to complete
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)

        self.workers.clear()
        self.worker_tasks.clear()

        logger.info("webhook_worker_pool_stopped")

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the worker pool.

        Returns:
            Pool statistics
        """
        queue_size = await webhook_queue_service.get_queue_size()
        processing_count = await webhook_queue_service.get_processing_count()

        return {
            "num_workers": self.num_workers,
            "max_concurrent_per_worker": self.max_concurrent_per_worker,
            "queue_size": queue_size,
            "processing_count": processing_count,
            "workers_running": len([w for w in self.workers if w._running]),
        }


# Global worker pool instance (will be initialized in main app)
webhook_worker_pool: Optional[WebhookWorkerPool] = None
