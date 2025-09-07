"""QuizAttempt model for tracking user quiz attempts."""

from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.questions_bank import QuestionsBank
    from app.models.chat_session import ChatSession


class QuizAttempt(BaseModel, table=True):
    """QuizAttempt model for tracking user attempts at quiz questions.

    Attributes:
        id: The primary key (UUID)
        user_id: Foreign key to users table
        question_id: Foreign key to questions_bank table
        session_id: Foreign key to chat_sessions table
        user_answer: The answer provided by the user
        is_correct: Whether the answer was correct
        time_taken_seconds: Time taken to answer (optional)
        created_at: When the attempt was created

        # Relationships
        user: Relationship to User model
        question: Relationship to QuestionsBank model
        session: Relationship to ChatSession model
    """

    __tablename__ = "quiz_attempts"

    id: str = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    question_id: str = Field(foreign_key="questions_bank.id", index=True)
    session_id: str = Field(foreign_key="chat_sessions.session_id", index=True)
    user_answer: str = Field(description="The answer provided by the user")
    is_correct: bool = Field(index=True, description="Whether the answer was correct")
    time_taken_seconds: Optional[int] = Field(default=None, description="Time taken to answer")

    # Relationships
    user: "User" = Relationship(back_populates="quiz_attempts")
    question: "QuestionsBank" = Relationship(back_populates="quiz_attempts")
    session: "ChatSession" = Relationship(back_populates="quiz_attempts")

    # Note: CheckConstraint with subquery not supported in PostgreSQL
    # Business logic should ensure quiz_attempts only reference quiz-type questions
