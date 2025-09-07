"""Simple phone-based user identification service for Chatwoot integration."""

from datetime import datetime
from typing import Optional
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.user import User
from app.services.database import database_service
from app.schemas.chatwoot import ChatwootContact


class UserIdentificationService:
    """Simple service for identifying users by phone number."""

    def __init__(self):
        """Initialize the user identification service."""
        self.db_service = database_service

    def find_user_by_phone(self, phone: str) -> Optional[User]:
        """Find user by normalized phone number.

        Args:
            phone: Phone number to search for

        Returns:
            Optional[User]: User if found
        """
        normalized_phone = User.normalize_phone(phone)
        if not normalized_phone:
            return None

        with Session(self.db_service.engine) as session:
            statement = select(User).where(User.phone == normalized_phone)
            return session.exec(statement).first()

    def create_user_with_phone(
        self, phone: str, email: Optional[str] = None, name: Optional[str] = None
    ) -> Optional[User]:
        """Create a new user with phone number.

        Args:
            phone: Phone number for the user
            email: Optional email address
            name: Optional name (used for generating email if not provided)

        Returns:
            Optional[User]: Created user or None if phone is invalid
        """
        normalized_phone = User.normalize_phone(phone)
        if not normalized_phone or not User.is_valid_malaysian_phone(normalized_phone):
            logger.warning("user_identification_invalid_phone", phone=phone, normalized=normalized_phone)
            return None

        # Generate email if not provided
        phone_digits = "".join(filter(str.isdigit, normalized_phone))
        if not email:
            # Use phone number to generate a placeholder email
            email = f"user_{phone_digits}@chatwoot.local"

        # Generate a temporary password (user will need to set proper one later)
        temp_password = f"temp_{phone_digits}"
        hashed_password = User.hash_password(temp_password)

        try:
            with Session(self.db_service.engine) as session:
                new_user = User(
                    email=email,
                    phone=normalized_phone,
                    hashed_password=hashed_password,
                )

                session.add(new_user)
                session.commit()
                session.refresh(new_user)

                logger.info("user_identification_created", user_id=new_user.id, phone=normalized_phone, email=email)
                return new_user

        except Exception as e:
            logger.error("user_identification_create_failed", phone=normalized_phone, error=str(e))
            return None

    def find_or_create_user_from_chatwoot(self, contact: ChatwootContact) -> Optional[User]:
        """Find existing user or create new one from Chatwoot contact.

        Args:
            contact: Chatwoot contact data

        Returns:
            Optional[User]: Found or created user, None if no phone available
        """
        if not contact.phone:
            logger.debug("user_identification_no_phone", contact_id=contact.id, email=contact.email)
            return None

        # Try to find existing user
        existing_user = self.find_user_by_phone(contact.phone)
        if existing_user:
            logger.debug("user_identification_found", user_id=existing_user.id, phone=contact.phone)
            return existing_user

        # Create new user with available information
        return self.create_user_with_phone(phone=contact.phone, email=contact.email, name=contact.name)

    def get_user_session_id(self, user_id: int, conversation_id: int) -> str:
        """Generate session ID for user and conversation.

        Args:
            user_id: Database user ID
            conversation_id: Chatwoot conversation ID

        Returns:
            str: Session ID for chat management
        """
        return f"user_{user_id}_conv_{conversation_id}"

    def requires_phone_number(self, contact: ChatwootContact) -> bool:
        """Check if we need to request phone number from user.

        Args:
            contact: Chatwoot contact data

        Returns:
            bool: True if phone number is missing or invalid
        """
        # First check if the contact already has a valid phone
        if contact.phone:
            normalized = User.normalize_phone(contact.phone)
            if normalized and User.is_valid_malaysian_phone(normalized):
                return False
        
        # Check our stored mapping for this contact
        stored_phone = self.get_contact_phone_from_mapping(contact.id)
        if stored_phone:
            # Update the contact object with stored phone for consistency
            contact.phone = stored_phone
            return False
        
        return True

    def extract_phone_from_message(self, message: str) -> Optional[str]:
        """Extract Malaysian phone number from message text.

        Args:
            message: Message content to search for phone numbers

        Returns:
            Optional[str]: Normalized phone number if found and valid
        """
        import re

        # Malaysian phone number patterns (more specific)
        patterns = [
            r"\+60[\d\s\-]{9,12}",  # +60123456789, +60 123 456 789, +60-123-456-789
            r"60[\d\s\-]{9,12}",    # 60123456789, 60 123 456 789
            r"0[\d\s\-]{9,11}",     # 0123456789, 012 345 6789, 012-345-6789
            r"(?<!\d)1[\d\s\-]{8,9}(?!\d)",  # 123456789 (9-10 digits starting with 1, not part of longer number)
        ]

        for pattern in patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                # Remove spaces and dashes before normalizing
                cleaned_match = re.sub(r'[\s\-]', '', match)
                normalized = User.normalize_phone(cleaned_match)
                if normalized and User.is_valid_malaysian_phone(normalized):
                    return normalized

        return None

    def store_contact_phone_mapping(self, contact_id: int, phone: str) -> bool:
        """Store contact ID to phone number mapping in database.

        Args:
            contact_id: Chatwoot contact ID
            phone: Phone number to associate

        Returns:
            bool: True if mapping stored successfully
        """
        from app.models.chatwoot_contact_mapping import ChatwootContactMapping
        
        normalized = User.normalize_phone(phone)
        if not normalized or not User.is_valid_malaysian_phone(normalized):
            return False
        
        try:
            with Session(self.db_service.engine) as session:
                # Check if mapping already exists
                existing = session.exec(
                    select(ChatwootContactMapping).where(ChatwootContactMapping.contact_id == contact_id)
                ).first()
                
                if existing:
                    # Update existing mapping
                    existing.phone = normalized
                    session.add(existing)
                else:
                    # Create new mapping
                    new_mapping = ChatwootContactMapping(
                        contact_id=contact_id,
                        phone=normalized
                    )
                    session.add(new_mapping)
                
                session.commit()
                logger.info("contact_phone_mapping_stored", contact_id=contact_id, phone=normalized)
                return True
                
        except Exception as e:
            logger.error("contact_phone_mapping_store_failed", contact_id=contact_id, phone=normalized, error=str(e))
            return False

    def get_contact_phone_from_mapping(self, contact_id: int) -> Optional[str]:
        """Get phone number for a contact from database mapping.

        Args:
            contact_id: Chatwoot contact ID

        Returns:
            Optional[str]: Phone number if found
        """
        from app.models.chatwoot_contact_mapping import ChatwootContactMapping
        
        try:
            with Session(self.db_service.engine) as session:
                mapping = session.exec(
                    select(ChatwootContactMapping).where(ChatwootContactMapping.contact_id == contact_id)
                ).first()
                
                return mapping.phone if mapping else None
                
        except Exception as e:
            logger.error("contact_phone_mapping_get_failed", contact_id=contact_id, error=str(e))
            return None


# Create singleton instance
user_identification_service = UserIdentificationService()
