"""SpotQuestionAttempt model for tracking user spot question attempts."""

from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.spot_question import SpotQuestion
    from app.models.chat_session import ChatSession


class SpotQuestionAttempt(BaseModel, table=True):
    """SpotQuestionAttempt model for tracking user attempts at spot questions.
    
    Attributes:
        id: The primary key (UUID)
        user_id: Foreign key to users table
        question_id: Foreign key to spot_questions table
        session_id: Foreign key to chat_sessions table
        user_answer: The answer provided by the user
        is_correct: Whether the answer was correct
        similarity_score: Semantic similarity to correct answer (optional)
        time_taken_seconds: Time taken to answer (optional)
        created_at: When the attempt was created
        
        # Relationships
        user: Relationship to User model
        question: Relationship to SpotQuestion model
        session: Relationship to ChatSession model
    """
    
    __tablename__ = "spot_question_attempts"
    
    id: str = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    question_id: str = Field(foreign_key="spot_questions.id", index=True)
    session_id: str = Field(foreign_key="chat_sessions.session_id", index=True)
    user_answer: str = Field(description="The answer provided by the user")
    is_correct: bool = Field(index=True, description="Whether the answer was correct")
    similarity_score: Optional[float] = Field(default=None, description="Semantic similarity to correct answer")
    time_taken_seconds: Optional[int] = Field(default=None, description="Time taken to answer")
    
    # Relationships
    user: "User" = Relationship(back_populates="spot_question_attempts")
    question: "SpotQuestion" = Relationship(back_populates="attempts")
    session: "ChatSession" = Relationship(back_populates="spot_question_attempts")