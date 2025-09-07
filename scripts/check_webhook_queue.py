#!/usr/bin/env python3
"""Check webhook queue status and force process a message."""

import asyncio
import json
from app.services.redis import redis_service
from app.services.webhook_queue import webhook_queue_service
from app.workers.webhook_worker import WebhookWorker

async def check_queue_status():
    """Check the status of webhook queue."""
    print("📊 Webhook Queue Status")
    print("=" * 40)
    
    try:
        # Check Redis connection
        async with redis_service.get_client() as client:
            if not client:
                print("❌ Redis client not available")
                return
                
            print("✅ Redis connection OK")
            
            # Check queue contents
            queue_key = webhook_queue_service.QUEUE_KEY
            processing_key = webhook_queue_service.PROCESSING_KEY
            failed_key = webhook_queue_service.FAILED_KEY
            
            queue_length = await client.llen(queue_key)
            processing_length = await client.llen(processing_key)
            failed_length = await client.llen(failed_key)
            
            print(f"📋 Queue length: {queue_length}")
            print(f"⚡ Processing length: {processing_length}")
            print(f"❌ Failed length: {failed_length}")
            
            # Show first few queue items
            if queue_length > 0:
                print("\n📄 First few queue items:")
                queue_items = await client.lrange(queue_key, 0, 2)
                for i, item in enumerate(queue_items):
                    try:
                        data = json.loads(item)
                        content = data.get('content', 'N/A')[:50]
                        message_id = data.get('id', 'N/A')
                        print(f"  [{i+1}] ID: {message_id} | Content: {content}...")
                    except Exception as e:
                        print(f"  [{i+1}] Invalid JSON: {e}")
            
            # Check processing items
            if processing_length > 0:
                print(f"\n⚡ Processing items: {processing_length}")
                processing_items = await client.lrange(processing_key, 0, 2)
                for i, item in enumerate(processing_items):
                    try:
                        data = json.loads(item)
                        content = data.get('content', 'N/A')[:50]
                        print(f"  [{i+1}] Processing: {content}...")
                    except Exception as e:
                        print(f"  [{i+1}] Invalid JSON: {e}")

    except Exception as e:
        print(f"💥 Error checking queue: {e}")

async def process_one_message():
    """Process one message from the queue manually."""
    print("\n🔨 Manual Message Processing")
    print("=" * 40)
    
    try:
        worker = WebhookWorker(worker_id=999, max_concurrent_tasks=1)
        
        # Try to dequeue and process one message
        webhook_data = await webhook_queue_service.dequeue()
        
        if webhook_data:
            print(f"📝 Processing message: {webhook_data.get('content', 'N/A')[:100]}...")
            
            # Process the webhook manually
            success = await worker._process_single_webhook(webhook_data)
            
            if success:
                print("✅ Message processed successfully")
            else:
                print("❌ Message processing failed")
        else:
            print("📭 No messages in queue to process")
            
    except Exception as e:
        print(f"💥 Error processing message: {e}")

if __name__ == "__main__":
    asyncio.run(check_queue_status())
    asyncio.run(process_one_message())