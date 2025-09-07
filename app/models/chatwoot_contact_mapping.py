"""Chatwoot contact to phone number mapping model."""

from typing import Optional
from sqlmodel import Field, SQLModel

from app.models.base import BaseModel


class ChatwootContactMapping(BaseModel, table=True):
    """Maps Chatwoot contact IDs to phone numbers for user identification.

    This model stores the association between Chatwoot contact IDs and phone numbers
    to maintain user identity across conversations without relying on Chatwoot's
    contact data being updated.

    Attributes:
        id: Primary key
        contact_id: Chatwoot contact ID (unique)
        phone: Normalized phone number (+60 format)
        created_at: When the mapping was created
        updated_at: When the mapping was last updated
    """

    __tablename__ = "chatwoot_contact_mappings"

    id: int = Field(default=None, primary_key=True)
    contact_id: int = Field(unique=True, index=True, description="Chatwoot contact ID")
    phone: str = Field(index=True, description="Normalized phone number (+60 format)")