"""Message model for storing conversation messages."""

from datetime import datetime, UTC
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum

from sqlmodel import Field, SQLModel, JSON, Relationship

if TYPE_CHECKING:
    from app.models.thread import Thread
    from app.models.user import User


class MessageRole(str, Enum):
    """Message role enumeration."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(SQLModel, table=True):
    """Message model for storing individual messages in conversations.

    Attributes:
        id: Primary key
        thread_id: Foreign key to threads table (indexed)
        user_id: Foreign key to users table (indexed)  
        role: Message role (user, assistant, system, tool)
        content: Message content
        metadata: Additional metadata (tool calls, etc.)
        created_at: When the message was created (indexed)
        is_deleted: Soft delete flag (indexed)
        token_count: Number of tokens in the message (for billing/limits)
    """

    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(foreign_key="threads.id", index=True)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    role: MessageRole = Field(index=True, description="Message role")
    content: str = Field(description="Message content")
    message_metadata: Optional[Dict[str, Any]] = Field(
        default=None, 
        sa_type=JSON,
        description="Additional metadata like tool calls, function arguments, etc."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
        description="When the message was created"
    )
    is_deleted: bool = Field(
        default=False,
        index=True, 
        description="Soft delete flag"
    )
    token_count: Optional[int] = Field(
        default=None,
        description="Number of tokens in the message content"
    )

    # Relationships (will be enabled when other models are ready)

    def to_chat_format(self) -> Dict[str, Any]:
        """Convert to chat format for LLM APIs.
        
        Returns:
            Dict in the format expected by LLM APIs
        """
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        
        # Add metadata if present (e.g., tool calls)
        if self.message_metadata:
            result.update(self.message_metadata)
            
        return result

    def calculate_tokens(self) -> int:
        """Estimate token count for this message.
        
        Returns:
            Estimated token count (rough approximation)
        """
        # Simple approximation: 1 token ≈ 4 characters
        # More sophisticated tokenization can be added later
        return len(self.content) // 4

    def mark_deleted(self) -> None:
        """Mark message as deleted (soft delete)."""
        self.is_deleted = True