"""This file contains the chat schema for the application."""

import re
from typing import (
    List,
    Literal,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ValidationInfo,
)


class Message(BaseModel):
    """Message model for chat endpoint.

    Attributes:
        role: The role of the message sender (user or assistant).
        content: The content of the message.
    """

    model_config = {"extra": "ignore"}

    role: Literal["user", "assistant", "system"] = Field(..., description="The role of the message sender")
    content: str = Field(..., description="The content of the message", min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str, info: ValidationInfo) -> str:
        """Validate the message content with role-specific length limits.

        Args:
            v: The content to validate
            info: ValidationInfo containing field data

        Returns:
            str: The validated content

        Raises:
            ValueError: If the content contains disallowed patterns or exceeds length limits
        """
        # Get role from the model data
        role = info.data.get("role") if info.data else None
        
        # Apply role-specific length limits
        if role == "system":
            max_length = 15000  # Allow longer system prompts
        else:
            max_length = 3000   # Limit user/assistant messages
        
        if len(v) > max_length:
            raise ValueError(f"Content exceeds maximum length of {max_length} characters for {role} messages")
        
        # Check for potentially harmful content
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("Content contains potentially harmful script tags")

        # Check for null bytes
        if "\0" in v:
            raise ValueError("Content contains null bytes")

        return v


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
