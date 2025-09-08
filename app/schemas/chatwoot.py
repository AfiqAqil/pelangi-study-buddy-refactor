"""Chatwoot webhook schemas and models.

This module defines the data models and schemas for Chatwoot webhook payloads,
API responses, and internal mapping between Chatwoot and application formats.
"""

from datetime import datetime
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.schemas.chat import Message


class ChatwootContact(BaseModel):
    """Chatwoot contact information."""

    id: int = Field(..., description="Contact ID in Chatwoot")
    name: Optional[str] = Field(None, description="Contact name")
    email: Optional[str] = Field(None, description="Contact email")
    phone: Optional[str] = Field(None, description="Contact phone number")
    identifier: Optional[str] = Field(None, description="External identifier")
    custom_attributes: Optional[Dict[str, Any]] = Field(default={}, description="Custom contact attributes")


class ChatwootAccount(BaseModel):
    """Chatwoot account information."""

    id: int = Field(..., description="Account ID")
    name: str = Field(..., description="Account name")


class ChatwootInbox(BaseModel):
    """Chatwoot inbox information."""

    id: int = Field(..., description="Inbox ID")
    name: str = Field(..., description="Inbox name")
    channel_type: Optional[str] = Field(None, description="Type of channel (api, website, etc.)")


class ChatwootConversation(BaseModel):
    """Chatwoot conversation details."""

    id: int = Field(..., description="Conversation ID in Chatwoot")
    status: Literal["open", "resolved", "pending"] = Field(..., description="Conversation status")
    priority: Optional[Literal["urgent", "high", "medium", "low"]] = Field(None, description="Conversation priority")
    agent_last_seen_at: Optional[datetime] = Field(None, description="When agent was last seen")
    assignee: Optional[Dict[str, Any]] = Field(None, description="Assigned agent details")
    contact_last_seen_at: Optional[datetime] = Field(None, description="When contact was last seen")
    timestamp: Optional[datetime] = Field(None, description="Conversation timestamp")
    meta: Optional[Dict[str, Any]] = Field(default={}, description="Additional conversation metadata")
    custom_attributes: Optional[Dict[str, Any]] = Field(default={}, description="Custom conversation attributes")


class ChatwootMessage(BaseModel):
    """Chatwoot message details."""

    id: int = Field(..., description="Message ID in Chatwoot")
    content: str = Field(..., description="Message content", max_length=10000)
    message_type: Literal["incoming", "outgoing", "activity"] = Field(..., description="Type of message")
    content_type: Literal["text", "input_select", "cards", "form", "article"] = Field(
        default="text", description="Content type of the message"
    )
    content_attributes: Optional[Dict[str, Any]] = Field(default={}, description="Additional content attributes")
    created_at: datetime = Field(..., description="Message creation timestamp")
    private: bool = Field(default=False, description="Whether message is private note")
    source_id: Optional[str] = Field(None, description="External source ID")
    sender: Optional[Dict[str, Any]] = Field(None, description="Message sender details")
    external_source_ids: Optional[Dict[str, Any]] = Field(default={}, description="External source identifiers")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate message content."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()


class ChatwootWebhookPayload(BaseModel):
    """Base Chatwoot webhook payload."""

    event: str = Field(..., description="Webhook event type")
    account: ChatwootAccount = Field(..., description="Account information")
    inbox: ChatwootInbox = Field(..., description="Inbox information")
    conversation: ChatwootConversation = Field(..., description="Conversation details")


class ChatwootMessageWebhook(BaseModel):
    """Chatwoot message webhook payload with actual structure."""

    # Basic webhook info
    event: str = Field(..., description="Webhook event type")

    # Message data (at root level in actual Chatwoot webhooks)
    id: int = Field(..., description="Message ID")
    content: str = Field(..., description="Message content")
    message_type: Literal["incoming", "outgoing", "activity"] = Field(..., description="Type of message")
    content_type: Literal["text", "input_select", "cards", "form", "article"] = Field(
        default="text", description="Content type of the message"
    )
    created_at: str = Field(..., description="Message creation timestamp")
    private: bool = Field(default=False, description="Whether message is private note")

    # Account, inbox, conversation info
    account: ChatwootAccount = Field(..., description="Account information")
    inbox: ChatwootInbox = Field(..., description="Inbox information")
    conversation: ChatwootConversation = Field(..., description="Conversation details")

    # Contact/sender info (called 'sender' in actual payload)
    sender: ChatwootContact = Field(..., description="Message sender information")

    # Additional fields from actual payload
    source_id: Optional[str] = Field(None, description="External source ID")
    additional_attributes: Optional[Dict[str, Any]] = Field(default={}, description="Additional attributes")
    content_attributes: Optional[Dict[str, Any]] = Field(default={}, description="Content attributes")


