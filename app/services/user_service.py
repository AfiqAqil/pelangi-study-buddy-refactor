"""User service for profile and onboarding management."""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.user import User
from app.services.database import database_service


class UserService:
    """Service for managing user profiles and onboarding."""

    def __init__(self):
        """Initialize the user service."""
        self.db_service = database_service

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID.
        
        Args:
            user_id: User ID to search for
            
        Returns:
            Optional[User]: User if found
        """
        try:
            with Session(self.db_service.engine) as session:
                statement = select(User).where(User.id == user_id)
                return session.exec(statement).first()
        except Exception as e:
            logger.error("get_user_by_id_failed", error=str(e), user_id=user_id)
            return None

    def get_user_by_external_id(self, external_id: str) -> Optional[User]:
        """Get user by external ID.
        
        Args:
            external_id: External ID to search for
            
        Returns:
            Optional[User]: User if found
        """
        try:
            with Session(self.db_service.engine) as session:
                statement = select(User).where(User.external_id == external_id)
                return session.exec(statement).first()
        except Exception as e:
            logger.error("get_user_by_external_id_failed", error=str(e), external_id=external_id)
            return None

    def is_onboarding_completed(self, user_id: str) -> bool:
        """Check if user has completed onboarding.
        
        Args:
            user_id: User ID to check
            
        Returns:
            bool: True if onboarding is completed
        """
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                return False
            return user.onboarding_completed
        except Exception as e:
            logger.error("is_onboarding_completed_failed", error=str(e), user_id=user_id)
            return False

    def get_user_profile_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile data formatted for onboarding.
        
        Args:
            user_id: User ID to get profile for
            
        Returns:
            Optional[Dict]: User profile data or None
        """
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                return None
                
            profile_data = {}
            
            # Map user model fields to onboarding fields
            if user.full_name:
                profile_data["full_name"] = user.full_name
            if user.date_of_birth:
                profile_data["date_of_birth"] = user.date_of_birth.isoformat()
            if user.current_subjects:
                profile_data["current_subjects"] = user.current_subjects
            if user.focus_subjects:
                profile_data["focus_subjects"] = user.focus_subjects
            if user.form_level:
                profile_data["form_level"] = f"Form {user.form_level}"
            if user.school_name:
                profile_data["school_name"] = user.school_name
            if user.language:
                profile_data["language_preference"] = user.language
            if user.student_id:
                profile_data["student_id"] = user.student_id
                
            return profile_data if profile_data else None
            
        except Exception as e:
            logger.error("get_user_profile_data_failed", error=str(e), user_id=user_id)
            return None

    def save_onboarding_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """Save completed onboarding profile to database.
        
        Args:
            user_id: User ID to save profile for
            profile_data: Dictionary with profile data
            
        Returns:
            bool: True if saved successfully
        """
        try:
            with Session(self.db_service.engine) as session:
                # Get existing user
                statement = select(User).where(User.id == user_id)
                user = session.exec(statement).first()
                
                if not user:
                    logger.error("save_onboarding_profile_user_not_found", user_id=user_id)
                    return False
                
                # Update user profile fields
                if "full_name" in profile_data:
                    user.full_name = profile_data["full_name"]
                if "date_of_birth" in profile_data:
                    user.date_of_birth = profile_data["date_of_birth"]
                if "current_subjects" in profile_data:
                    user.current_subjects = profile_data["current_subjects"]
                if "focus_subjects" in profile_data:
                    user.focus_subjects = profile_data["focus_subjects"]
                
                # Parse form level (handle different formats)
                if "form_level" in profile_data:
                    form_level = profile_data["form_level"]
                    if isinstance(form_level, str) and form_level.startswith("Form "):
                        user.form_level = int(form_level.split(" ")[1])
                    else:
                        user.form_level = int(form_level)
                    
                if "school_name" in profile_data:
                    user.school_name = profile_data["school_name"]
                if "language_preference" in profile_data:
                    user.language = profile_data["language_preference"]
                if "student_id" in profile_data:
                    user.student_id = profile_data["student_id"]
                    
                user.onboarding_completed = True
                user.updated_at = datetime.utcnow()
                
                session.add(user)
                session.commit()
                session.refresh(user)
                
                logger.info(
                    "onboarding_profile_saved",
                    user_id=user_id,
                    full_name=user.full_name,
                    form_level=user.form_level,
                    subjects_count=len(user.current_subjects) if user.current_subjects else 0
                )
                
                return True
                
        except Exception as e:
            logger.error("save_onboarding_profile_failed", error=str(e), user_id=user_id)
            return False

    def update_partial_profile(self, user_id: str, field_name: str, value: Any) -> bool:
        """Update a single profile field during onboarding.
        
        Args:
            user_id: User ID to update
            field_name: Field name to update
            value: New value for the field
            
        Returns:
            bool: True if updated successfully
        """
        try:
            with Session(self.db_service.engine) as session:
                statement = select(User).where(User.id == user_id)
                user = session.exec(statement).first()
                
                if not user:
                    logger.error("update_partial_profile_user_not_found", user_id=user_id)
                    return False
                
                # Map onboarding field names to user model fields
                field_mapping = {
                    "full_name": "full_name",
                    "date_of_birth": "date_of_birth",
                    "current_subjects": "current_subjects",
                    "focus_subjects": "focus_subjects",
                    "form_level": "form_level",
                    "school_name": "school_name",
                    "language_preference": "language",
                    "student_id": "student_id"
                }
                
                if field_name not in field_mapping:
                    logger.warning("update_partial_profile_unknown_field", field_name=field_name)
                    return False
                
                user_field = field_mapping[field_name]
                
                # Handle special cases
                if field_name == "form_level":
                    if isinstance(value, str) and value.startswith("Form "):
                        value = int(value.split(" ")[1])
                    else:
                        value = int(value)
                elif field_name == "date_of_birth" and isinstance(value, str):
                    value = datetime.fromisoformat(value).date()
                
                setattr(user, user_field, value)
                user.updated_at = datetime.utcnow()
                
                session.add(user)
                session.commit()
                
                logger.debug(
                    "partial_profile_updated",
                    user_id=user_id,
                    field_name=field_name,
                    user_field=user_field
                )
                
                return True
                
        except Exception as e:
            logger.error(
                "update_partial_profile_failed",
                error=str(e),
                user_id=user_id,
                field_name=field_name
            )
            return False

    def get_profile_completeness(self, user_id: str) -> Dict[str, Any]:
        """Get profile completeness status.
        
        Args:
            user_id: User ID to check
            
        Returns:
            Dict with completeness information
        """
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                return {
                    "is_complete": False,
                    "missing_fields": ["all"],
                    "completed_fields": []
                }
            
            required_fields = {
                "full_name": user.full_name,
                "current_subjects": user.current_subjects,
                "form_level": user.form_level,
                "school_name": user.school_name,
                "focus_subjects": user.focus_subjects,
                "language_preference": user.language
            }
            
            completed_fields = [field for field, value in required_fields.items() if value]
            missing_fields = [field for field, value in required_fields.items() if not value]
            
            # Profile is complete if all required fields are filled
            fields_complete = len(missing_fields) == 0
            # Onboarding is truly complete if profile complete AND onboarding flag is set
            is_complete = fields_complete and user.onboarding_completed
            
            return {
                "is_complete": is_complete,
                "fields_complete": fields_complete,  # New field for checking if ready for confirmation
                "missing_fields": missing_fields,
                "completed_fields": completed_fields,
                "onboarding_completed": user.onboarding_completed
            }
            
        except Exception as e:
            logger.error("get_profile_completeness_failed", error=str(e), user_id=user_id)
            return {
                "is_complete": False,
                "missing_fields": ["all"],
                "completed_fields": []
            }


# Global instance
user_service = UserService()