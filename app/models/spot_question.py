"""SpotQuestion model for targeted practice questions."""

from typing import TYPE_CHECKING, List

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.subject import Subject
    from app.models.spot_question_attempt import SpotQuestionAttempt


class SpotQuestion(BaseModel, table=True):
    """SpotQuestion model for storing targeted practice questions.
    
    Attributes:
        id: The primary key (UUID)
        subject_id: Foreign key to subjects table
        question_text: The question text
        correct_answer: The correct answer text
        explanation: Detailed explanation of the answer
        difficulty_level: Difficulty level (default 'moderate')
        created_at: When the question was created
        
        # Relationships
        subject: Relationship to Subject model
        attempts: Relationship to SpotQuestionAttempt model
    """
    
    __tablename__ = "spot_questions"
    
    id: str = Field(default=None, primary_key=True)
    subject_id: str = Field(foreign_key="subjects.id", index=True)
    question_text: str = Field(description="The question text")
    correct_answer: str = Field(description="The correct answer text")
    explanation: str = Field(description="Detailed explanation of the answer")
    difficulty_level: str = Field(default="moderate", index=True, description="Difficulty level")
    
    # Relationships
    subject: "Subject" = Relationship(back_populates="spot_questions")
    attempts: List["SpotQuestionAttempt"] = Relationship(back_populates="question")