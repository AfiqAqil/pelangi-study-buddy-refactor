"""Tier configuration management service."""

from typing import Optional, Dict, Any, List
from sqlmodel import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import logger
from app.models.user import UserTier
from app.models.daily_quota import TierQuotaConfig
from app.services.database import database_service


class TierService:
    """Service for managing tier configurations and upgrades."""

    def __init__(self):
        """Initialize tier service."""
        self._config_cache = {}

    async def get_all_tier_configs(self) -> List[TierQuotaConfig]:
        """Get all tier configurations.

        Returns:
            List of all tier configurations
        """
        try:
            with database_service.get_session_maker() as session:
                statement = select(TierQuotaConfig).order_by(TierQuotaConfig.tier_name)
                configs = session.exec(statement).all()

                if not configs:
                    logger.warning("no_tier_configs_found_using_defaults")
                    return self._get_default_tier_configs()

                return configs

        except SQLAlchemyError as e:
            logger.error("database_error_getting_tier_configs", error=str(e))
            return self._get_default_tier_configs()

    async def get_tier_config_by_name(self, tier_name: str) -> Optional[TierQuotaConfig]:
        """Get tier configuration by name with caching.

        Args:
            tier_name: Name of the tier (FREE, PREMIUM, ENTERPRISE)

        Returns:
            TierQuotaConfig if found, None otherwise
        """
        # Check cache first
        if tier_name in self._config_cache:
            return self._config_cache[tier_name]

        try:
            with database_service.get_session_maker() as session:
                statement = select(TierQuotaConfig).where(TierQuotaConfig.tier_name == tier_name)
                config = session.exec(statement).first()

                if config:
                    self._config_cache[tier_name] = config
                    return config

                # Return default configuration
                default_config = self._get_default_tier_config(tier_name)
                if default_config:
                    self._config_cache[tier_name] = default_config

                return default_config

        except SQLAlchemyError as e:
            logger.error("database_error_getting_tier_config", error=str(e), tier_name=tier_name)
            default_config = self._get_default_tier_config(tier_name)
            if default_config:
                self._config_cache[tier_name] = default_config
            return default_config

    async def update_tier_config(self, tier_name: str, **updates) -> bool:
        """Update tier configuration.

        Args:
            tier_name: Name of the tier to update
            **updates: Fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            with database_service.get_session_maker() as session:
                statement = select(TierQuotaConfig).where(TierQuotaConfig.tier_name == tier_name)
                config = session.exec(statement).first()

                if not config:
                    logger.error("tier_config_not_found_for_update", tier_name=tier_name)
                    return False

                # Update fields
                for field, value in updates.items():
                    if hasattr(config, field):
                        setattr(config, field, value)
                    else:
                        logger.warning("invalid_field_for_tier_config", field=field)

                session.add(config)
                session.commit()

                # Clear cache
                if tier_name in self._config_cache:
                    del self._config_cache[tier_name]

                logger.info("tier_config_updated", tier_name=tier_name, updates=list(updates.keys()))
                return True

        except SQLAlchemyError as e:
            logger.error("database_error_updating_tier_config", error=str(e), tier_name=tier_name)
            return False

    def get_upgrade_benefits(self, current_tier: UserTier, target_tier: UserTier) -> Dict[str, Any]:
        """Get upgrade benefits comparison between tiers.

        Args:
            current_tier: User's current tier
            target_tier: Target tier for upgrade

        Returns:
            Dictionary with upgrade benefits and pricing
        """
        benefits = {
            "current_tier": current_tier.value,
            "target_tier": target_tier.value,
            "benefits": [],
            "pricing": self._get_tier_pricing(target_tier),
        }

        if current_tier == UserTier.FREE and target_tier == UserTier.PREMIUM:
            benefits["benefits"] = [
                "50 quiz questions per day (vs 10 free)",
                "100 messages per day (vs 20 free)",
                "Advanced explanations and detailed feedback",
                "Priority support",
                "Detailed progress tracking",
                "No advertisements",
                "Subject-specific insights",
            ]
        elif current_tier == UserTier.FREE and target_tier == UserTier.ENTERPRISE:
            benefits["benefits"] = [
                "Unlimited quiz questions and messages",
                "All Premium features included",
                "Custom curriculum and learning paths",
                "Advanced analytics dashboard",
                "Multi-user management",
                "API access for integrations",
                "Dedicated support",
            ]
        elif current_tier == UserTier.PREMIUM and target_tier == UserTier.ENTERPRISE:
            benefits["benefits"] = [
                "Unlimited quiz questions and messages (vs 50/100 daily limits)",
                "Custom curriculum and learning paths",
                "Advanced analytics dashboard",
                "Multi-user management",
                "API access for integrations",
                "Dedicated support and training",
            ]

        return benefits

    def generate_upgrade_message(self, current_tier: UserTier, quota_type: str) -> str:
        """Generate upgrade message for specific quota limit.

        Args:
            current_tier: User's current tier
            quota_type: Type of quota ('quiz' or 'message')

        Returns:
            Formatted upgrade message
        """
        if current_tier == UserTier.FREE:
            if quota_type == "quiz":
                return """📚 **Quiz Questions Limit Reached!**

You've used all 10 of your daily quiz questions.

🌟 **Upgrade to Premium for:**
• **50 quiz questions per day**
• 100 messages per day
• Advanced explanations
• Progress tracking
• No ads

💰 **Only $9.99/month** - Start learning more today!"""

            elif quota_type == "message":
                return """💬 **Message Limit Reached!**

You've used all 20 of your daily messages.

🌟 **Upgrade to Premium for:**
• **100 messages per day**
• 50 quiz questions per day
• Advanced explanations
• Priority support
• Progress tracking

