"""Enhanced quota management service for validation and tracking."""

from typing import Optional, Dict, Any, List
from datetime import datetime, date, timezone, timedelta
from dataclasses import dataclass
from sqlmodel import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import logger
from app.models.user import User, UserTier
from app.models.daily_quota import TierQuotaConfig, DailyQuizQuota, DailyUserQuota
from app.services.database import database_service


@dataclass
class QuotaValidationResult:
    """Result of quota validation check."""

    is_valid: bool
    current_usage: int
    daily_limit: int
    remaining: int
    tier: str
    upgrade_prompt: Optional[str] = None
    quota_type: str = "unknown"


@dataclass
class QuotaStatus:
    """Current quota status for a user."""

    quiz_quota: QuotaValidationResult
    message_quota: QuotaValidationResult
    tier: str
    upgrade_available: bool = False


class QuotaService:
    """Service for managing user quotas and tier limits."""

    def __init__(self):
        """Initialize quota service."""
        self.gmt8_timezone = timezone(timedelta(hours=8))
        self._tier_cache = {}  # Simple in-memory cache for tier configs

    def _get_gmt8_date(self) -> date:
        """Get current date in GMT+8 timezone (Malaysia time)."""
        return datetime.now(self.gmt8_timezone).date()

    async def get_tier_config(self, tier: UserTier) -> Optional[TierQuotaConfig]:
        """Get tier configuration with caching.

        Args:
            tier: User tier

        Returns:
            TierQuotaConfig if found, None otherwise
        """
        tier_name = tier.value

        # Check cache first
        if tier_name in self._tier_cache:
            return self._tier_cache[tier_name]

        try:
            with database_service.get_session_maker() as session:
                statement = select(TierQuotaConfig).where(TierQuotaConfig.tier_name == tier_name)
                config = session.exec(statement).first()

                if config:
                    self._tier_cache[tier_name] = config
                    return config

                # Return fallback configuration
                fallback_config = self._get_fallback_tier_config(tier)
                if fallback_config:
                    self._tier_cache[tier_name] = fallback_config
                return fallback_config

        except SQLAlchemyError as e:
            logger.error("database_error_getting_tier_config", error=str(e), tier=tier_name)
            fallback_config = self._get_fallback_tier_config(tier)
            if fallback_config:
                self._tier_cache[tier_name] = fallback_config
            return fallback_config

    def _get_fallback_tier_config(self, tier: UserTier) -> TierQuotaConfig:
        """Get fallback tier configuration when database is unavailable."""
        import uuid

        if tier == UserTier.FREE:
            return TierQuotaConfig(
                id=str(uuid.uuid4()),
                tier_name="FREE",
                daily_quiz_limit=10,
                daily_quiz_limit_type="questions_attempted",
                daily_message_limit=20,
                daily_message_limit_type="messages_sent",
                rollover_enabled=False,
                rollover_days=0,
            )
        elif tier == UserTier.PREMIUM:
            return TierQuotaConfig(
                id=str(uuid.uuid4()),
                tier_name="PREMIUM",
                daily_quiz_limit=50,
                daily_quiz_limit_type="questions_attempted",
                daily_message_limit=100,
                daily_message_limit_type="messages_sent",
                rollover_enabled=False,
                rollover_days=0,
            )
        elif tier == UserTier.ENTERPRISE:
            return TierQuotaConfig(
                id=str(uuid.uuid4()),
                tier_name="ENTERPRISE",
                daily_quiz_limit=999999,  # Unlimited
                daily_quiz_limit_type="questions_attempted",
                daily_message_limit=999999,  # Unlimited
                daily_message_limit_type="messages_sent",
                rollover_enabled=False,
                rollover_days=0,
            )
        else:
            # Default to FREE
            return self._get_fallback_tier_config(UserTier.FREE)

    async def validate_quiz_request(self, user_id: str) -> QuotaValidationResult:
        """Validate if user can make a quiz request.

        Args:
            user_id: User ID

        Returns:
            QuotaValidationResult with validation details
        """
        try:
            with database_service.get_session_maker() as session:
                user = session.get(User, user_id)
                if not user:
                    logger.error("user_not_found_for_quota_validation", user_id=user_id)
                    return QuotaValidationResult(
                        is_valid=False, current_usage=0, daily_limit=0, remaining=0, tier="UNKNOWN", quota_type="quiz"
                    )

                tier_config = await self.get_tier_config(user.tier)
                if not tier_config:
                    logger.error("tier_config_not_found", tier=user.tier.value)
                    # Fail safe - allow request
                    return QuotaValidationResult(
                        is_valid=True,
                        current_usage=0,
                        daily_limit=999999,
                        remaining=999999,
                        tier=user.tier.value,
                        quota_type="quiz",
                    )

                # Get current usage
                quota_date = self._get_gmt8_date()
                statement = select(DailyQuizQuota).where(
                    DailyQuizQuota.user_id == user_id, DailyQuizQuota.quota_date == quota_date
                )
                daily_quota = session.exec(statement).first()

                current_usage = daily_quota.questions_attempted if daily_quota else 0
                daily_limit = tier_config.daily_quiz_limit

                # Check if unlimited
                if daily_limit == -1 or daily_limit >= 999999:
                    return QuotaValidationResult(
                        is_valid=True,
                        current_usage=current_usage,
                        daily_limit=daily_limit,
                        remaining=999999,
                        tier=user.tier.value,
                        quota_type="quiz",
                    )

                remaining = max(0, daily_limit - current_usage)
                is_valid = current_usage < daily_limit

                upgrade_prompt = None
                if not is_valid:
                    upgrade_prompt = self._generate_upgrade_prompt(user.tier, "quiz")

                return QuotaValidationResult(
                    is_valid=is_valid,
                    current_usage=current_usage,
                    daily_limit=daily_limit,
                    remaining=remaining,
                    tier=user.tier.value,
                    upgrade_prompt=upgrade_prompt,
                    quota_type="quiz",
                )

        except SQLAlchemyError as e:
            logger.error("database_error_validating_quiz_quota", error=str(e), user_id=user_id)
            # Fail safe - allow request
            return QuotaValidationResult(
                is_valid=True, current_usage=0, daily_limit=999999, remaining=999999, tier="UNKNOWN", quota_type="quiz"
            )

    async def validate_message_request(self, user_id: str) -> QuotaValidationResult:
        """Validate if user can send a message.

        Args:
            user_id: User ID

        Returns:
            QuotaValidationResult with validation details
        """
        try:
            with database_service.get_session_maker() as session:
                user = session.get(User, user_id)
                if not user:
                    logger.error("user_not_found_for_message_quota_validation", user_id=user_id)
                    return QuotaValidationResult(
                        is_valid=False,
                        current_usage=0,
                        daily_limit=0,
                        remaining=0,
                        tier="UNKNOWN",
                        quota_type="message",
                    )

                tier_config = await self.get_tier_config(user.tier)
                if not tier_config or tier_config.daily_message_limit is None:
                    # Fail safe - allow request
                    return QuotaValidationResult(
                        is_valid=True,
                        current_usage=0,
                        daily_limit=999999,
                        remaining=999999,
                        tier=user.tier.value,
                        quota_type="message",
                    )

                # Get current usage
                quota_date = self._get_gmt8_date()
                statement = select(DailyUserQuota).where(
                    DailyUserQuota.user_id == user_id,
                    DailyUserQuota.quota_date == quota_date,
                    DailyUserQuota.quota_type == "message",
                )
                daily_quota = session.exec(statement).first()

                current_usage = daily_quota.count if daily_quota else 0
                daily_limit = tier_config.daily_message_limit

                # Check if unlimited
                if daily_limit == -1 or daily_limit >= 999999:
                    return QuotaValidationResult(
                        is_valid=True,
                        current_usage=current_usage,
                        daily_limit=daily_limit,
                        remaining=999999,
                        tier=user.tier.value,
                        quota_type="message",
                    )

                remaining = max(0, daily_limit - current_usage)
                is_valid = current_usage < daily_limit

                upgrade_prompt = None
                if not is_valid:
                    upgrade_prompt = self._generate_upgrade_prompt(user.tier, "message")

                return QuotaValidationResult(
                    is_valid=is_valid,
                    current_usage=current_usage,
                    daily_limit=daily_limit,
                    remaining=remaining,
                    tier=user.tier.value,
                    upgrade_prompt=upgrade_prompt,
                    quota_type="message",
                )

        except SQLAlchemyError as e:
            logger.error("database_error_validating_message_quota", error=str(e), user_id=user_id)
            # Fail safe - allow request
            return QuotaValidationResult(
                is_valid=True,
                current_usage=0,
                daily_limit=999999,
                remaining=999999,
                tier="UNKNOWN",
                quota_type="message",
            )

    async def record_quiz_attempt(self, user_id: str, answered: bool = False) -> bool:
        """Record a quiz attempt.

        Args:
            user_id: User ID
            answered: Whether the question was answered correctly

        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            with database_service.get_session_maker() as session:
                quota_date = self._get_gmt8_date()

                # Get or create daily quiz quota
                statement = select(DailyQuizQuota).where(
                    DailyQuizQuota.user_id == user_id, DailyQuizQuota.quota_date == quota_date
                )
                daily_quota = session.exec(statement).first()

                if not daily_quota:
                    import uuid

                    daily_quota = DailyQuizQuota(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        quota_date=quota_date,
                        questions_attempted=0,
                        questions_answered=0,
                    )
                    session.add(daily_quota)

                # Update counters
                daily_quota.questions_attempted += 1
                if answered:
                    daily_quota.questions_answered += 1
                daily_quota.last_question_at = datetime.now(timezone.utc)

                # Also record in unified quota table
                statement = select(DailyUserQuota).where(
                    DailyUserQuota.user_id == user_id,
                    DailyUserQuota.quota_date == quota_date,
                    DailyUserQuota.quota_type == "quiz",
                )
                unified_quota = session.exec(statement).first()

                if not unified_quota:
                    import uuid

                    unified_quota = DailyUserQuota(
                        id=str(uuid.uuid4()), user_id=user_id, quota_date=quota_date, quota_type="quiz", count=0
                    )
                    session.add(unified_quota)

                unified_quota.count = daily_quota.questions_attempted
                unified_quota.last_used_at = datetime.now(timezone.utc)

                session.commit()
                logger.info("quiz_attempt_recorded", user_id=user_id, answered=answered)
                return True

        except SQLAlchemyError as e:
            logger.error("database_error_recording_quiz_attempt", error=str(e), user_id=user_id)
            return False

    async def record_message_sent(self, user_id: str) -> bool:
        """Record a message sent.

        Args:
            user_id: User ID

        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            with database_service.get_session_maker() as session:
                quota_date = self._get_gmt8_date()

                # Get or create daily user quota for messages
                statement = select(DailyUserQuota).where(
                    DailyUserQuota.user_id == user_id,
                    DailyUserQuota.quota_date == quota_date,
                    DailyUserQuota.quota_type == "message",
                )
                daily_quota = session.exec(statement).first()

                if not daily_quota:
                    import uuid

                    daily_quota = DailyUserQuota(
                        id=str(uuid.uuid4()), user_id=user_id, quota_date=quota_date, quota_type="message", count=0
                    )
                    session.add(daily_quota)

                daily_quota.count += 1
                daily_quota.last_used_at = datetime.now(timezone.utc)

                session.commit()
                logger.info("message_sent_recorded", user_id=user_id)
                return True

        except SQLAlchemyError as e:
            logger.error("database_error_recording_message_sent", error=str(e), user_id=user_id)
            return False

    async def get_quota_status(self, user_id: str) -> Optional[QuotaStatus]:
        """Get comprehensive quota status for a user.

        Args:
            user_id: User ID

        Returns:
            QuotaStatus with both quiz and message quotas
        """
        try:
            quiz_quota = await self.validate_quiz_request(user_id)
            message_quota = await self.validate_message_request(user_id)

            with database_service.get_session_maker() as session:
                user = session.get(User, user_id)
                tier = user.tier.value if user else "UNKNOWN"

            upgrade_available = tier == "FREE" or tier == "PREMIUM"

            return QuotaStatus(
                quiz_quota=quiz_quota, message_quota=message_quota, tier=tier, upgrade_available=upgrade_available
            )

        except Exception as e:
            logger.error("error_getting_quota_status", error=str(e), user_id=user_id)
            return None

    async def get_quota_history(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get quota usage history for a user.

        Args:
            user_id: User ID
            days: Number of days to retrieve (default: 7)

        Returns:
            List of daily quota usage records
        """
        try:
            with database_service.get_session_maker() as session:
                end_date = self._get_gmt8_date()
                start_date = end_date - timedelta(days=days - 1)

                # Get quiz quotas
                quiz_statement = (
                    select(DailyQuizQuota)
                    .where(
                        DailyQuizQuota.user_id == user_id,
                        DailyQuizQuota.quota_date >= start_date,
                        DailyQuizQuota.quota_date <= end_date,
                    )
                    .order_by(DailyQuizQuota.quota_date.desc())
                )
                quiz_quotas = session.exec(quiz_statement).all()

                # Get message quotas
                message_statement = (
                    select(DailyUserQuota)
                    .where(
                        DailyUserQuota.user_id == user_id,
                        DailyUserQuota.quota_type == "message",
                        DailyUserQuota.quota_date >= start_date,
                        DailyUserQuota.quota_date <= end_date,
                    )
                    .order_by(DailyUserQuota.quota_date.desc())
                )
                message_quotas = session.exec(message_statement).all()

                # Combine into daily records
                history = []
                quiz_dict = {q.quota_date: q for q in quiz_quotas}
                message_dict = {q.quota_date: q for q in message_quotas}

                for i in range(days):
                    current_date = end_date - timedelta(days=i)
                    quiz_quota = quiz_dict.get(current_date)
                    message_quota = message_dict.get(current_date)

                    history.append(
                        {
                            "date": current_date.isoformat(),
                            "quiz_attempted": quiz_quota.questions_attempted if quiz_quota else 0,
                            "quiz_answered": quiz_quota.questions_answered if quiz_quota else 0,
                            "messages_sent": message_quota.count if message_quota else 0,
                        }
                    )

                return history

        except SQLAlchemyError as e:
            logger.error("database_error_getting_quota_history", error=str(e), user_id=user_id)
            return []

    def _generate_upgrade_prompt(self, current_tier: UserTier, quota_type: str) -> str:
        """Generate tier-specific upgrade prompt.

        Args:
            current_tier: User's current tier
            quota_type: Type of quota limit reached ('quiz' or 'message')

        Returns:
            Formatted upgrade prompt message
        """
        if current_tier == UserTier.FREE:
            return """🌟 **Upgrade to Premium!**

💎 **Premium Benefits:**
• 50 questions per day (vs 10 free)
• 100 messages per day (vs 20 free)  
• Advanced explanations
• Priority support
• Detailed progress tracking
• No advertisements

💰 **Only $9.99/month**"""

        elif current_tier == UserTier.PREMIUM:
            return """🚀 **Upgrade to Enterprise!**

💎 **Enterprise Benefits:**
• Unlimited questions and messages
• Custom curriculum
• Analytics dashboard
• Multi-user management
• API access

💰 **Only $29.99/month**"""

        else:
            return "You've reached your daily limit. Please try again tomorrow!"

    def clear_tier_cache(self):
        """Clear the tier configuration cache."""
        self._tier_cache.clear()
        logger.info("tier_cache_cleared")


# Create singleton instance
quota_service = QuotaService()
