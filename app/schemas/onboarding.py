"""Onboarding schemas for student profile collection."""

from datetime import date, datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class StudentProfile(BaseModel):
    """Complete student profile for onboarding."""
    
    # Required fields (in sequence)
    full_name: str = Field(..., description="Student's complete name", min_length=2, max_length=100)
    date_of_birth: date = Field(..., description="Birth date (required)")
    school_name: str = Field(..., description="Name of the school", min_length=3, max_length=200)
    form_level: Literal["Form 4", "Form 5"] = Field(..., description="Current form level")
    current_subjects: List[str] = Field(..., description="All subjects currently studying", min_length=1, max_length=15)
    focus_subjects: List[str] = Field(..., description="1-3 subjects for extra help", min_length=1, max_length=3)
    language_preference: Literal["English", "Bahasa Malaysia", "Chinese"] = Field(..., description="Preferred language")
    
    # Optional fields
    student_id: Optional[str] = Field(None, description="School ID number (optional)", max_length=50)
    
    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name format."""
        v = v.strip()
        if not v or len(v) < 2:
            raise ValueError("Name must be at least 2 characters long")
        if any(char.isdigit() for char in v):
            raise ValueError("Name cannot contain numbers")
        return v
    
    @field_validator('current_subjects', 'focus_subjects')
    @classmethod
    def validate_subjects(cls, v: List[str]) -> List[str]:
        """Validate and normalize subject names."""
        if not v:
            raise ValueError("At least one subject is required")
        # Remove duplicates and normalize
        normalized = []
        seen = set()
        for subject in v:
            subject = subject.strip()
            if subject and subject.lower() not in seen:
                normalized.append(subject)
                seen.add(subject.lower())
        return normalized
    
    @field_validator('date_of_birth', mode='before')
    @classmethod
    def parse_date_of_birth(cls, v: Union[str, date]) -> date:
        """Parse and validate date of birth from string or date."""
        if v is None:
            raise ValueError("Date of birth is required")
        
        if isinstance(v, date):
            parsed_date = v
        elif isinstance(v, str):
            # Try multiple date formats
            date_formats = [
                "%d/%m/%Y",    # 15/03/2007
                "%Y-%m-%d",    # 2007-03-15
                "%d-%m-%Y",    # 15-03-2007
                "%m/%d/%Y",    # 03/15/2007
                "%Y/%m/%d",    # 2007/03/15
            ]
            
            parsed_date = None
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(v, fmt).date()
                    break
                except ValueError:
                    continue
            
            if parsed_date is None:
                raise ValueError("Invalid date format. Use DD/MM/YYYY, YYYY-MM-DD, or similar formats")
        else:
            raise ValueError("Date of birth must be a string or date object")
        
        # Validate age
        today = date.today()
        age = today.year - parsed_date.year - ((today.month, today.day) < (parsed_date.month, parsed_date.day))
        
        if age < 13:
            raise ValueError("Student must be at least 13 years old")
        if age > 20:
            raise ValueError("Student age seems incorrect for Form 4/5 (over 20)")
        
        return parsed_date
    
    @model_validator(mode='after')
    def validate_focus_subjects_from_current(self) -> 'StudentProfile':
        """Ensure focus subjects are from current subjects."""
        if self.focus_subjects and self.current_subjects:
            current_lower = {s.lower() for s in self.current_subjects}
            for subject in self.focus_subjects:
                if subject.lower() not in current_lower:
                    raise ValueError(f"Focus subject '{subject}' must be from current subjects")
        return self


class OnboardingFieldExtraction(BaseModel):
    """Schema for LLM-based field extraction from user input."""
    
    full_name: Optional[str] = Field(None, description="Student's full name if provided")
    form_level: Optional[Literal["Form 4", "Form 5"]] = Field(None, description="Form level if mentioned")
    school_name: Optional[str] = Field(None, description="School name if provided")
    current_subjects: Optional[List[str]] = Field(None, description="List of current subjects if mentioned")
    focus_subjects: Optional[List[str]] = Field(None, description="Subjects for extra help if specified")
    language_preference: Optional[Literal["English", "Bahasa Malaysia", "Chinese"]] = Field(None, description="Language preference if stated")
    date_of_birth: Optional[str] = Field(None, description="Date of birth in any format if provided")
    student_id: Optional[str] = Field(None, description="Student ID if mentioned")