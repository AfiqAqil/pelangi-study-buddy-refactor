"""This file contains the LangGraph Agent/workflow and interactions with the LLM."""

import asyncio
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Literal,
    Optional,
)

from asgiref.sync import sync_to_async
from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot
from openai import OpenAIError
from psycopg_pool import AsyncConnectionPool

from app.core.config import (
    Environment,
    settings,
)
from app.core.langgraph.tools import tools
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.prompts import SYSTEM_PROMPT
from app.schemas import (
    GraphState,
    Message,
)
from app.utils import (
    dump_messages,
    prepare_messages,
    trim_messages_by_count,
)


class LangGraphAgent:
    """Manages the LangGraph Agent/workflow and interactions with the LLM.

    This class handles the creation and management of the LangGraph workflow,
    including LLM interactions, database connections, and response processing.
    """

    def __init__(self):
        """Initialize the LangGraph Agent with necessary components."""
        # Use environment-specific LLM model
        # Check if we're using Gemini or OpenAI
        if settings.LLM_PROVIDER == "gemini":
            self.llm = ChatGoogleGenerativeAI(
                model=settings.LLM_MODEL,  # e.g., "gemini-1.5-flash" or "gemini-1.5-pro"
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                google_api_key=settings.LLM_API_KEY,
                max_output_tokens=settings.MAX_TOKENS,
                **self._get_model_kwargs(),
            ).bind_tools(tools)
        else:  # Default to OpenAI
            self.llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                api_key=settings.LLM_API_KEY,
                max_tokens=settings.MAX_TOKENS,
                **self._get_model_kwargs(),
            ).bind_tools(tools)
        self.tools_by_name = {tool.name: tool for tool in tools}
        self._connection_pool: Optional[AsyncConnectionPool] = None
        self._graph: Optional[CompiledStateGraph] = None

        logger.info("llm_initialized", model=settings.LLM_MODEL, environment=settings.ENVIRONMENT.value)

    def _get_model_kwargs(self) -> Dict[str, Any]:
        """Get environment-specific model kwargs.

        Returns:
            Dict[str, Any]: Additional model arguments based on environment
        """
        model_kwargs = {}

        # Development - we can use lower speeds for cost savings
        if settings.ENVIRONMENT == Environment.DEVELOPMENT:
            model_kwargs["top_p"] = 0.8

        # Production - use higher quality settings
        elif settings.ENVIRONMENT == Environment.PRODUCTION:
            model_kwargs["top_p"] = 0.95
            model_kwargs["presence_penalty"] = 0.1
            model_kwargs["frequency_penalty"] = 0.1

        return model_kwargs

    async def _get_connection_pool(self) -> AsyncConnectionPool:
        """Get a PostgreSQL connection pool using environment-specific settings.

        Returns:
            AsyncConnectionPool: A connection pool for PostgreSQL database.
        """
        if self._connection_pool is None:
            try:
                # Configure pool size based on environment
                max_size = settings.POSTGRES_POOL_SIZE

                self._connection_pool = AsyncConnectionPool(
                    settings.POSTGRES_URL,
                    open=False,
                    max_size=max_size,
                    min_size=2,  # Maintain minimum connections
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT,
                        "application_name": f"langgraph-agent-{settings.ENVIRONMENT.value}",
                        "prepare_threshold": None,
                    },
                    # Pool configuration
                    timeout=settings.POSTGRES_POOL_TIMEOUT,
                    max_idle=settings.POSTGRES_MAX_IDLE,
                    max_lifetime=settings.POSTGRES_MAX_LIFETIME,
                )
                await self._connection_pool.open()
                logger.info(
                    "connection_pool_created",
                    max_size=max_size,
                    min_size=2,
                    timeout=settings.POSTGRES_POOL_TIMEOUT,
                    max_idle=settings.POSTGRES_MAX_IDLE,
                    max_lifetime=settings.POSTGRES_MAX_LIFETIME,
                    environment=settings.ENVIRONMENT.value,
                )
            except Exception as e:
                logger.error("connection_pool_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # In production, we might want to degrade gracefully
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_connection_pool", environment=settings.ENVIRONMENT.value)
                    return None
                raise e
        return self._connection_pool

    async def close_connection_pool(self) -> None:
        """Close the PostgreSQL connection pool gracefully."""
        if self._connection_pool:
            try:
                await self._connection_pool.close()
                self._connection_pool = None
                logger.info("connection_pool_closed", environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("connection_pool_close_failed", error=str(e), environment=settings.ENVIRONMENT.value)

    async def _chat(self, state: GraphState) -> dict:
        """Process the chat state and generate a response.

        Args:
            state (GraphState): The current state of the conversation.

        Returns:
            dict: Updated state with new messages.
        """
        messages = prepare_messages(state.messages, self.llm, SYSTEM_PROMPT)

        llm_calls_num = 0

        # Configure retry attempts based on environment
        max_retries = settings.MAX_LLM_CALL_RETRIES

        for attempt in range(max_retries):
            try:
                # Get model name - different attribute for different providers
                model_name = getattr(self.llm, "model_name", None) or getattr(self.llm, "model", "unknown")
                with llm_inference_duration_seconds.labels(model=model_name).time():
                    generated_state = {"messages": [await self.llm.ainvoke(dump_messages(messages))]}
                logger.info(
                    "llm_response_generated",
                    session_id=state.session_id,
                    llm_calls_num=llm_calls_num + 1,
                    model=settings.LLM_MODEL,
                    environment=settings.ENVIRONMENT.value,
                )
                return generated_state
            except OpenAIError as e:
                logger.error(
                    "llm_call_failed",
                    llm_calls_num=llm_calls_num,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    environment=settings.ENVIRONMENT.value,
                )
                llm_calls_num += 1

                # In production, we might want to fall back to a more reliable model
                if settings.ENVIRONMENT == Environment.PRODUCTION and attempt == max_retries - 2:
                    fallback_model = "gpt-4o"
                    logger.warning(
                        "using_fallback_model", model=fallback_model, environment=settings.ENVIRONMENT.value
                    )
                    # Set model name appropriately based on provider
                    if hasattr(self.llm, "model_name"):
                        self.llm.model_name = fallback_model
                    elif hasattr(self.llm, "model"):
                        self.llm.model = fallback_model

                continue

        raise Exception(f"Failed to get a response from the LLM after {max_retries} attempts")

    # Define our tool node
    async def _tool_call(self, state: GraphState) -> GraphState:
        """Process tool calls from the last message.

        Args:
            state: The current agent state containing messages and tool calls.

        Returns:
            Dict with updated messages containing tool responses.
        """
        outputs = []
        for tool_call in state.messages[-1].tool_calls:
            tool_result = await self.tools_by_name[tool_call["name"]].ainvoke(tool_call["args"])
            outputs.append(
                ToolMessage(
                    content=tool_result,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}

    def _should_continue(self, state: GraphState) -> Literal["end", "continue"]:
        """Determine if the agent should continue or end based on the last message.

        Args:
            state: The current agent state containing messages.

        Returns:
            Literal["end", "continue"]: "end" if there are no tool calls, "continue" otherwise.
        """
        messages = state.messages
        last_message = messages[-1]
        # If there is no function call, then we finish
        if not last_message.tool_calls:
            return "end"
        # Otherwise if there is, we continue
        else:
            return "continue"

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """Create and configure the LangGraph workflow.

        Returns:
            Optional[CompiledStateGraph]: The configured LangGraph instance or None if init fails
        """
        if self._graph is None:
            try:
                graph_builder = StateGraph(GraphState)
                graph_builder.add_node("chat", self._chat)
                graph_builder.add_node("tool_call", self._tool_call)
                graph_builder.add_conditional_edges(
                    "chat",
                    self._should_continue,
                    {"continue": "tool_call", "end": END},
                )
                graph_builder.add_edge("tool_call", "chat")
                graph_builder.set_entry_point("chat")
                graph_builder.set_finish_point("chat")

                # Get connection pool (may be None in production if DB unavailable)
                connection_pool = await self._get_connection_pool()
                if connection_pool:
                    checkpointer = AsyncPostgresSaver(connection_pool)
                    await checkpointer.setup()
                else:
                    # In production, proceed without checkpointer if needed
                    checkpointer = None
                    if settings.ENVIRONMENT != Environment.PRODUCTION:
                        raise Exception("Connection pool initialization failed")

                self._graph = graph_builder.compile(
                    checkpointer=checkpointer, name=f"{settings.PROJECT_NAME} Agent ({settings.ENVIRONMENT.value})"
                )

                logger.info(
                    "graph_created",
                    graph_name=f"{settings.PROJECT_NAME} Agent",
                    environment=settings.ENVIRONMENT.value,
                    has_checkpointer=checkpointer is not None,
                )
            except Exception as e:
                logger.error("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # In production, we don't want to crash the app
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_graph")
                    return None
                raise e

        return self._graph

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
    ) -> dict:
        """Get a response from the LLM with tracking of new messages.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for Langfuse tracking.
            user_id (Optional[str]): The user ID for Langfuse tracking.

        Returns:
            dict: Contains:
                - 'messages': All messages in the conversation
                - 'new_messages': Only the newly generated messages
                - 'new_start_index': Index where new messages begin
        """
        if self._graph is None:
            self._graph = await self.create_graph()
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": [CallbackHandler()],
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": False,
            },
        }
        try:
            # Try to get message count from Redis cache first (performance optimization)
            from app.services.redis import redis_service
            from app.core.cache import ConversationCache

            async def fetch_message_count():
                # Optimized: Use async database query with timeout
                try:
                    # Set timeout for database queries to prevent hanging
                    import asyncio

                    state_before = await asyncio.wait_for(
                        sync_to_async(self._graph.get_state)(config),
                        timeout=3.0,  # 3 second timeout
                    )
                    return len(state_before.values.get("messages", [])) if state_before.values else 0
                except asyncio.TimeoutError:
                    logger.warning("db_state_query_timeout", session_id=session_id)
                    # Return 0 for new conversations to avoid blocking
                    return 0
                except Exception as e:
                    logger.error("db_state_query_failed", session_id=session_id, error=str(e))
                    return 0

            # Get message count from cache or database with faster cache TTL
            messages_before_count = await ConversationCache.get_or_set_message_count(
                session_id,
                fetch_message_count,
                ttl=600,  # Cache for 10 minutes (longer cache)
            )

            # Invoke the graph with new messages
            response = await self._graph.ainvoke(
                {"messages": dump_messages(messages), "session_id": session_id}, config
            )

            # Process all messages
            all_messages = self.__process_messages(response["messages"])

            # Calculate where new messages start (after original + user input)
            new_start_index = messages_before_count + len(messages)

            # Update cache with new message count for next request
            new_message_count = len(all_messages)
            if new_message_count > messages_before_count:
                # Use fire-and-forget cache update to avoid blocking response
                asyncio.create_task(redis_service.set_message_count(session_id, new_message_count, ttl=600))
                logger.debug(
                    "message_count_cache_updated",
                    session_id=session_id,
                    old_count=messages_before_count,
                    new_count=new_message_count,
                )

            return {
                "messages": all_messages,
                "new_messages": all_messages[new_start_index:],
                "new_start_index": new_start_index,
            }
        except Exception as e:
            logger.error(f"Error getting response: {str(e)}")
            raise e

    async def get_stream_response(
        self, messages: list[Message], session_id: str, user_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Get a stream response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for the conversation.
            user_id (Optional[str]): The user ID for the conversation.

        Yields:
            str: Tokens of the LLM response.
        """
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": [
                CallbackHandler(
                    environment=settings.ENVIRONMENT.value, debug=False, user_id=user_id, session_id=session_id
                )
            ],
        }
        if self._graph is None:
            self._graph = await self.create_graph()

        try:
            async for token, _ in self._graph.astream(
                {"messages": dump_messages(messages), "session_id": session_id}, config, stream_mode="messages"
            ):
                try:
                    yield token.content
                except Exception as token_error:
                    logger.error("Error processing token", error=str(token_error), session_id=session_id)
                    # Continue with next token even if current one fails
                    continue
        except Exception as stream_error:
            logger.error("Error in stream processing", error=str(stream_error), session_id=session_id)
            raise stream_error

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Get the chat history for a given thread ID.

        Args:
            session_id (str): The session ID for the conversation.

        Returns:
            list[Message]: The chat history with context window applied.
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        state: StateSnapshot = await sync_to_async(self._graph.get_state)(
            config={"configurable": {"thread_id": session_id}}
        )

        if not state.values:
            return []

        # Get all messages and apply context window
        all_messages = self.__process_messages(state.values["messages"])
        windowed_messages = trim_messages_by_count(all_messages, settings.CONTEXT_WINDOW_SIZE)

        return windowed_messages

    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        openai_style_messages = convert_to_openai_messages(messages)
        # keep just assistant and user messages
        return [
            Message(**message)
            for message in openai_style_messages
            if message["role"] in ["assistant", "user"] and message["content"]
        ]

    async def clear_chat_history(self, session_id: str) -> None:
        """Clear all chat history for a given thread ID.

        Args:
            session_id: The ID of the session to clear history for.

        Raises:
            Exception: If there's an error clearing the chat history.
        """
        try:
            # Make sure the pool is initialized in the current event loop
            conn_pool = await self._get_connection_pool()

            if conn_pool is None:
                logger.warning(
                    "no_connection_pool", session_id=session_id, message="Cannot clear history without connection pool"
                )
                return

            # Use a connection with timeout and retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with conn_pool.connection() as conn:
                        for table in settings.CHECKPOINT_TABLES:
                            try:
                                await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))
                                logger.info(f"Cleared {table} for session {session_id}")
                            except Exception as table_error:
                                logger.error(f"Error clearing {table}", error=str(table_error), session_id=session_id)
                                raise table_error
                    break  # Success, exit retry loop

                except Exception as conn_error:
                    logger.warning(
                        "connection_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error=str(conn_error),
                        session_id=session_id,
                    )
                    if attempt == max_retries - 1:
                        raise conn_error
                    # Wait before retry with exponential backoff
                    await asyncio.sleep(2**attempt)

        except Exception as e:
            logger.error("Failed to clear chat history", error=str(e), session_id=session_id)
            raise
