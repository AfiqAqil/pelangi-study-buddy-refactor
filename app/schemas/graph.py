"""This file contains the graph schema for the application."""

import re
import uuid
from typing import Annotated, Dict, Any

from langgraph.graph.message import add_messages
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.core.logging import logger


class GraphState(BaseModel):
    """State definition for the LangGraph Agent/Workflow with versioning support."""

    # Current schema version
    CURRENT_VERSION: int = 1

    version: int = Field(
        default=CURRENT_VERSION, 
        description="State schema version for migrations"
    )
    messages: Annotated[list, add_messages] = Field(
        default_factory=list, 
        description="The messages in the conversation"
    )
    session_id: str = Field(..., description="The unique identifier for the conversation session")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for extensibility"
    )

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """Validate that the session ID is a valid UUID or follows safe pattern.

        Args:
            v: The thread ID to validate

        Returns:
            str: The validated session ID

        Raises:
            ValueError: If the session ID is not valid
        """
        # Try to validate as UUID
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            # If not a UUID, check for safe characters only
            if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
                raise ValueError("Session ID must contain only alphanumeric characters, underscores, and hyphens")
            return v

    def migrate_to_latest(self) -> "GraphState":
        """Migrate this state to the latest version.
        
        Returns:
            GraphState: Migrated state instance
        """
        if self.version == self.CURRENT_VERSION:
            return self  # Already current version
        
        logger.info(
            "graph_state_migration_start",
            session_id=self.session_id,
            from_version=self.version,
            to_version=self.CURRENT_VERSION,
        )
        
        # Apply migrations step by step
        migrated_state = self
        for target_version in range(self.version + 1, self.CURRENT_VERSION + 1):
            migrated_state = self._migrate_to_version(migrated_state, target_version)
            
        logger.info(
            "graph_state_migration_complete",
            session_id=self.session_id,
            final_version=migrated_state.version,
        )
        
        return migrated_state

    def _migrate_to_version(self, state: "GraphState", target_version: int) -> "GraphState":
        """Migrate state to a specific version.
        
        Args:
            state: Current state to migrate
            target_version: Target version to migrate to
            
        Returns:
            GraphState: Migrated state
        """
        if target_version == 1:
            # Future migration example:
            # If we had a version 0->1 migration, it would be here
            # For now, version 1 is the initial version
            return state.model_copy(update={"version": 1})
        elif target_version == 2:
            # Example future migration from v1 to v2 would be implemented here
            pass
        
        # If no specific migration is needed, just update version
        return state.model_copy(update={"version": target_version})

    def is_compatible(self) -> bool:
        """Check if this state version is compatible with current code.
        
        Returns:
            True if compatible, False if migration is needed
        """
        # States within 1 version are considered compatible
        return abs(self.version - self.CURRENT_VERSION) <= 1

    def get_migration_info(self) -> Dict[str, Any]:
        """Get information about migration requirements.
        
        Returns:
            Dictionary with migration information
        """
        return {
            "current_version": self.version,
            "target_version": self.CURRENT_VERSION,
            "migration_needed": self.version != self.CURRENT_VERSION,
            "compatible": self.is_compatible(),
            "session_id": self.session_id,
        }
