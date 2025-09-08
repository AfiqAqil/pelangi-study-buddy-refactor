#!/usr/bin/env python3
"""Script to insert default tier configurations into the database.

This script populates the tier_quota_configs table with default configurations
for FREE, PREMIUM, and ENTERPRISE tiers.
"""

import sys
import os
import uuid
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging import logger
from app.services.database import database_service
from app.models.daily_quota import TierQuotaConfig


def get_default_tier_configs():
    """Get the default tier configurations to insert.
    
    Returns:
        List of tier configuration dictionaries
    """
    return [
        {
            "id": str(uuid.uuid4()),
            "tier_name": "FREE",
            "daily_quiz_limit": 10,
            "daily_quiz_limit_type": "questions_attempted",
            "daily_message_limit": 20,
            "daily_message_limit_type": "messages_sent",
            "rollover_enabled": False,
            "rollover_days": 0
        },
        {
            "id": str(uuid.uuid4()),
            "tier_name": "PREMIUM",
            "daily_quiz_limit": 50,
            "daily_quiz_limit_type": "questions_attempted",
            "daily_message_limit": 100,
            "daily_message_limit_type": "messages_sent",
            "rollover_enabled": False,
            "rollover_days": 0
        },
        {
            "id": str(uuid.uuid4()),
            "tier_name": "ENTERPRISE",
            "daily_quiz_limit": 999999,  # Unlimited
            "daily_quiz_limit_type": "questions_attempted",
            "daily_message_limit": 999999,  # Unlimited
            "daily_message_limit_type": "messages_sent",
            "rollover_enabled": False,
            "rollover_days": 0
        }
    ]


def tier_config_exists(session: Session, tier_name: str) -> TierQuotaConfig:
    """Check if a tier configuration already exists in the database.
    
    Args:
        session: Database session
        tier_name: Name of the tier to check
        
    Returns:
        TierQuotaConfig if exists, None otherwise
    """
    try:
        statement = select(TierQuotaConfig).where(TierQuotaConfig.tier_name == tier_name)
        existing = session.exec(statement).first()
        return existing
    except SQLAlchemyError:
        return None


def insert_tier_config(session: Session, config_data: dict) -> bool:
    """Insert a single tier configuration into the database.
    
    Args:
        session: Database session
        config_data: Dictionary containing tier configuration
        
    Returns:
        True if insertion was successful, False otherwise
    """
    try:
        config = TierQuotaConfig(
            id=config_data["id"],
            tier_name=config_data["tier_name"],
            daily_quiz_limit=config_data["daily_quiz_limit"],
            daily_quiz_limit_type=config_data["daily_quiz_limit_type"],
            daily_message_limit=config_data["daily_message_limit"],
            daily_message_limit_type=config_data["daily_message_limit_type"],
            rollover_enabled=config_data["rollover_enabled"],
            rollover_days=config_data["rollover_days"]
        )
        
        session.add(config)
        session.commit()
        session.refresh(config)
        
        logger.info(
            "tier_config_inserted",
            tier_name=config.tier_name,
            quiz_limit=config.daily_quiz_limit,
            message_limit=config.daily_message_limit
        )
        
        return True
        
    except SQLAlchemyError as e:
        logger.error(
            "tier_config_insertion_failed",
            tier_name=config_data["tier_name"],
            error=str(e)
        )
        session.rollback()
        return False


def update_tier_config(session: Session, existing_config: TierQuotaConfig, config_data: dict) -> bool:
    """Update an existing tier configuration with new data.
    
    Args:
        session: Database session
        existing_config: Existing configuration record
        config_data: New configuration data
        
    Returns:
        True if update was successful, False otherwise
    """
    try:
        existing_config.daily_quiz_limit = config_data["daily_quiz_limit"]
        existing_config.daily_quiz_limit_type = config_data["daily_quiz_limit_type"]
        existing_config.daily_message_limit = config_data["daily_message_limit"]
        existing_config.daily_message_limit_type = config_data["daily_message_limit_type"]
        existing_config.rollover_enabled = config_data["rollover_enabled"]
        existing_config.rollover_days = config_data["rollover_days"]
        
        session.add(existing_config)
        session.commit()
        
        logger.info(
            "tier_config_updated",
            tier_name=existing_config.tier_name,
            quiz_limit=existing_config.daily_quiz_limit,
            message_limit=existing_config.daily_message_limit
        )
        
        return True
        
    except SQLAlchemyError as e:
        logger.error(
            "tier_config_update_failed",
            tier_name=config_data["tier_name"],
            error=str(e)
        )
        session.rollback()
        return False