💰 **Only $9.99/month** - Continue your conversation!"""

        elif current_tier == UserTier.PREMIUM:
            if quota_type == "quiz":
                return """📚 **Premium Quiz Limit Reached!**

You've used all 50 of your daily premium quiz questions.

🚀 **Upgrade to Enterprise for:**
• **Unlimited quiz questions**
• Unlimited messages
• Custom curriculum
• Analytics dashboard
• API access

💰 **Only $29.99/month** - Unlimited learning!"""

            elif quota_type == "message":
                return """💬 **Premium Message Limit Reached!**

You've used all 100 of your daily premium messages.

🚀 **Upgrade to Enterprise for:**
• **Unlimited messages**
• Unlimited quiz questions
• Advanced analytics
• Multi-user management
• Dedicated support

💰 **Only $29.99/month** - Unlimited conversations!"""

        return "You've reached your daily limit. Please try again tomorrow!"

    def _get_default_tier_configs(self) -> List[TierQuotaConfig]:
        """Get default tier configurations."""
        import uuid

        return [
            TierQuotaConfig(
                id=str(uuid.uuid4()),
                tier_name="FREE",
                daily_quiz_limit=10,
                daily_quiz_limit_type="questions_attempted",
                daily_message_limit=20,
                daily_message_limit_type="messages_sent",
                rollover_enabled=False,
                rollover_days=0,
            ),
            TierQuotaConfig(
                id=str(uuid.uuid4()),
                tier_name="PREMIUM",
                daily_quiz_limit=50,
                daily_quiz_limit_type="questions_attempted",
                daily_message_limit=100,
                daily_message_limit_type="messages_sent",
                rollover_enabled=False,
                rollover_days=0,
            ),
            TierQuotaConfig(
                id=str(uuid.uuid4()),
                tier_name="ENTERPRISE",
                daily_quiz_limit=999999,
                daily_quiz_limit_type="questions_attempted",
                daily_message_limit=999999,
                daily_message_limit_type="messages_sent",
                rollover_enabled=False,
                rollover_days=0,
            ),
        ]

    def _get_default_tier_config(self, tier_name: str) -> Optional[TierQuotaConfig]:
        """Get default configuration for a specific tier."""
        default_configs = self._get_default_tier_configs()
        return next((config for config in default_configs if config.tier_name == tier_name), None)

    def _get_tier_pricing(self, tier: UserTier) -> Dict[str, Any]:
        """Get pricing information for a tier."""
        pricing = {
            UserTier.FREE: {"monthly": 0, "yearly": 0, "currency": "USD"},
            UserTier.PREMIUM: {"monthly": 9.99, "yearly": 99.99, "currency": "USD", "savings": "2 months free"},
            UserTier.ENTERPRISE: {"monthly": 29.99, "yearly": 299.99, "currency": "USD", "savings": "2 months free"},
        }

        return pricing.get(tier, {"monthly": 0, "yearly": 0, "currency": "USD"})

    async def get_tier_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics across all tiers.

        Returns:
            Dictionary with tier usage statistics
        """
        try:
            with database_service.get_session_maker() as session:
                from app.models.user import User

                # Count users by tier
                free_users = len(session.exec(select(User).where(User.tier == UserTier.FREE)).all())
                premium_users = len(session.exec(select(User).where(User.tier == UserTier.PREMIUM)).all())
                enterprise_users = len(session.exec(select(User).where(User.tier == UserTier.ENTERPRISE)).all())

                total_users = free_users + premium_users + enterprise_users

                return {
                    "total_users": total_users,
                    "tier_distribution": {
                        "FREE": {
                            "count": free_users,
                            "percentage": (free_users / total_users * 100) if total_users > 0 else 0,
                        },
                        "PREMIUM": {
                            "count": premium_users,
                            "percentage": (premium_users / total_users * 100) if total_users > 0 else 0,
                        },
                        "ENTERPRISE": {
                            "count": enterprise_users,
                            "percentage": (enterprise_users / total_users * 100) if total_users > 0 else 0,
                        },
                    },
                }

        except SQLAlchemyError as e:
            logger.error("database_error_getting_tier_stats", error=str(e))
            return {
                "total_users": 0,
                "tier_distribution": {
                    "FREE": {"count": 0, "percentage": 0},
                    "PREMIUM": {"count": 0, "percentage": 0},
                    "ENTERPRISE": {"count": 0, "percentage": 0},
                },
            }

    def clear_cache(self):
        """Clear the configuration cache."""
        self._config_cache.clear()
        logger.info("tier_service_cache_cleared")

    async def validate_tier_limits(self) -> List[Dict[str, Any]]:
        """Validate that all tier configurations have reasonable limits.

        Returns:
            List of validation issues if any
        """
        issues = []
        configs = await self.get_all_tier_configs()

        for config in configs:
            # Check for negative limits (except -1 for unlimited)
            if config.daily_quiz_limit < -1:
                issues.append(
                    {"tier": config.tier_name, "issue": "Invalid quiz limit", "value": config.daily_quiz_limit}
                )

            if config.daily_message_limit is not None and config.daily_message_limit < -1:
                issues.append(
                    {"tier": config.tier_name, "issue": "Invalid message limit", "value": config.daily_message_limit}
                )

            # Check tier progression
            if config.tier_name == "PREMIUM":
                free_config = await self.get_tier_config_by_name("FREE")
                if (
                    free_config
                    and config.daily_quiz_limit <= free_config.daily_quiz_limit
                    and config.daily_quiz_limit != -1
                ):
                    issues.append(
                        {
                            "tier": config.tier_name,
                            "issue": "Premium limits should be higher than Free limits",
                            "value": f"quiz_limit: {config.daily_quiz_limit}",
                        }
                    )

        return issues


# Create singleton instance
tier_service = TierService()
