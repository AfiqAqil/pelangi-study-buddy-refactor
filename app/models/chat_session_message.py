"""ChatSessionMessage model for individual messages within chat sessions."""

from typing import TYPE_CHECKING, Optional, Dict, Any

from sqlmodel import Field, Relationship, Column, JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession


class ChatSessionMessage(BaseModel, table=True):
    """ChatSessionMessage model for storing individual messages within chat sessions.

    Attributes:
        id: The primary key (UUID)
        session_id: Foreign key to chat_sessions table
        message_index: Optional message index within the session
        role: Message role ('user', 'assistant', 'system')
        content: Message content
        feedback: User feedback ('like', 'dislike', optional)
        feedback_text: User's text feedback (optional)
        rag_chunks: RAG chunks used for the message (JSON, optional)
        created_at: When the message was created

        # Chatwoot-specific fields
        chatwoot_message_id: Chatwoot message ID (unique)
        chatwoot_message_type: Chatwoot message type ('incoming', 'outgoing', 'template')
        chatwoot_content_type: Chatwoot content type ('text', 'input_select', 'cards', 'form')
        chatwoot_source_id: External source ID from Chatwoot

        # Relationships
        session: Relationship to ChatSession model
    """

    __tablename__ = "chat_session_messages"

    id: str = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chat_sessions.session_id", index=True)
    message_index: Optional[int] = Field(default=None, description="Message index within the session")
    role: str = Field(index=True, description="Message role ('user', 'assistant', 'system')")
    content: str = Field(description="Message content")
    feedback: Optional[str] = Field(default=None, description="User feedback ('like', 'dislike')")
    feedback_text: Optional[str] = Field(default=None, description="User's text feedback")
    rag_chunks: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON), description="RAG chunks used")

    # Chatwoot-specific fields
    chatwoot_message_id: Optional[int] = Field(default=None, unique=True, description="Chatwoot message ID")
    chatwoot_message_type: Optional[str] = Field(default=None, description="Chatwoot message type")
    chatwoot_content_type: Optional[str] = Field(default=None, description="Chatwoot content type")
    chatwoot_source_id: Optional[str] = Field(default=None, description="External source ID from Chatwoot")

    # Relationships
    session: "ChatSession" = Relationship(back_populates="messages")
