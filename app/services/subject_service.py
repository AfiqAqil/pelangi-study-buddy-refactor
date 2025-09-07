"""Subject management service for handling subject selection and filtering."""

from typing import List, Optional, Dict, Any
from sqlmodel import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import logger
from app.models.subject import Subject
from app.models.user import User
from app.services.database import database_service


class SubjectService:
    """Service for managing subjects and subject selection."""

    def __init__(self):
        """Initialize subject service."""
        self.fallback_subjects = self._get_fallback_subjects()

    def _get_fallback_subjects(self) -> List[Dict[str, Any]]:
        """Get hardcoded fallback subjects when database is unavailable."""
        return [
            {
                "id": "1",
                "name": "Focus SPM Biology",
                "description": "SPM Biology preparation",
                "book_code": "ePDF FOCUS SPM (2025) BIOLOGY AAEVSB2572004A.pdf",
                "alt_names": ["Biology", "Bio", "Biologi"],
            },
            {
                "id": "2",
                "name": "Focus SPM Chemistry",
                "description": "SPM Chemistry preparation",
                "book_code": "ePDF FOCUS SPM (2025) CHEMISTRY AAEVSC2572004A.pdf",
                "alt_names": ["Chemistry", "Chem", "Kimia"],
            },
            {
                "id": "3",
                "name": "Focus SPM Physics",
                "description": "SPM Physics preparation",
                "book_code": "ePDF FOCUS SPM (2025) PHYSICS AAEVSP2572004A.pdf",
                "alt_names": ["Physics", "Fizik"],
            },
            {
                "id": "4",
                "name": "Focus SPM Mathematics",
                "description": "SPM Mathematics preparation",
                "book_code": "ePDF FOCUS SPM (2025) MATHEMATICS AAEVMM2572004A.pdf",
                "alt_names": ["Mathematics", "Math", "Maths", "Matematik"],
            },
            {
                "id": "5",
                "name": "Focus SPM Science",
                "description": "SPM Science preparation",
                "book_code": "ePDF FOCUS SPM (2025) SCIENCE AAEVSN2572004A.pdf",
                "alt_names": ["Science", "Sains"],
            },
            {
                "id": "6",
                "name": "Focus SPM Matematik",
                "description": "SPM Matematik preparation",
                "book_code": "ePDF FOCUS SPM (2025) MATEMATIK AAMVMM2572004A.pdf",
                "alt_names": ["Matematik", "Mathematics", "Math", "Maths"],
            },
            {
                "id": "7",
                "name": "Focus SPM Matematik Tambah",
                "description": "SPM Additional Mathematics preparation",
                "book_code": "ePDF FOCUS SPM (2025) MATEMATIK TAMBAHAN AAMVMB2572004A.pdf",
                "alt_names": ["Matematik Tambahan", "Additional Mathematics", "Add Math", "Add Maths"],
            },
            {
                "id": "8",
                "name": "Focus SPM Sains",
                "description": "SPM Sains preparation",
                "book_code": "ePDF FOCUS SPM (2025) SAINS AAMVSN2572004A.pdf",
                "alt_names": ["Sains", "Science"],
            },
            {
                "id": "9",
                "name": "Focus SPM Kimia",
                "description": "SPM Kimia preparation",
                "book_code": "ePDF FOCUS SPM (2025) KIMIA AAMVSC2572004A.pdf",
                "alt_names": ["Kimia", "Chemistry", "Chem"],
            },
            {
                "id": "10",
                "name": "Focus SPM Fizik",
                "description": "SPM Fizik preparation",
                "book_code": "ePDF FOCUS SPM (2025) FIZIK AAMVSP2572004A.pdf",
                "alt_names": ["Fizik", "Physics"],
            },
            {
                "id": "11",
                "name": "Focus SPM Sejarah",
                "description": "SPM Sejarah preparation",
                "book_code": "ePDF FOCUS SPM (2025) SEJARAH AAMVSJ2572004A.pdf",
                "alt_names": ["Sejarah", "History"],
            },
        ]

    async def get_available_subjects(
        self, form_level: Optional[int] = None, language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get list of available subjects with filtering options.

        Args:
            form_level: Filter subjects by form level (1-5)
            language: Filter subjects by language preference

        Returns:
            List of subject dictionaries with formatting
        """
        try:
            with database_service.get_session_maker() as session:
                statement = select(Subject)
                subjects = session.exec(statement).all()

                if not subjects:
                    logger.warning("no_subjects_in_database_using_fallback")
                    return self._format_fallback_subjects(form_level, language)

                return self._format_subjects(subjects, form_level, language)

        except SQLAlchemyError as e:
            logger.error("database_error_getting_subjects", error=str(e))
            return self._format_fallback_subjects(form_level, language)
        except Exception as e:
            logger.error("unexpected_error_getting_subjects", error=str(e))
            return self._format_fallback_subjects(form_level, language)

    async def find_subject_by_name_or_number(self, input_str: str) -> Optional[Dict[str, Any]]:
        """Find subject by name, alternative name, or number.

        Args:
            input_str: User input (subject name, number, or alternative)

        Returns:
            Subject dictionary if found, None otherwise
        """
        if not input_str or not input_str.strip():
            return None

        input_str = input_str.strip()

        try:
            with database_service.get_session_maker() as session:
                statement = select(Subject)
                subjects = session.exec(statement).all()

                if not subjects:
                    logger.warning("no_subjects_in_database_using_fallback_for_search")
                    return self._search_fallback_subjects(input_str)

                return self._search_subjects(subjects, input_str)

        except SQLAlchemyError as e:
            logger.error("database_error_searching_subjects", error=str(e))
            return self._search_fallback_subjects(input_str)
        except Exception as e:
            logger.error("unexpected_error_searching_subjects", error=str(e))
            return self._search_fallback_subjects(input_str)

    def _normalize_user_id(self, user_id: str) -> str:
        """Normalize user ID by removing common prefixes.

        The LangGraph agent may inject user IDs with 'user_' prefix,
        but the database stores UUIDs without prefixes.

        Args:
            user_id: Raw user ID that may have prefix

        Returns:
            Normalized user ID without prefix
        """
        if user_id.startswith("user_"):
            normalized_id = user_id[5:]  # Remove 'user_' prefix
            logger.debug("user_id_normalized", original=user_id, normalized=normalized_id)
            return normalized_id
        return user_id

    async def set_user_focus_subject(self, user_id: str, subject_id: str) -> bool:
        """Set user's current focus subject.

        Args:
            user_id: User ID (may have 'user_' prefix from LangGraph agent)
            subject_id: Subject ID to set as focus

        Returns:
            True if successful, False otherwise
        """
        try:
            # Normalize user ID to handle prefixes from different sources
            normalized_user_id = self._normalize_user_id(user_id)

            with database_service.get_session_maker() as session:
                user = session.get(User, normalized_user_id)
                if not user:
                    logger.error(
                        "user_not_found_for_subject_selection", user_id=user_id, normalized_user_id=normalized_user_id
                    )
                    return False

                # Verify subject exists
                subject = session.get(Subject, subject_id)
                if not subject:
                    # Check fallback subjects
                    fallback_subject = next((s for s in self.fallback_subjects if s["id"] == subject_id), None)
                    if not fallback_subject:
                        logger.error("subject_not_found_for_selection", subject_id=subject_id)
                        return False
                    subject_name = fallback_subject["name"]
                else:
                    subject_name = subject.name

                # Update user's current subjects
                if user.current_subjects is None:
                    user.current_subjects = []

                # Remove subject if already exists, then add to front
                user.current_subjects = [s for s in user.current_subjects if s != subject_name]
                user.current_subjects.insert(0, subject_name)

                # Keep only top 3 current subjects
                user.current_subjects = user.current_subjects[:3]

                # Update focus subjects
                if user.focus_subjects is None:
                    user.focus_subjects = []

                # Set as primary focus subject
                user.focus_subjects = [s for s in user.focus_subjects if s != subject_name]
                user.focus_subjects.insert(0, subject_name)
                user.focus_subjects = user.focus_subjects[:5]  # Keep top 5 focus subjects

                session.add(user)
                session.commit()

                logger.info("user_focus_subject_updated", user_id=user_id, subject_name=subject_name)
                return True

        except SQLAlchemyError as e:
            logger.error("database_error_setting_focus_subject", error=str(e), user_id=user_id)
            return False
        except Exception as e:
            logger.error("unexpected_error_setting_focus_subject", error=str(e), user_id=user_id)
            return False

    async def get_user_current_subject(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's current primary focus subject.

        Args:
            user_id: User ID

        Returns:
            Subject dictionary if found, None otherwise
        """
        try:
            with database_service.get_session_maker() as session:
                user = session.get(User, user_id)
                if not user or not user.current_subjects or len(user.current_subjects) == 0:
                    return None

                current_subject_name = user.current_subjects[0]

                # First try to find in database
                statement = select(Subject).where(Subject.name == current_subject_name)
                subject = session.exec(statement).first()

                if subject:
                    return {
                        "id": subject.id,
                        "name": subject.name,
                        "description": subject.description,
                        "book_code": subject.book_code,
                    }

                # Fall back to hardcoded subjects
                fallback_subject = next((s for s in self.fallback_subjects if s["name"] == current_subject_name), None)
                if fallback_subject:
                    return fallback_subject

                return None

        except SQLAlchemyError as e:
            logger.error("database_error_getting_current_subject", error=str(e), user_id=user_id)
            return None
        except Exception as e:
            logger.error("unexpected_error_getting_current_subject", error=str(e), user_id=user_id)
            return None

    def format_subject_selection_message(self, subjects: List[Dict[str, Any]], context: str = "") -> str:
        """Format subjects into a user-friendly selection message.

        Args:
            subjects: List of subject dictionaries
            context: Additional context for the message

        Returns:
            Formatted message string
        """
        if not subjects:
            return "🔍 No subjects are currently available. Please try again later."

        message = "📚 **Available Subjects:**\n\n"

        for i, subject in enumerate(subjects, 1):
            name = subject["name"]
            description = subject.get("description", "")

            # Create bilingual display
            alt_names = subject.get("alt_names", [])
            if alt_names:
                display_name = f"{name} ({', '.join(alt_names[:2])})"
            else:
                display_name = name

            message += f"{i}. **{display_name}**"
            if description:
                message += f" - {description}"
            message += "\n"

        message += "\n💬 You can select a subject by:\n"
        message += '• Saying the subject name: *"I want to learn Biology"*\n'
        message += '• Using the number: *"Subject 1"* or *"1"*\n'
        message += '• Using alternative names: *"Bio"*, *"Fizik"*, etc.\n'

        if context:
            message += f"\n{context}"

        return message

    def _format_subjects(
        self, subjects: List[Subject], form_level: Optional[int], language: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Format database subjects into dictionaries."""
        formatted = []
        for subject in subjects:
            # Get alternative names from fallback data
            fallback = next((s for s in self.fallback_subjects if s["name"] == subject.name), None)
            alt_names = fallback.get("alt_names", []) if fallback else []

            formatted.append(
                {
                    "id": subject.id,
                    "name": subject.name,
                    "description": subject.description,
                    "book_code": subject.book_code,
                    "alt_names": alt_names,
                }
            )

        return formatted

    def _format_fallback_subjects(self, form_level: Optional[int], language: Optional[str]) -> List[Dict[str, Any]]:
        """Format fallback subjects with optional filtering."""
        # For now, return all fallback subjects
        # Future enhancement: implement form_level and language filtering
        return self.fallback_subjects.copy()

    def _search_subjects(self, subjects: List[Subject], input_str: str) -> Optional[Dict[str, Any]]:
        """Search database subjects by name or number."""
        # Try number-based selection first
        if input_str.isdigit():
            index = int(input_str) - 1
            if 0 <= index < len(subjects):
                subject = subjects[index]
                fallback = next((s for s in self.fallback_subjects if s["name"] == subject.name), None)
                alt_names = fallback.get("alt_names", []) if fallback else []

                return {
                    "id": subject.id,
                    "name": subject.name,
                    "description": subject.description,
                    "book_code": subject.book_code,
                    "alt_names": alt_names,
                }

        # Try exact name match (case-insensitive)
        input_lower = input_str.lower()
        for subject in subjects:
            if subject.name.lower() == input_lower:
                fallback = next((s for s in self.fallback_subjects if s["name"] == subject.name), None)
                alt_names = fallback.get("alt_names", []) if fallback else []

                return {
                    "id": subject.id,
                    "name": subject.name,
                    "description": subject.description,
                    "book_code": subject.book_code,
                    "alt_names": alt_names,
                }

        # Try alternative name matching using fallback data
        for subject in subjects:
            fallback = next((s for s in self.fallback_subjects if s["name"] == subject.name), None)
            if fallback:
                alt_names = fallback.get("alt_names", [])
                if any(alt_name.lower() == input_lower for alt_name in alt_names):
                    return {
                        "id": subject.id,
                        "name": subject.name,
                        "description": subject.description,
                        "book_code": subject.book_code,
                        "alt_names": alt_names,
                    }

        # Try partial matching
        for subject in subjects:
            if input_lower in subject.name.lower():
                fallback = next((s for s in self.fallback_subjects if s["name"] == subject.name), None)
                alt_names = fallback.get("alt_names", []) if fallback else []

                return {
                    "id": subject.id,
                    "name": subject.name,
                    "description": subject.description,
                    "book_code": subject.book_code,
                    "alt_names": alt_names,
                }

        return None

    def _search_fallback_subjects(self, input_str: str) -> Optional[Dict[str, Any]]:
        """Search fallback subjects by name or number."""
        # Try number-based selection first
        if input_str.isdigit():
            index = int(input_str) - 1
            if 0 <= index < len(self.fallback_subjects):
                return self.fallback_subjects[index].copy()

        # Try exact name match (case-insensitive)
        input_lower = input_str.lower()
        for subject in self.fallback_subjects:
            if subject["name"].lower() == input_lower:
                return subject.copy()

        # Try alternative name matching
        for subject in self.fallback_subjects:
            alt_names = subject.get("alt_names", [])
            if any(alt_name.lower() == input_lower for alt_name in alt_names):
                return subject.copy()

        # Try partial matching
        for subject in self.fallback_subjects:
            if input_lower in subject["name"].lower():
                return subject.copy()

            # Check alternative names for partial match
            alt_names = subject.get("alt_names", [])
            if any(input_lower in alt_name.lower() for alt_name in alt_names):
                return subject.copy()

        return None


# Create singleton instance
subject_service = SubjectService()
