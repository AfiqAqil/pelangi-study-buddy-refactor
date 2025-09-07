"""PaymentLink model for payment processing."""

from typing import TYPE_CHECKING
from datetime import datetime

from sqlmodel import Field, Relationship, Column
import sqlalchemy as sa

from app.models.base import BaseModel
from app.models.user import UserTier

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.chat_session import ChatSession


class PaymentLink(BaseModel, table=True):
    """PaymentLink model for storing payment links for tier upgrades.
    
    Attributes:
        id: The primary key (UUID)
        user_id: Foreign key to users table
        session_id: Foreign key to chat_sessions table
        target_tier: Target tier for upgrade
        payment_url: Payment URL for the link
        amount: Payment amount
        currency: Currency code (default 'USD')
        status: Payment status ('pending', 'completed', 'expired', 'failed')
        expires_at: When the payment link expires
        created_at: When the payment link was created
        
        # Relationships
        user: Relationship to User model
        session: Relationship to ChatSession model
    """
    
    __tablename__ = "payment_links"
    
    id: str = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    session_id: str = Field(foreign_key="chat_sessions.session_id", index=True)
    target_tier: UserTier = Field(description="Target tier for upgrade")
    payment_url: str = Field(description="Payment URL for the link")
    amount: float = Field(description="Payment amount")
    currency: str = Field(default="USD", description="Currency code")
    status: str = Field(default="pending", index=True, description="Payment status")
    expires_at: datetime = Field(sa_column=Column(sa.DateTime(timezone=True)), description="When the payment link expires")
    
    # Relationships
    user: "User" = Relationship()
    session: "ChatSession" = Relationship()