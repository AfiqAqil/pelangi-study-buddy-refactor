"""QuestionsBank model for storing quiz questions."""

from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, Column
import sqlalchemy as sa

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.quiz_attempt import QuizAttempt


class QuestionsBank(BaseModel, table=True):
    """QuestionsBank model for storing quiz questions with rich metadata.
    
    Attributes:
        id: The primary key (UUID)
        question: The question text
        answer: The correct answer
        type: Question type (e.g., 'exam' or 'quiz')
        forms: List of applicable school forms [1,2,3] or [4,5]
        subject: Subject area (e.g., 'math', 'science')
        language: Language of the question ('english', 'malay', 'chinese')
        difficulty_level: Difficulty level ('easy', 'moderate', 'hard')
        blooms_level: Bloom's taxonomy level ('tp1', 'tp2', 'tp3', 'tp4')
        blooms_descriptor: Bloom's taxonomy descriptor
        question_type: Type of question format
        learning_standards: List of learning standards covered
        answer_page: Page number where answer can be found
        chapter_number: Chapter number (1-27)
        chapter_name: Chapter name (e.g., 'Introduction to Chemistry')
        source: Source identifier (e.g., 'FOCUS SPM CHEMISTRY')
        assessment_type: Type of assessment
        requires_latex: Whether LaTeX rendering is needed
        contains_calculations: Whether calculations are involved
        knowledge_snippet: Knowledge snippet for context
        knowledge_snippet_type: Type of knowledge snippet
        image_uri: URI for associated image
        created_at: When the question was created
        
        # Relationships
        quiz_attempts: Relationship to quiz attempts for this question
    """
    
    __tablename__ = "questions_bank"
    
    id: str = Field(default=None, primary_key=True)
    question: str = Field(description="The question text")
    answer: str = Field(description="The correct answer")
    type: str = Field(index=True, description="Question type (e.g., 'exam' or 'quiz')")
    forms: Optional[List[int]] = Field(default=None, sa_column=Column(sa.ARRAY(sa.Integer)), description="List of form [1,2,3] or [4,5]")
    subject: str = Field(index=True, description="Subject area (e.g., 'math', 'science')")
    language: str = Field(index=True, description="Language ('english', 'malay', 'chinese')")
    difficulty_level: str = Field(index=True, description="Difficulty level ('easy', 'moderate', 'hard')")
    blooms_level: Optional[str] = Field(default=None, index=True, description="Bloom's taxonomy level ('tp1', 'tp2', 'tp3', 'tp4')")
    blooms_descriptor: Optional[str] = Field(default=None, description="Bloom's taxonomy descriptor")
    question_type: Optional[str] = Field(default=None, description="Type of question format")
    learning_standards: Optional[List[str]] = Field(default=None, sa_column=Column(sa.ARRAY(sa.Text)), description="Learning standards covered")
    answer_page: Optional[int] = Field(default=None, description="Page number where answer can be found")
    chapter_number: Optional[str] = Field(default=None, index=True, description="Chapter number (1-27)")
    chapter_name: Optional[str] = Field(default=None, index=True, description="Chapter name")
    source: Optional[str] = Field(default=None, index=True, description="Source identifier")
    assessment_type: Optional[str] = Field(default=None, description="Assessment type")
    requires_latex: Optional[bool] = Field(default=None, description="Whether LaTeX rendering is needed")
    contains_calculations: Optional[bool] = Field(default=None, description="Whether calculations are involved")
    knowledge_snippet: Optional[str] = Field(default=None, description="Knowledge snippet for context")
    knowledge_snippet_type: Optional[str] = Field(default=None, description="Type of knowledge snippet")
    image_uri: Optional[str] = Field(default=None, description="URI for associated image")
    
    # Relationships
    quiz_attempts: List["QuizAttempt"] = Relationship(back_populates="question")