class ChatwootConversationWebhook(ChatwootWebhookPayload):
    """Chatwoot conversation webhook payload."""

    contact: ChatwootContact = Field(..., description="Contact information")
    changed_attributes: Optional[List[str]] = Field(default=[], description="Changed conversation attributes")


class ChatwootAttachment(BaseModel):
    """Chatwoot message attachment."""
    
    external_url: str = Field(..., description="External URL of the attachment")
    file_type: str = Field(default="image", description="Type of attachment (image, file, etc.)")
    fallback_text: Optional[str] = Field(None, description="Fallback text for the attachment")


class ChatwootApiMessage(BaseModel):
    """Chatwoot API message for sending responses."""

    content: str = Field(..., description="Message content", min_length=1, max_length=10000)
    message_type: Literal["outgoing"] = Field(default="outgoing", description="Message type")
    private: bool = Field(default=False, description="Whether message is private note")
    content_type: Literal["text", "input_select", "cards", "form", "article"] = Field(
        default="text", description="Content type"
    )
    content_attributes: Optional[Dict[str, Any]] = Field(default={}, description="Additional content attributes")
    template_params: Optional[Dict[str, Any]] = Field(default={}, description="Template parameters")
    attachments: Optional[List[ChatwootAttachment]] = Field(default=None, description="Message attachments")


class ChatwootApiResponse(BaseModel):
    """Standard Chatwoot API response."""

    id: Optional[int] = Field(None, description="Resource ID")
    message: Optional[str] = Field(None, description="Response message")
    errors: Optional[List[str]] = Field(default=[], description="Error messages if any")


class MessageMapping:
    """Utility class for mapping between Chatwoot and internal message formats."""

    @staticmethod
    def chatwoot_to_internal(webhook_data: "ChatwootMessageWebhook") -> Message:
        """Convert Chatwoot webhook message to internal Message format.

        Args:
            webhook_data: Chatwoot webhook data containing message info

        Returns:
            Message: Internal message format
        """
        return Message(
            role="user",  # Incoming messages from Chatwoot are always user messages
            content=webhook_data.content,
        )

    @staticmethod
    def internal_to_chatwoot(internal_msg: Message) -> ChatwootApiMessage:
        """Convert internal Message to Chatwoot API message format.

        Args:
            internal_msg: Internal message object

        Returns:
            ChatwootApiMessage: Chatwoot API message format
        """
        return ChatwootApiMessage(content=internal_msg.content, message_type="outgoing", content_type="text")

    @staticmethod
    def conversation_to_session_id(webhook_data: "ChatwootMessageWebhook") -> str:
        """Generate a consistent session ID from Chatwoot webhook data.

        Args:
            webhook_data: Chatwoot webhook data

        Returns:
            str: Generated session ID
        """
        return f"chatwoot_conv_{webhook_data.conversation.id}_contact_{webhook_data.sender.id}"


class ChatwootEventType:
    """Constants for Chatwoot webhook event types."""

    MESSAGE_CREATED = "message_created"
    MESSAGE_UPDATED = "message_updated"
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_UPDATED = "conversation_updated"
    CONVERSATION_STATUS_CHANGED = "conversation_status_changed"
    CONVERSATION_TYPING_ON = "conversation_typing_on"
    CONVERSATION_TYPING_OFF = "conversation_typing_off"
    WEBWIDGET_TRIGGERED = "webwidget_triggered"
    CONTACT_CREATED = "contact_created"
    CONTACT_UPDATED = "contact_updated"
