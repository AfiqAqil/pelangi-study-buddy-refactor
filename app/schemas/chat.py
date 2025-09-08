"""This file contains the chat schema for the application."""

import re
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
    model_validator,
    ValidationInfo,
)


class Message(BaseModel):
    """Message model for chat endpoint.

    Attributes:
        role: The role of the message sender (user, assistant, system, or tool).
        content: The content of the message.
        tool_call_id: ID of the tool call (for tool messages).
        name: Name of the tool (for tool messages).
    """

    model_config = {"extra": "ignore"}

    role: Literal["user", "assistant", "system", "tool"] = Field(..., description="The role of the message sender")
    content: str = Field(..., description="The content of the message")
    tool_call_id: Optional[str] = Field(None, description="ID of the tool call (for tool messages)")
    name: Optional[str] = Field(None, description="Name of the tool (for tool messages)")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls (for assistant messages)")

    @model_validator(mode='after')
    def validate_message(self):
        """Validate the complete message with role-specific rules."""
        role = self.role
        content = self.content
        tool_calls = getattr(self, 'tool_calls', None)
        
        # Tool messages and assistant messages with tool_calls can have empty content
        # Others need at least 1 character
        has_tool_calls = tool_calls and len(tool_calls) > 0
        
        if role not in ["tool"] and not has_tool_calls and len(content) < 1:
            raise ValueError("Content must be at least 1 character for messages without tool_calls")
        
        # Apply role-specific length limits
        if role == "system":
            max_length = 15000  # Allow longer system prompts
        elif role == "tool":
            max_length = 5000   # Allow longer tool responses
        else:
            max_length = 3000   # Limit user/assistant messages
        
        if len(content) > max_length:
            raise ValueError(f"Content exceeds maximum length of {max_length} characters for {role} messages")
        
        # Skip script and null byte validation for tool messages (they might contain technical content)
        if role != "tool":
            # Check for potentially harmful content
            if re.search(r"<script.*?>.*?</script>", content, re.IGNORECASE | re.DOTALL):
                raise ValueError("Content contains potentially harmful script tags")

            # Check for null bytes
            if "\0" in content:
                raise ValueError("Content contains null bytes")

        return self


class ChatRequest(BaseModel):
    """Request model for chat endpoint.

    Attributes:
        messages: List of messages in the conversation.
    """

    messages: List[Message] = Field(
        ...,
        description="List of messages in the conversation",
        min_length=1,
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint.

    Attributes:
        messages: List of messages in the conversation.
    """

    messages: List[Message] = Field(..., description="List of messages in the conversation")


class StreamResponse(BaseModel):
    """Response model for streaming chat endpoint.

    Attributes:
        content: The content of the current chunk.
        done: Whether the stream is complete.
    """

    content: str = Field(default="", description="The content of the current chunk")
    done: bool = Field(default=False, description="Whether the stream is complete")
