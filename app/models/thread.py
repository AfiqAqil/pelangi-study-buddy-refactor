"""This file contains the thread model for the application."""

from datetime import (
    UTC,
    datetime,
)
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)

if TYPE_CHECKING:
    from app.models.user import User


class Thread(SQLModel, table=True):
    """Thread model for storing conversation threads.

    Attributes:
        id: The primary key
        user_id: Foreign key to users table
        created_at: When the thread was created (indexed for time-based queries)
        is_active: Whether the thread is active (indexed for filtering)
        title: Optional thread title for display
        user: Relationship to User model
    """

    __tablename__ = "threads"

    id: str = Field(primary_key=True)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), 
        index=True,  # Index for time-based queries like "recent threads"
        description="When the thread was created"
    )
    is_active: bool = Field(
        default=True, 
        index=True,  # Index for filtering active/inactive threads
        description="Whether the thread is currently active"
    )
    title: Optional[str] = Field(default=None, max_length=255)

    # Relationships (will be set up when User model is available)
