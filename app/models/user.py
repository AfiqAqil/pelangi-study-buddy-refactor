"""This file contains the user model for the application."""

from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)
from datetime import date, datetime
from enum import Enum

import uuid
import bcrypt
from sqlmodel import (
    Field,
    Relationship,
    Column,
    JSON,
)
import sqlalchemy as sa

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.chat_session import ChatSession
    from app.models.quiz_attempt import QuizAttempt
    from app.models.spot_question_attempt import SpotQuestionAttempt
    from app.models.daily_quota import DailyQuizQuota, DailyUserQuota


class UserTier(str, Enum):
    """User tier enumeration for subscription levels."""
    FREE = "FREE"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"


class User(BaseModel, table=True):
    """User model for storing user accounts.

    Attributes:
        id: The primary key (UUID)
        external_id: External user ID from WhatsApp/Web
        channel: Communication channel ('web' or 'whatsapp')
        tier: User subscription tier (FREE, PREMIUM, ENTERPRISE)
        email: User's email (unique, optional)
        phone: User's phone number (Malaysian +60 format, unique)
        hashed_password: Bcrypt hashed password
        created_at: When the user was created
        updated_at: When the user was last updated
        
        # Onboarding and profile fields
        full_name: User's full name
        date_of_birth: User's date of birth
        current_subjects: List of subjects currently studying (JSONB)
        focus_subjects: Subjects user wants help with most (JSONB)
        form_level: School form level (1-5)
        year: School year (text/number)
        school_name: Name of the school
        language: Preferred language (English, Bahasa Malaysia, Chinese)
        student_id: Optional student ID
        onboarding_completed: Whether onboarding is complete
        
        # Chatwoot-specific fields
        chatwoot_user_id: Chatwoot's user ID
        chatwoot_contact_id: Chatwoot's contact ID
        chatwoot_account_id: Chatwoot account ID
        
        # Relationships
        sessions: Relationship to user's chat sessions
        chat_sessions: Relationship to user's enhanced chat sessions
        quiz_attempts: Relationship to user's quiz attempts
        spot_question_attempts: Relationship to user's spot question attempts
        daily_quotas: Relationship to user's daily quiz quotas
        daily_user_quotas: Relationship to user's daily user quotas
    """

    __tablename__ = "users"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    external_id: str = Field(unique=True, index=True)
    channel: str = Field(index=True)  # 'web' or 'whatsapp'
    tier: UserTier = Field(default=UserTier.FREE, index=True)
    
    # Authentication fields
    email: Optional[str] = Field(default=None, unique=True, index=True)
    phone: Optional[str] = Field(default=None, unique=True, index=True)
    hashed_password: Optional[str] = Field(default=None)
    
    # Audit fields
    updated_at: Optional[datetime] = Field(default=None, sa_column=Column(sa.DateTime(timezone=True), onupdate=sa.func.now()))
    
    # Onboarding and profile fields
    full_name: Optional[str] = Field(default=None)
    date_of_birth: Optional[date] = Field(default=None)
    current_subjects: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    focus_subjects: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    form_level: Optional[int] = Field(default=None)  # 1-5 for Form 1-5
    year: Optional[str] = Field(default=None)  # School year
    school_name: Optional[str] = Field(default=None)
    language: str = Field(default="English")  # "English", "Bahasa Malaysia", "Chinese"
    student_id: Optional[str] = Field(default=None)
    onboarding_completed: bool = Field(default=False)
    
    # Chatwoot-specific fields
    chatwoot_user_id: Optional[int] = Field(default=None, unique=True)
    chatwoot_contact_id: Optional[int] = Field(default=None)
    chatwoot_account_id: Optional[int] = Field(default=None)
    
    # Relationships
    sessions: List["Session"] = Relationship(back_populates="user")
    chat_sessions: List["ChatSession"] = Relationship(back_populates="user")
    quiz_attempts: List["QuizAttempt"] = Relationship(back_populates="user")
    spot_question_attempts: List["SpotQuestionAttempt"] = Relationship(back_populates="user")
    daily_quotas: List["DailyQuizQuota"] = Relationship(back_populates="user")
    daily_user_quotas: List["DailyUserQuota"] = Relationship(back_populates="user")

    def verify_password(self, password: str) -> bool:
        """Verify if the provided password matches the hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def normalize_phone(phone: str) -> Optional[str]:
        """Normalize phone number to Malaysian +60 format."""
        if not phone:
            return None

        # Remove all non-digit characters
        digits = "".join(filter(str.isdigit, phone))

        # Handle different Malaysian phone number formats
        if digits.startswith("60") and len(digits) >= 11:
            # Already has country code - ensure it's 60 + 9-10 digits  
            if len(digits) >= 11 and len(digits) <= 12:
                return f"+{digits}"
        elif digits.startswith("0") and len(digits) >= 10:
            # Remove leading 0 and add country code - 0 + 9-10 digits
            if len(digits) >= 10 and len(digits) <= 11:
                return f"+60{digits[1:]}"
        elif len(digits) >= 9 and len(digits) <= 10 and digits.startswith("1"):
            # Missing country code - Malaysian mobile numbers start with 1
            return f"+60{digits}"

        return None

    @staticmethod
    def is_valid_malaysian_phone(phone: str) -> bool:
        """Check if phone number is a valid Malaysian format."""
        if not phone:
            return False

        normalized = User.normalize_phone(phone)
        if not normalized:
            return False

        # Malaysian phone numbers should be +60 followed by 9-10 digits
        digits = normalized[3:]  # Remove +60
        return len(digits) >= 9 and len(digits) <= 10 and digits.isdigit()


# Avoid circular imports
from app.models.session import Session  # noqa: E402
