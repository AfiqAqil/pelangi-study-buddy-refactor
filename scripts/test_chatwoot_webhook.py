#!/usr/bin/env python3
"""Test Chatwoot webhook with RAG functionality."""

import requests
import json
import hashlib
import hmac
import time
from datetime import datetime

# Configuration
WEBHOOK_URL = "http://localhost:8000/api/v1/chatwoot/webhook"
WEBHOOK_SECRET = "your-webhook-secret"  # Replace with actual secret if needed

def create_chatwoot_signature(payload, secret):
    """Create HMAC signature for Chatwoot webhook."""
    signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def test_rag_webhook():
    """Test RAG functionality through Chatwoot webhook."""
    
    # Test payload simulating a Chatwoot message about Newton's law (flat structure)
    payload = {
        "event": "message_created",
        "id": 12345,
        "content": "What is Newton's first law?",
        "message_type": "incoming",
        "content_type": "text",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "private": False,
        "conversation": {
            "id": 1001,
            "status": "open",
            "contact_id": 5001
        },
        "contact": {
            "id": 5001,
            "name": "Test Student", 
            "phone": "+60123456789",
            "email": "test@example.com"
        },
        "account": {
            "id": 1,
            "name": "Test Account"
        },
        "inbox": {
            "id": 1,
            "name": "Test Inbox",
            "channel_type": "api"
        },
        "sender": {
            "id": 5001,
            "name": "Test Student",
            "type": "contact"
        }
    }
    
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    # Create signature (if webhook secret is configured)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Chatwoot-Webhook/1.0"
    }
    
    # Add signature if secret is configured
    if WEBHOOK_SECRET and WEBHOOK_SECRET != "your-webhook-secret":
        signature = create_chatwoot_signature(payload_str, WEBHOOK_SECRET)
        headers["X-Chatwoot-Signature"] = signature
    
    print("🧪 Testing RAG through Chatwoot webhook...")
    print(f"📤 Sending request to: {WEBHOOK_URL}")
    print(f"💬 Message: '{payload['content']}'")
    print()
    
    try:
        # Send webhook request
        start_time = time.time()
        response = requests.post(
            WEBHOOK_URL,
            headers=headers,
            data=payload_str,
            timeout=30
        )
        end_time = time.time()
        
        print(f"⏱️  Response time: {end_time - start_time:.2f} seconds")
        print(f"📊 Status code: {response.status_code}")
        print(f"📋 Response headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            print("✅ Webhook processed successfully")
            try:
                response_data = response.json()
                print(f"📄 Response: {json.dumps(response_data, indent=2)}")
            except:
                print(f"📄 Response text: {response.text}")
        else:
            print(f"❌ Webhook failed with status {response.status_code}")
            print(f"📄 Error response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out (>30s)")
    except requests.exceptions.ConnectionError:
        print("🔌 Connection error - is the server running on port 8000?")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")

def test_multiple_messages():
    """Test multiple educational questions to see RAG behavior."""
    
    questions = [
        "What is Newton's first law?",
        "Explain photosynthesis process",
        "What is the formula for kinetic energy?",
        "Define osmosis in biology"
    ]
    
    print("🔄 Testing multiple RAG questions...")
    print("=" * 50)
    
    for i, question in enumerate(questions, 1):
        print(f"\n🧪 Test {i}/4: {question}")
        print("-" * 30)
        
        payload = {
            "event": "message_created",
            "id": 12345 + i,
            "content": question,
            "message_type": "incoming",
            "content_type": "text",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "private": False,
            "conversation": {
                "id": 1001,
                "status": "open", 
                "contact_id": 5001
            },
            "contact": {
                "id": 5001,
                "name": "Test Student",
                "phone": "+60123456789"
            },
            "account": {
                "id": 1,
                "name": "Test Account"
            },
            "inbox": {
                "id": 1,
                "name": "Test Inbox",
                "channel_type": "api"
            },
            "sender": {
                "id": 5001,
                "name": "Test Student", 
                "type": "contact"
            }
        }
        
        payload_str = json.dumps(payload, separators=(',', ':'))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Chatwoot-Webhook/1.0"
        }
        
        try:
            start_time = time.time()
            response = requests.post(WEBHOOK_URL, headers=headers, data=payload_str, timeout=45)
            end_time = time.time()
            
            print(f"⏱️  Time: {end_time - start_time:.2f}s | Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ Failed: {response.text}")
            else:
                print("✅ Success")
                
        except Exception as e:
            print(f"💥 Error: {e}")
        
        # Small delay between requests
        time.sleep(2)

if __name__ == "__main__":
    print("🚀 Chatwoot + RAG Integration Test")
    print("=" * 40)
    
    # Test single question first
    test_rag_webhook()
    
    print("\n" + "=" * 50)
    
    # Test multiple questions
    test_multiple_messages()