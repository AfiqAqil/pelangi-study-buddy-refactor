"""Subject model for academic subjects."""

from typing import TYPE_CHECKING, List

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.spot_question import SpotQuestion


class Subject(BaseModel, table=True):
    """Subject model for storing academic subjects.
    
    Attributes:
        id: The primary key (UUID)
        name: Subject name (e.g., 'Mathematics', 'Science')
        description: Optional description of the subject
        book_code: Optional book code identifier
        created_at: When the subject was created
        
        # Relationships
        spot_questions: Relationship to spot questions for this subject
    """
    
    __tablename__ = "subjects"
    
    id: str = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str | None = Field(default=None)
    book_code: str | None = Field(default=None, index=True)
    
    # Relationships
    spot_questions: List["SpotQuestion"] = Relationship(back_populates="subject")