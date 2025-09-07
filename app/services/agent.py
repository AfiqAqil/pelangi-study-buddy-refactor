"""Global LangGraph agent service instance."""

from app.core.langgraph.graph import LangGraphAgent
from app.core.logging import logger


class AgentService:
    """Service to manage a single LangGraph agent instance."""

    def __init__(self):
        """Initialize the agent service."""
        self._agent: LangGraphAgent | None = None

    def get_agent(self) -> LangGraphAgent:
        """Get the agent instance, creating it if necessary."""
        if self._agent is None:
            self._agent = LangGraphAgent()
        return self._agent

    async def close(self) -> None:
        """Close the agent and its resources."""
        if self._agent:
            try:
                await self._agent.close_connection_pool()
                logger.info("agent_service_closed")
            except Exception as e:
                logger.error("agent_service_close_failed", error=str(e))


# Global agent service instance
agent_service = AgentService()
