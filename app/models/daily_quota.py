"""Daily quota tracking models for users."""

from typing import TYPE_CHECKING, Optional
from datetime import datetime, date

from sqlmodel import Field, Relationship, Column, UniqueConstraint, CheckConstraint
import sqlalchemy as sa

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class TierQuotaConfig(BaseModel, table=True):
    """Configuration for tier-based quotas (quiz and messages).

    Attributes:
        id: The primary key (UUID)
        tier_name: Tier name (unique)
        daily_quiz_limit: Daily quiz question limit (-1 for unlimited)
        daily_quiz_limit_type: Type of quiz limit (default 'questions_attempted')
        daily_message_limit: Daily message limit (-1 for unlimited, 20 for FREE tier)
        daily_message_limit_type: Type of message limit (default 'messages_sent')
        rollover_enabled: Whether unused quotas rollover
        rollover_days: Number of days quotas can rollover
        created_at: When the config was created
        updated_at: When the config was last updated
    """

    __tablename__ = "tier_quota_configs"

    id: str = Field(default=None, primary_key=True)
    tier_name: str = Field(unique=True, max_length=20, description="Tier name")
    daily_quiz_limit: int = Field(description="Daily quiz question limit (-1 for unlimited)")
    daily_quiz_limit_type: str = Field(default="questions_attempted", max_length=20, description="Type of quiz limit")
    daily_message_limit: Optional[int] = Field(default=None, description="Daily message limit (-1 for unlimited)")
    daily_message_limit_type: Optional[str] = Field(
        default="messages_sent", max_length=50, description="Type of message limit"
    )
    rollover_enabled: bool = Field(default=False, description="Whether unused quotas rollover")
    rollover_days: int = Field(default=0, description="Number of days quotas can rollover")
    updated_at: Optional[datetime] = Field(
        default=None, sa_column=Column(sa.DateTime(timezone=True), onupdate=sa.func.now())
    )


class DailyQuizQuota(BaseModel, table=True):
    """Daily quiz quota tracking for users.

    Attributes:
        id: The primary key (UUID)
        user_id: Foreign key to users table
        quota_date: Date in GMT+8 timezone
        questions_attempted: Number of questions attempted
        questions_answered: Number of questions answered
        last_question_at: Timestamp of last question attempt
        created_at: When the quota record was created
        updated_at: When the quota record was last updated

        # Relationships
        user: Relationship to User model
    """

    __tablename__ = "daily_quiz_quotas"

    id: str = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    quota_date: date = Field(index=True, description="Date in GMT+8 timezone")
    questions_attempted: int = Field(default=0, description="Number of questions attempted")
    questions_answered: int = Field(default=0, description="Number of questions answered")
    last_question_at: Optional[datetime] = Field(default=None, sa_column=Column(sa.DateTime(timezone=True)))
    updated_at: Optional[datetime] = Field(
        default=None, sa_column=Column(sa.DateTime(timezone=True), onupdate=sa.func.now())
    )

    # Relationships
    user: "User" = Relationship(back_populates="daily_quotas")

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "quota_date", name="uq_user_date"),
        CheckConstraint("questions_attempted >= 0 AND questions_answered >= 0", name="positive_quotas"),
    )


class DailyUserQuota(BaseModel, table=True):
    """Unified daily quota tracking for users (quiz and messages).

    Attributes:
        id: The primary key (UUID)
        user_id: Foreign key to users table
        quota_date: Date in GMT+8 timezone
        quota_type: Type of quota ('quiz' or 'message')
        count: Current count for the quota
        last_used_at: Timestamp of last usage
        created_at: When the quota record was created
        updated_at: When the quota record was last updated

        # Relationships
        user: Relationship to User model
    """

    __tablename__ = "daily_user_quotas"

    id: str = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    quota_date: date = Field(index=True, description="Date in GMT+8 timezone")
    quota_type: str = Field(max_length=50, index=True, description="Type of quota ('quiz' or 'message')")
    count: int = Field(default=0, description="Current count for the quota")
    last_used_at: Optional[datetime] = Field(default=None, sa_column=Column(sa.DateTime(timezone=True)))
    updated_at: Optional[datetime] = Field(
        default=None, sa_column=Column(sa.DateTime(timezone=True), onupdate=sa.func.now())
    )

    # Relationships
    user: "User" = Relationship(back_populates="daily_user_quotas")

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "quota_date", "quota_type", name="uq_user_date_type"),
        CheckConstraint("count >= 0", name="positive_count"),
    )
