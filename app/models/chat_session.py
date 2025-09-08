"""ChatSession model for comprehensive chat session management."""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime

from sqlmodel import Field, Relationship, Column
import sqlalchemy as sa

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.chat_session_message import ChatSessionMessage
    from app.models.quiz_attempt import QuizAttempt
    from app.models.spot_question_attempt import SpotQuestionAttempt


class ChatSession(BaseModel, table=True):
    """ChatSession model for storing comprehensive chat sessions.

    Attributes:
        session_id: The primary key (UUID)
        user_id: Foreign key to users table (required)
        external_user_id: External user identifier (e.g., WhatsApp number, web user ID)
        channel: Communication channel ('web' or 'whatsapp')
        last_message_at: Timestamp of last message (optional)
        ended_at: Timestamp when session ended (optional)
        total_messages: Total number of messages in session
        created_at: When the session was created

        # Chatwoot-specific fields
        chatwoot_conversation_id: Chatwoot conversation ID (unique)
        chatwoot_inbox_id: Chatwoot inbox ID
        chatwoot_status: Chatwoot status ('open', 'resolved', 'pending')

        # Relationships
        user: Relationship to User model
        messages: Relationship to ChatSessionMessage model
        quiz_attempts: Relationship to QuizAttempt model
        spot_question_attempts: Relationship to SpotQuestionAttempt model
    """

    __tablename__ = "chat_sessions"

    session_id: str = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    external_user_id: Optional[str] = Field(default=None, index=True, description="External user identifier")
    channel: str = Field(index=True, description="Communication channel ('web' or 'whatsapp')")
    last_message_at: Optional[datetime] = Field(default=None, sa_column=Column(sa.DateTime(timezone=True)))
    ended_at: Optional[datetime] = Field(default=None, sa_column=Column(sa.DateTime(timezone=True)))
    total_messages: int = Field(default=0, description="Total number of messages in session")

    # Chatwoot-specific fields
    chatwoot_conversation_id: Optional[int] = Field(default=None, unique=True, description="Chatwoot conversation ID")
    chatwoot_inbox_id: Optional[int] = Field(default=None, description="Chatwoot inbox ID")
    chatwoot_status: Optional[str] = Field(default=None, description="Chatwoot status")

    # Relationships
    user: "User" = Relationship(back_populates="chat_sessions")
    messages: List["ChatSessionMessage"] = Relationship(back_populates="session")
    quiz_attempts: List["QuizAttempt"] = Relationship(back_populates="session")
    spot_question_attempts: List["SpotQuestionAttempt"] = Relationship(back_populates="session")
