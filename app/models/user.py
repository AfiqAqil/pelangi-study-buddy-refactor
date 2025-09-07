"""This file contains the user model for the application."""

from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)

import bcrypt
from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class User(BaseModel, table=True):
    """User model for storing user accounts.

    Attributes:
        id: The primary key
        email: User's email (unique)
        phone: User's phone number (Malaysian +60 format, unique)
        hashed_password: Bcrypt hashed password
        created_at: When the user was created
        sessions: Relationship to user's chat sessions
    """

    id: int = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    phone: Optional[str] = Field(default=None, unique=True, index=True)
    hashed_password: str
    sessions: List["Session"] = Relationship(back_populates="user")

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
