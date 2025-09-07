"""Database models for the application."""

# Import all models to ensure they are registered with SQLModel
from app.models.user import User, UserTier
from app.models.session import Session
from app.models.thread import Thread
from app.models.chatwoot_contact_mapping import ChatwootContactMapping
from app.models.subject import Subject
from app.models.questions_bank import QuestionsBank
from app.models.spot_question import SpotQuestion
from app.models.quiz_attempt import QuizAttempt
from app.models.spot_question_attempt import SpotQuestionAttempt
from app.models.chat_session import ChatSession
from app.models.chat_session_message import ChatSessionMessage
from app.models.daily_quota import TierQuotaConfig, DailyQuizQuota, DailyUserQuota
from app.models.payment_link import PaymentLink

__all__ = [
    "User",
    "UserTier",
    "Session",
    "Thread",
    "ChatwootContactMapping",
    "Subject",
    "QuestionsBank",
    "SpotQuestion",
    "QuizAttempt",
    "SpotQuestionAttempt",
    "ChatSession",
    "ChatSessionMessage",
    "TierQuotaConfig",
    "DailyQuizQuota",
    "DailyUserQuota",
    "PaymentLink",
]
