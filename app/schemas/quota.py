"""Quota-related schemas for API requests and responses."""

from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class QuotaType(str, Enum):
    """Quota type enumeration."""

    QUIZ = "quiz"
    MESSAGE = "message"


class QuotaValidationStatus(BaseModel):
    """Schema for quota validation status."""

    is_valid: bool = Field(..., description="Whether the request is within quota limits")
    current_usage: int = Field(..., description="Current usage count for the day")
    daily_limit: int = Field(..., description="Daily limit for this quota type")
    remaining: int = Field(..., description="Remaining quota for today")
    tier: str = Field(..., description="User's tier")
    quota_type: str = Field(..., description="Type of quota (quiz/message)")
    upgrade_prompt: Optional[str] = Field(None, description="Upgrade prompt if limit reached")


class QuotaStatusResponse(BaseModel):
    """Schema for comprehensive quota status response."""

    quiz_quota: QuotaValidationStatus = Field(..., description="Quiz quota status")
    message_quota: QuotaValidationStatus = Field(..., description="Message quota status")
    tier: str = Field(..., description="User's current tier")
    upgrade_available: bool = Field(..., description="Whether upgrade options are available")


class QuotaHistoryEntry(BaseModel):
    """Schema for a single day's quota history."""

    date: str = Field(..., description="Date in ISO format (GMT+8)")
    quiz_attempted: int = Field(..., description="Number of quiz questions attempted")
    quiz_answered: int = Field(..., description="Number of quiz questions answered correctly")
    messages_sent: int = Field(..., description="Number of messages sent")


class QuotaHistoryResponse(BaseModel):
    """Schema for quota history response."""

    history: List[QuotaHistoryEntry] = Field(..., description="Daily quota usage history")
    days: int = Field(..., description="Number of days in the history")
    total_quiz_attempted: int = Field(..., description="Total quiz questions attempted in period")
    total_messages_sent: int = Field(..., description="Total messages sent in period")


class TierConfigResponse(BaseModel):
    """Schema for tier configuration response."""

    id: str = Field(..., description="Configuration ID")
    tier_name: str = Field(..., description="Tier name")
    daily_quiz_limit: int = Field(..., description="Daily quiz question limit (-1 for unlimited)")
    daily_quiz_limit_type: str = Field(..., description="Type of quiz limit")
    daily_message_limit: Optional[int] = Field(None, description="Daily message limit (-1 for unlimited)")
    daily_message_limit_type: Optional[str] = Field(None, description="Type of message limit")
    rollover_enabled: bool = Field(..., description="Whether unused quotas rollover")
    rollover_days: int = Field(..., description="Number of days quotas can rollover")

    class Config:
        """Pydantic configuration."""

        from_attributes = True


class TierConfigListResponse(BaseModel):
    """Schema for tier configuration list response."""

    configs: List[TierConfigResponse] = Field(..., description="List of tier configurations")
    total: int = Field(..., description="Total number of configurations")


class TierConfigUpdateRequest(BaseModel):
    """Schema for updating tier configuration."""

    daily_quiz_limit: Optional[int] = Field(None, description="Daily quiz question limit (-1 for unlimited)")
    daily_message_limit: Optional[int] = Field(None, description="Daily message limit (-1 for unlimited)")
    rollover_enabled: Optional[bool] = Field(None, description="Whether unused quotas rollover")
    rollover_days: Optional[int] = Field(None, description="Number of days quotas can rollover", ge=0)


class UpgradeBenefitsResponse(BaseModel):
    """Schema for upgrade benefits response."""

    current_tier: str = Field(..., description="User's current tier")
    target_tier: str = Field(..., description="Target tier for upgrade")
    benefits: List[str] = Field(..., description="List of upgrade benefits")
    pricing: dict = Field(..., description="Pricing information")


class QuotaRecordRequest(BaseModel):
    """Schema for recording quota usage."""

    quota_type: QuotaType = Field(..., description="Type of quota to record")
    answered: Optional[bool] = Field(None, description="Whether quiz question was answered correctly (quiz only)")


class QuotaRecordResponse(BaseModel):
    """Schema for quota recording response."""

    success: bool = Field(..., description="Whether recording was successful")
    message: str = Field(..., description="Response message")
    new_usage: int = Field(..., description="New usage count after recording")


class TierUsageStatsResponse(BaseModel):
    """Schema for tier usage statistics response."""

    total_users: int = Field(..., description="Total number of users")
    tier_distribution: dict = Field(..., description="Distribution of users across tiers")


class TierValidationIssue(BaseModel):
    """Schema for tier configuration validation issue."""

    tier: str = Field(..., description="Tier name with issue")
    issue: str = Field(..., description="Description of the issue")
    value: str = Field(..., description="Problematic value")


class TierValidationResponse(BaseModel):
    """Schema for tier validation response."""

    is_valid: bool = Field(..., description="Whether all tier configurations are valid")
    issues: List[TierValidationIssue] = Field(default_factory=list, description="List of validation issues")
    total_issues: int = Field(..., description="Total number of issues found")
