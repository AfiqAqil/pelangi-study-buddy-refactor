"""Simple phone-based user identification service for Chatwoot integration."""

from typing import Optional
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.user import User
from app.services.database import database_service
from app.schemas.chatwoot import ChatwootContact, ChatwootMessageWebhook


class UserIdentificationService:
    """Simple service for identifying users by phone number."""

    def __init__(self):
        """Initialize the user identification service."""
        self.db_service = database_service
        # Simple in-memory cache for contact phone mappings (contact_id -> phone)
        self._phone_cache: dict[int, str] = {}

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
            import uuid

            # Generate external_id for WhatsApp users
            external_id = f"whatsapp_{uuid.uuid4().hex[:12]}"

            with Session(self.db_service.engine) as session:
                new_user = User(
                    email=email,
                    phone=normalized_phone,
                    hashed_password=hashed_password,
                    external_id=external_id,
                    channel="whatsapp",
                    tier="FREE",  # Default tier
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

    def get_user_session_id(self, user_id: str, conversation_id: int) -> str:
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
        logger.debug(
            "requires_phone_number_check_start",
            contact_id=contact.id,
            contact_phone=contact.phone,
            contact_identifier=contact.identifier,
        )

        # First check if the contact already has a valid phone
        if contact.phone:
            normalized = User.normalize_phone(contact.phone)
            if normalized and User.is_valid_malaysian_phone(normalized):
                logger.debug("phone_valid_in_contact_phone_field", contact_id=contact.id, phone=normalized)
                return False

        # Check for phone number in contact custom attributes (WhatsApp channels)
        phone_from_attributes = self._extract_phone_from_contact_attributes(contact)
        if phone_from_attributes:
            # Update the contact object with found phone for consistency
            contact.phone = phone_from_attributes
            logger.debug("phone_found_in_attributes", contact_id=contact.id, phone=phone_from_attributes)
            return False

        # Check if the contact identifier is a phone number (WhatsApp channels)
        phone_from_identifier = self._extract_phone_from_identifier(contact)
        if phone_from_identifier:
            # Update the contact object with found phone for consistency
            contact.phone = phone_from_identifier
            logger.debug("phone_found_in_identifier", contact_id=contact.id, phone=phone_from_identifier)
            return False

        # Check our stored mapping for this contact
        stored_phone = self.get_contact_phone_from_mapping(contact.id)
        if stored_phone:
            # Update the contact object with stored phone for consistency
            contact.phone = stored_phone
            logger.debug("phone_found_in_mapping", contact_id=contact.id, phone=stored_phone)
            return False

        logger.info("phone_number_required", contact_id=contact.id)
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
            r"60[\d\s\-]{9,12}",  # 60123456789, 60 123 456 789
            r"0[\d\s\-]{9,11}",  # 0123456789, 012 345 6789, 012-345-6789
            r"(?<!\d)1[\d\s\-]{8,9}(?!\d)",  # 123456789 (9-10 digits starting with 1, not part of longer number)
        ]

        for pattern in patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                # Remove spaces and dashes before normalizing
                cleaned_match = re.sub(r"[\s\-]", "", match)
                normalized = User.normalize_phone(cleaned_match)
                if normalized and User.is_valid_malaysian_phone(normalized):
                    return normalized

        return None

    def _extract_phone_from_contact_attributes(self, contact: ChatwootContact) -> Optional[str]:
        """Extract phone number from contact custom attributes.

        Simple check for phone number in contact custom attributes.

        Args:
            contact: Chatwoot contact data

        Returns:
            Optional[str]: Normalized phone number if found and valid
        """
        if not contact.custom_attributes:
            return None

        # Check for phone_number in custom attributes
        if "phone_number" in contact.custom_attributes:
            phone_value = contact.custom_attributes["phone_number"]
            if isinstance(phone_value, str) and phone_value.strip():
                normalized = User.normalize_phone(phone_value.strip())
                if normalized and User.is_valid_malaysian_phone(normalized):
                    logger.info("phone_found_in_custom_attributes", contact_id=contact.id, phone=normalized)
                    return normalized

        return None

    def _extract_phone_from_identifier(self, contact: ChatwootContact) -> Optional[str]:
        """Extract phone number from contact identifier.

        WhatsApp and similar channels often use phone numbers as contact identifiers.

        Args:
            contact: Chatwoot contact data

        Returns:
            Optional[str]: Normalized phone number if found and valid
        """
        if not contact.identifier:
            return None

        # Try to extract phone number from identifier
        # WhatsApp identifiers are often just phone numbers
        identifier = contact.identifier.strip()

        # Try direct normalization first
        normalized = User.normalize_phone(identifier)
        if normalized and User.is_valid_malaysian_phone(normalized):
            logger.info("phone_found_in_identifier", contact_id=contact.id, identifier=identifier, phone=normalized)
            return normalized

        # If direct normalization fails, try extracting phone patterns
        extracted = self.extract_phone_from_message(identifier)
        if extracted:
            logger.info(
                "phone_extracted_from_identifier_pattern",
                contact_id=contact.id,
                identifier=identifier,
                phone=extracted,
            )
            return extracted

        return None

    def extract_phone_from_webhook_meta(self, webhook_data: ChatwootMessageWebhook) -> Optional[str]:
        """Extract phone number from webhook conversation meta data.

        WhatsApp channels store the phone number in conversation.meta.sender.phone_number

        Args:
            webhook_data: Full Chatwoot webhook data

        Returns:
            Optional[str]: Normalized phone number if found and valid
        """
        try:
            # Access the conversation meta data
            meta = webhook_data.conversation.meta
            if not meta or not isinstance(meta, dict):
                return None

            # Look for sender information in meta
            sender_meta = meta.get("sender")
            if not sender_meta or not isinstance(sender_meta, dict):
                return None

            # Extract phone_number from sender meta
            phone_value = sender_meta.get("phone_number")
            if isinstance(phone_value, str) and phone_value.strip():
                normalized = User.normalize_phone(phone_value.strip())
                if normalized and User.is_valid_malaysian_phone(normalized):
                    logger.info(
                        "phone_found_in_webhook_meta",
                        contact_id=webhook_data.sender.id,
                        conversation_id=webhook_data.conversation.id,
                        phone=normalized,
                    )
                    return normalized

        except (AttributeError, KeyError, TypeError) as e:
            logger.debug(
                "phone_extraction_from_meta_failed", conversation_id=webhook_data.conversation.id, error=str(e)
            )

        return None

    def store_contact_phone_mapping(self, contact_id: int, phone: str) -> bool:
        """Store contact ID to phone number mapping in database and cache.

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

        # Update cache immediately
        self._phone_cache[contact_id] = normalized

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
                    new_mapping = ChatwootContactMapping(contact_id=contact_id, phone=normalized)
                    session.add(new_mapping)

                session.commit()
                logger.info("contact_phone_mapping_stored", contact_id=contact_id, phone=normalized)
                return True

        except Exception as e:
            # Remove from cache on failure
            self._phone_cache.pop(contact_id, None)
            logger.error("contact_phone_mapping_store_failed", contact_id=contact_id, phone=normalized, error=str(e))
            return False

    def get_contact_phone_from_mapping(self, contact_id: int) -> Optional[str]:
        """Get phone number for a contact from cache or database mapping.

        Args:
            contact_id: Chatwoot contact ID

        Returns:
            Optional[str]: Phone number if found
        """
        # Check cache first
        if contact_id in self._phone_cache:
            return self._phone_cache[contact_id]

        from app.models.chatwoot_contact_mapping import ChatwootContactMapping

        try:
            with Session(self.db_service.engine) as session:
                mapping = session.exec(
                    select(ChatwootContactMapping).where(ChatwootContactMapping.contact_id == contact_id)
                ).first()

                if mapping and mapping.phone:
                    # Update cache with database result
                    self._phone_cache[contact_id] = mapping.phone
                    return mapping.phone

                return None

        except Exception as e:
            logger.error("contact_phone_mapping_get_failed", contact_id=contact_id, error=str(e))
            return None


# Create singleton instance
user_identification_service = UserIdentificationService()
