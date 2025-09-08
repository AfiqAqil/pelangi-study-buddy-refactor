"""Subject-related schemas for API requests and responses."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SubjectBase(BaseModel):
    """Base subject schema."""

    name: str = Field(..., description="Subject name")
    description: Optional[str] = Field(None, description="Subject description")
    book_code: Optional[str] = Field(None, description="Book code for RAG filtering")


class SubjectCreate(SubjectBase):
    """Schema for creating a new subject."""

    pass


class SubjectUpdate(BaseModel):
    """Schema for updating a subject."""

    name: Optional[str] = Field(None, description="Subject name")
    description: Optional[str] = Field(None, description="Subject description")
    book_code: Optional[str] = Field(None, description="Book code for RAG filtering")


class SubjectResponse(SubjectBase):
    """Schema for subject API responses."""

    id: str = Field(..., description="Subject ID")
    alt_names: Optional[List[str]] = Field(default_factory=list, description="Alternative names for the subject")

    class Config:
        """Pydantic configuration."""

        from_attributes = True


class SubjectListResponse(BaseModel):
    """Schema for subject list API response."""

    subjects: List[SubjectResponse] = Field(..., description="List of subjects")
    total: int = Field(..., description="Total number of subjects")
    formatted_message: Optional[str] = Field(None, description="Formatted selection message for users")


class SubjectSelectionRequest(BaseModel):
    """Schema for subject selection request."""

    subject_input: str = Field(..., description="Subject name, number, or alternative name", min_length=1)


class SubjectSelectionResponse(BaseModel):
    """Schema for subject selection response."""

    success: bool = Field(..., description="Whether selection was successful")
    message: str = Field(..., description="Response message")
    selected_subject: Optional[SubjectResponse] = Field(None, description="Selected subject details")


class UserSubjectResponse(BaseModel):
    """Schema for user's current subject response."""

    current_subject: Optional[SubjectResponse] = Field(None, description="User's current primary subject")
    current_subjects: Optional[List[str]] = Field(default_factory=list, description="All current subjects")
    focus_subjects: Optional[List[str]] = Field(default_factory=list, description="Focus subjects")
    form_level: Optional[int] = Field(None, description="User's form level (1-5)")
    language: str = Field("English", description="User's preferred language")


class SubjectFilterRequest(BaseModel):
    """Schema for subject filtering request."""

    form_level: Optional[int] = Field(None, description="Filter by form level (1-5)", ge=1, le=5)
    language: Optional[str] = Field(None, description="Filter by language preference")
    search: Optional[str] = Field(None, description="Search term for subject name or description")


class SubjectSearchRequest(BaseModel):
    """Schema for subject search request."""

    query: str = Field(..., description="Search query", min_length=1)
    include_alternatives: bool = Field(True, description="Include alternative names in search")
    exact_match: bool = Field(False, description="Require exact match")


class SubjectSearchResponse(BaseModel):
    """Schema for subject search response."""

    results: List[SubjectResponse] = Field(..., description="Search results")
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Number of results found")
    suggestions: Optional[List[str]] = Field(default_factory=list, description="Alternative search suggestions")