def validate_tier_configs():
    """Validate that tier configurations make sense.
    
    Returns:
        List of validation messages
    """
    configs = get_default_tier_configs()
    issues = []
    
    # Check that limits increase with tier level
    tiers = {config["tier_name"]: config for config in configs}
    
    free_quiz = tiers.get("FREE", {}).get("daily_quiz_limit", 0)
    premium_quiz = tiers.get("PREMIUM", {}).get("daily_quiz_limit", 0)
    enterprise_quiz = tiers.get("ENTERPRISE", {}).get("daily_quiz_limit", 0)
    
    if premium_quiz <= free_quiz and premium_quiz != -1 and enterprise_quiz != 999999:
        issues.append("⚠️  PREMIUM quiz limit should be higher than FREE")
    
    free_message = tiers.get("FREE", {}).get("daily_message_limit", 0)
    premium_message = tiers.get("PREMIUM", {}).get("daily_message_limit", 0)
    
    if premium_message <= free_message and premium_message != -1:
        issues.append("⚠️  PREMIUM message limit should be higher than FREE")
    
    return issues


def main():
    """Main function to insert tier configurations."""
    print("🚀 Starting tier configurations insertion...")
    print(f"Environment: {settings.ENVIRONMENT.value}")
    print(f"Database URL: {settings.POSTGRES_URL[:50]}...")
    
    # Validate configurations first
    issues = validate_tier_configs()
    if issues:
        print("\n⚠️  Configuration validation issues found:")
        for issue in issues:
            print(f"   {issue}")
        print("\nProceeding anyway, but please review the configurations.")
    
    try:
        configs_data = get_default_tier_configs()
        print(f"\n🔧 Found {len(configs_data)} tier configurations to process:")
        
        for config in configs_data:
            tier_name = config["tier_name"]
            quiz_limit = config["daily_quiz_limit"]
            message_limit = config["daily_message_limit"]
            
            if quiz_limit == 999999:
                quiz_display = "Unlimited"
            else:
                quiz_display = str(quiz_limit)
                
            if message_limit == 999999:
                message_display = "Unlimited"
            else:
                message_display = str(message_limit)
                
            print(f"   🎯 {tier_name}: {quiz_display} quiz, {message_display} messages per day")
        
        success_count = 0
        update_count = 0
        error_count = 0
        
        with database_service.get_session_maker() as session:
            for config_data in configs_data:
                tier_name = config_data["tier_name"]
                print(f"\n🔧 Processing tier: {tier_name}")
                
                # Check if configuration already exists
                existing_config = tier_config_exists(session, tier_name)
                
                if existing_config:
                    print("   ⚠️  Configuration already exists, updating...")
                    if update_tier_config(session, existing_config, config_data):
                        update_count += 1
                        print("   ✅ Updated successfully")
                    else:
                        error_count += 1
                        print("   ❌ Update failed")
                else:
                    print("   🆕 Creating new configuration...")
                    if insert_tier_config(session, config_data):
                        success_count += 1
                        print("   ✅ Created successfully")
                    else:
                        error_count += 1
                        print("   ❌ Creation failed")
        
        print("\n🎉 Tier configurations insertion completed!")
        print(f"   ✅ Created: {success_count}")
        print(f"   🔄 Updated: {update_count}")
        print(f"   ❌ Errors: {error_count}")
        print(f"   📊 Total processed: {len(configs_data)}")
        
        # Verify insertion by showing all configurations
        try:
            print("\n📋 Current tier configurations in database:")
            with database_service.get_session_maker() as session:
                all_configs = session.exec(select(TierQuotaConfig).order_by(TierQuotaConfig.tier_name)).all()
                
                for config in all_configs:
                    quiz_display = "Unlimited" if config.daily_quiz_limit >= 999999 else str(config.daily_quiz_limit)
                    message_display = "Unlimited" if config.daily_message_limit >= 999999 else str(config.daily_message_limit)
                    
                    print(f"   🎯 {config.tier_name}: {quiz_display} quiz, {message_display} messages per day")
                
                print(f"\n   📊 Total configurations: {len(all_configs)}")
                
        except Exception as e:
            print(f"   ⚠️  Could not verify configurations: {e}")
        
        if error_count == 0:
            print("\n🌟 All tier configurations processed successfully!")
            print("\n💡 Next steps:")
            print("   1. Restart your application to clear any cached configurations")
            print("   2. Test quota validation with different user tiers")
            print("   3. Monitor quota usage in your application logs")
            return 0
        else:
            print(f"\n⚠️  {error_count} configurations had errors. Check logs for details.")
            return 1
            
    except Exception as e:
        logger.error("tier_configs_insertion_script_failed", error=str(e), exc_info=True)
        print(f"\n💥 Script failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)