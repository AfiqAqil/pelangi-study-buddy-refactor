"""This file contains the graph schema for the application."""

import re
import uuid
from typing import Annotated, Any, Dict, List, Literal, Optional

from langgraph.graph.message import add_messages
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.core.logging import logger


class ToolResult(BaseModel):
    """Result from tool execution with lifecycle information."""
    
    content: str = Field(..., description="User-facing message")
    status: Literal["complete", "partial", "error", "retry"] = Field(..., description="Tool execution status")
    next_action: Optional[str] = Field(None, description="Hint for next action")
    data: Dict[str, Any] = Field(default_factory=dict, description="Structured data from tool")


class GraphState(BaseModel):
    """State definition for the LangGraph Agent/Workflow with versioning support."""

    # Current schema version
    CURRENT_VERSION: int = 3

    version: int = Field(default=CURRENT_VERSION, description="State schema version for migrations")
    messages: Annotated[list, add_messages] = Field(
        default_factory=list, description="The messages in the conversation"
    )
    session_id: str = Field(..., description="The unique identifier for the conversation session")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata for extensibility")
    
    # Tool lifecycle fields (added in version 2)
    last_tool_result: Optional[ToolResult] = Field(None, description="Result from last tool execution")
    max_iterations: int = Field(default=20, description="Maximum allowed chat/tool cycles")
    iteration_count: int = Field(default=0, description="Number of chat/tool cycles completed")
    
    # Onboarding state fields (added in version 3)
    onboarding_data: Dict[str, Any] = Field(default_factory=dict, description="Collected onboarding profile data")
    onboarding_status: Literal["not_started", "in_progress", "ready_for_confirmation", "completed"] = Field(
        default="not_started", description="Current onboarding status"
    )
    onboarding_missing_fields: List[str] = Field(default_factory=list, description="Fields still needed for onboarding")
    onboarding_validation_errors: Dict[str, str] = Field(default_factory=dict, description="Validation errors from onboarding")

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
            # Migration from v1 to v2: Add tool lifecycle fields
            return state.model_copy(update={
                "version": 2,
                "last_tool_result": None,
                "max_iterations": 20,
                "iteration_count": 0
            })
        elif target_version == 3:
            # Migration from v2 to v3: Add onboarding state fields
            return state.model_copy(update={
                "version": 3,
                "onboarding_data": {},
                "onboarding_status": "not_started",
                "onboarding_missing_fields": [],
                "onboarding_validation_errors": {}
            })

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
