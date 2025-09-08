"""This file contains the LangGraph Agent/workflow and interactions with the LLM."""

import asyncio
from typing import (
    AsyncGenerator,
    Literal,
    Optional,
)

from asgiref.sync import sync_to_async
from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
    convert_to_openai_messages,
)
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
from app.core.llm.provider import create_llm_provider
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.prompts import SYSTEM_PROMPT
from app.schemas import (
    GraphState,
    Message,
)
from app.schemas.graph import ToolResult
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
        # Create LLM provider using factory
        self.llm_provider = create_llm_provider()
        self.llm = self.llm_provider.get_llm()
        self.tools_by_name = {tool.name: tool for tool in tools}
        self._connection_pool: Optional[AsyncConnectionPool] = None
        self._graph: Optional[CompiledStateGraph] = None

    def __del__(self):
        """Cleanup resources when the agent is destroyed."""
        # Note: This is a safety net. Proper cleanup should use close_connection_pool()
        if self._connection_pool:
            logger.warning(
                "connection_pool_not_closed_properly",
                message="Connection pool was not closed properly. Use close_connection_pool()",
            )
            # Can't await in destructor, so just set to None
            self._connection_pool = None

    def get_model_name(self) -> str:
        """Get the model name from the LLM provider.

        Returns:
            str: The model name, handling different provider attribute names
        """
        # Use the provider's centralized method
        return self.llm_provider.get_model_name()

    def _detect_language(self, messages: list[str]) -> str:
        """Detect language from recent user messages.
        
        Args:
            messages: List of recent message contents
            
        Returns:
            str: Detected language code (en, ms, zh)
        """
        combined_text = " ".join(messages)
        
        # Simple language detection based on character patterns
        if not combined_text:
            return "en"  # Default to English
        
        # Check for Chinese characters
        chinese_chars = sum(1 for char in combined_text if '\u4e00' <= char <= '\u9fff')
        if chinese_chars > len(combined_text) * 0.1:  # 10% threshold
            return "zh"
        
        # Check for Malay/Indonesian indicators (common words and patterns)
        malay_indicators = [
            'adalah', 'dengan', 'yang', 'untuk', 'dalam', 'pada', 'atau', 'juga', 
            'akan', 'telah', 'sudah', 'belum', 'tidak', 'bukan', 'saya', 'anda',
            'kita', 'mereka', 'dia', 'ini', 'itu', 'bagaimana', 'mengapa', 'apa'
        ]
        
        words = combined_text.lower().split()
        malay_word_count = sum(1 for word in words if word in malay_indicators)
        
        if len(words) > 0 and malay_word_count / len(words) > 0.15:  # 15% threshold
            return "ms"
        
        return "en"  # Default to English
    
    def _create_rag_aware_prompt(self, state: GraphState) -> str:
        """Create an enhanced system prompt with RAG enforcement hints.
        
        Args:
            state: Current graph state
            
        Returns:
            str: Enhanced system prompt
        """
        base_prompt = SYSTEM_PROMPT
        
        # Add RAG hints if RAG is enabled
        if settings.RAG_ENABLED:
            try:
                from app.core.rag.classifier import classify_content, ContentType
                
                # Get subject context
                subject_context = state.metadata.get("subject_context", {}) if state.metadata else {}
                
                # Get recent user messages for content classification
                user_messages = [msg for msg in state.messages if hasattr(msg, 'role') and msg.role == "user"]
                if user_messages:
                    last_user_message = user_messages[-1].content if hasattr(user_messages[-1], 'content') else ""
                    
                    # Classify content type
                    content_type = classify_content(last_user_message, subject_context)
                    
                    # Add educational content hint
                    if content_type == ContentType.EDUCATIONAL:
                        hint = "\n🎯 EDUCATIONAL CONTENT DETECTED: Use RAG tools (comprehensive_rag_search, generate_rag_answer, or qdrant_retriever) to provide textbook-based answers."
                        base_prompt += hint
                        
                        logger.debug(
                            "rag_hint_added_to_prompt",
                            content_type=content_type.value,
                            session_id=state.session_id
                        )
                
            except ImportError:
                logger.debug("rag_classifier_not_available_for_prompt")
            except Exception as e:
                logger.error("rag_prompt_enhancement_failed", error=str(e))
        
        return base_prompt

    async def get_message_count_async(self, session_id: str) -> int:
        """Get message count using native async query.

        Args:
            session_id: Session ID to count messages for

        Returns:
            int: Number of messages for the session
        """
        connection_pool = await self._get_connection_pool()
        if not connection_pool:
            logger.warning("no_connection_pool_for_message_count", session_id=session_id)
            return 0

        try:
            async with connection_pool.connection() as conn:
                # Query the LangGraph checkpoint tables directly
                # Use parameterized query to prevent SQL injection
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT COUNT(*) 
                        FROM checkpoint_writes 
                        WHERE thread_id = %s 
                        AND channel = 'messages'
                        """,
                        (session_id,),
                    )
                    result = await cur.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logger.error("async_message_count_failed", session_id=session_id, error=str(e))
            return 0

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
                logger.info("connection_pool_closed", environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("connection_pool_close_failed", error=str(e), environment=settings.ENVIRONMENT.value)
            finally:
                # Always clear the reference to prevent reuse of broken pool
                self._connection_pool = None

    async def _chat(self, state: GraphState) -> dict:
        """Process the chat state and generate a response.

        Args:
            state (GraphState): The current state of the conversation.

        Returns:
            dict: Updated state with new messages and incremented iteration count.
        """
        # Increment iteration counter for loop protection
        current_iterations = getattr(state, 'iteration_count', 0) + 1
        
        logger.debug(
            "chat_iteration_started",
            session_id=state.session_id,
            iteration_count=current_iterations,
            max_iterations=getattr(state, 'max_iterations', settings.MAX_GRAPH_ITERATIONS)
        )
        
        # Note: RAG enforcement is now handled through tool selection in LLM response
        # The simplified architecture lets the LLM decide when to use RAG tools based on prompts
        
        # Prepare messages with enhanced system prompt for RAG awareness
        enhanced_system_prompt = self._create_rag_aware_prompt(state)
        messages = prepare_messages(state.messages, self.llm, enhanced_system_prompt)

        llm_calls_num = 0

        # Configure retry attempts based on environment
        max_retries = settings.MAX_LLM_CALL_RETRIES

        for attempt in range(max_retries):
            try:
                # Use the centralized method to get model name
                model_name = self.get_model_name()
                with llm_inference_duration_seconds.labels(model=model_name).time():
                    generated_state = {
                        "messages": [await self.llm.ainvoke(dump_messages(messages))],
                        "iteration_count": current_iterations
                    }
                logger.info(
                    "llm_response_generated",
                    session_id=state.session_id,
                    llm_calls_num=llm_calls_num + 1,
                    iteration_count=current_iterations,
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
            Dict with updated messages and last tool result.
        """
        outputs = []
        last_tool_result = None
        
        for tool_call in state.messages[-1].tool_calls:
            try:
                # Prepare tool arguments with metadata injection
                tool_args = tool_call["args"].copy()

                # Inject user_id and context for tools that require it
                tool_name = tool_call["name"]
                if tool_name in ["select_subject", "get_subject_context"]:
                    # Get user_id from state metadata
                    user_id = state.metadata.get("user_id") if state.metadata else None
                    if user_id:
                        tool_args["user_id"] = user_id
                        logger.debug(
                            "injected_user_id_to_tool",
                            tool_name=tool_name,
                            user_id=user_id,
                            session_id=state.session_id,
                        )
                    else:
                        logger.warning("missing_user_id_for_tool", tool_name=tool_name, session_id=state.session_id)
                
                # Inject context for RAG tools
                elif tool_name in ["qdrant_retriever", "generate_rag_answer", "comprehensive_rag_search"]:
                    # Get subject context from state metadata
                    subject_context = state.metadata.get("subject_context", {}) if state.metadata else {}
                    book_code = subject_context.get("book_code")
                    
                    # Inject book_code if available and not already specified
                    if book_code and "book_code" not in tool_args:
                        tool_args["book_code"] = book_code
                        logger.debug(
                            "injected_book_code_to_rag_tool",
                            tool_name=tool_name,
                            book_code=book_code,
                            session_id=state.session_id,
                        )
                    
                    # Inject session_id for comprehensive_rag_search to enable memory
                    if tool_name == "comprehensive_rag_search" and "session_id" not in tool_args:
                        tool_args["session_id"] = state.session_id
                        logger.debug(
                            "injected_session_id_to_rag_tool",
                            tool_name=tool_name,
                            session_id=state.session_id,
                        )
                    
                    # Auto-detect language if not specified
                    if "language" not in tool_args:
                        # Simple language detection based on recent messages
                        recent_user_messages = [
                            msg.content for msg in state.messages[-3:] 
                            if hasattr(msg, 'content') and msg.content
                        ]
                        language = self._detect_language(recent_user_messages)
                        tool_args["language"] = language
                        logger.debug(
                            "injected_language_to_rag_tool",
                            tool_name=tool_name,
                            language=language,
                            session_id=state.session_id,
                        )

                # Execute the tool with enhanced arguments
                tool_result_raw = await self.tools_by_name[tool_name].ainvoke(tool_args)
                
                # Parse ToolResult if it's JSON, otherwise treat as simple string
                try:
                    import json
                    tool_result_dict = json.loads(tool_result_raw)
                    parsed_result = ToolResult(**tool_result_dict)
                    last_tool_result = parsed_result
                    display_content = parsed_result.content
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Legacy tool that returns plain string
                    display_content = tool_result_raw
                    last_tool_result = ToolResult(
                        content=tool_result_raw,
                        status="complete",
                        next_action="respond_to_user"
                    )
                
                outputs.append(
                    ToolMessage(
                        content=display_content,
                        name=tool_name,
                        tool_call_id=tool_call["id"],
                    )
                )
                logger.debug("tool_call_success", tool_name=tool_name, session_id=state.session_id)
            except Exception as e:
                error_message = f"Tool execution failed: {str(e)}"
                logger.error("tool_call_failed", tool_name=tool_call["name"], error=str(e), session_id=state.session_id)
                
                last_tool_result = ToolResult(
                    content=error_message,
                    status="error",
                    next_action="retry_or_handle_error"
                )
                
                outputs.append(
                    ToolMessage(
                        content=error_message,
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                        additional_kwargs={"error": True, "error_type": type(e).__name__},
                    )
                )
        return {
            "messages": outputs,
            "last_tool_result": last_tool_result
        }

    def _should_continue(self, state: GraphState) -> Literal["end", "continue"]:
        """Determine if the agent should continue based on basic checks only.

        The tool lifecycle logic will be handled in _should_continue_after_tools.
        
        Args:
            state: The current agent state containing messages.

        Returns:
            Literal["end", "continue"]: Decision based on tool calls presence and safety checks.
        """
        messages = state.messages
        if not messages:
            return "end"
            
        last_message = messages[-1]
        
        # Check 1: No tool calls - normal termination
        if not last_message.tool_calls:
            return "end"
        
        # Check 2: Iteration limit reached (safety check)
        current_iterations = getattr(state, 'iteration_count', 0)
        max_iterations = getattr(state, 'max_iterations', settings.MAX_GRAPH_ITERATIONS)
        
        if current_iterations >= max_iterations:
            logger.warning(
                "graph_iteration_limit_reached",
                session_id=state.session_id,
                iteration_count=current_iterations,
                max_iterations=max_iterations
            )
            return "end"
        
        # If tool calls exist and we haven't hit limits, continue to tool execution
        return "continue"

    def _should_continue_after_tools(self, state: GraphState) -> Literal["end", "continue"]:
        """Determine if the agent should continue after tool execution based on tool lifecycle.

        Args:
            state: The current agent state containing tool results.

        Returns:
            Literal["end", "continue"]: Decision based on tool lifecycle status.
        """
        # Check the result of the last tool execution
        last_tool_result = getattr(state, 'last_tool_result', None)
        
        if last_tool_result:
            if last_tool_result.status == "complete":
                logger.info(
                    "tool_lifecycle_complete",
                    session_id=state.session_id,
                    next_action=last_tool_result.next_action
                )
                return "end"  # Tool is done, let LLM respond to user
            elif last_tool_result.status in ["retry", "partial"]:
                return "continue"  # Tool needs more work
            elif last_tool_result.status == "error":
                return "continue"  # Allow retry for errors
        
        # Default: end and respond (safety fallback)
        return "end"

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
                graph_builder.add_conditional_edges(
                    "tool_call",
                    self._should_continue_after_tools,
                    {"continue": "chat", "end": "chat"},
                )
                graph_builder.set_entry_point("chat")
                graph_builder.set_finish_point("chat")

                # Get connection pool (may be None in production if DB unavailable)
                connection_pool = await self._get_connection_pool()
                if connection_pool:
                    checkpointer = AsyncPostgresSaver(connection_pool)
                    try:
                        await checkpointer.setup()
                    except Exception as setup_error:
                        # Handle duplicate column error gracefully
                        if "already exists" in str(setup_error):
                            logger.warning(
                                "checkpoint_setup_skipped_column_exists",
                                error=str(setup_error),
                                message="Checkpoint tables already set up, continuing...",
                            )
                        else:
                            # Re-raise if it's a different error
                            raise setup_error
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

        # Get subject context for the user if available
        subject_context = {}
        if user_id:
            try:
                from app.services.subject_service import subject_service

                current_subject = await subject_service.get_user_current_subject(user_id)
                if current_subject:
                    subject_context = {
                        "current_subject": current_subject["name"],
                        "subject_id": current_subject["id"],
                        "book_code": current_subject.get("book_code"),
                        "description": current_subject.get("description"),
                    }
                    logger.debug("subject_context_added", user_id=user_id, subject=current_subject["name"])
            except Exception as e:
                logger.warning("failed_to_get_subject_context", user_id=user_id, error=str(e))

        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": [CallbackHandler()],
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": False,
                "subject_context": subject_context,
            },
        }
        try:
            # Try to get message count from Redis cache first (performance optimization)
            from app.services.redis import redis_service
            from app.core.cache import ConversationCache

            async def fetch_message_count():
                # Use native async query for better performance
                try:
                    # Set timeout for database queries to prevent hanging
                    import asyncio

                    # Use the new async method instead of sync_to_async
                    return await asyncio.wait_for(
                        self.get_message_count_async(session_id),
                        timeout=3.0,  # 3 second timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning("db_message_count_timeout", session_id=session_id)
                    # Return 0 for new conversations to avoid blocking
                    return 0
                except Exception as e:
                    logger.error("db_message_count_failed", session_id=session_id, error=str(e))
                    return 0

            # Get message count from cache or database with faster cache TTL
            messages_before_count = await ConversationCache.get_or_set_message_count(
                session_id,
                fetch_message_count,
                ttl=600,  # Cache for 10 minutes (longer cache)
            )

            # Get current state to preserve loop protection fields
            current_state = None
            try:
                current_state = await sync_to_async(self._graph.get_state)(
                    config={"configurable": {"thread_id": session_id}}
                )
            except Exception as e:
                logger.warning("failed_to_get_current_state", session_id=session_id, error=str(e))

            # Invoke the graph with new messages and subject context, preserving state
            graph_input = {
                "messages": dump_messages(messages),
                "session_id": session_id,
                "metadata": {
                    **subject_context,
                    "user_id": user_id,  # Ensure user_id is available in state
                },
                # Preserve tool lifecycle fields from existing state
                "iteration_count": current_state.values.get("iteration_count", 0) if current_state and current_state.values else 0,
                "last_tool_result": current_state.values.get("last_tool_result") if current_state and current_state.values else None,
                "max_iterations": current_state.values.get("max_iterations", settings.MAX_GRAPH_ITERATIONS) if current_state and current_state.values else settings.MAX_GRAPH_ITERATIONS,
            }
            response = await self._graph.ainvoke(graph_input, config)

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
            seen_tool_calls = False
            tool_execution_complete = False
            
            async for token, _metadata in self._graph.astream(
                {
                    "messages": dump_messages(messages),
                    "session_id": session_id,
                    "metadata": {"user_id": user_id},  # Include user_id for tool calls
                },
                config,
                stream_mode="messages",
            ):
                try:
                    # Track if we've seen tool calls (indicating RAG usage)
                    if hasattr(token, 'tool_calls') and token.tool_calls:
                        seen_tool_calls = True
                        continue  # Skip tool call messages
                    
                    # Skip tool response messages
                    if hasattr(token, 'type') and token.type == 'tool':
                        tool_execution_complete = True
                        continue
                    
                    # Only yield AI responses
                    if hasattr(token, 'type') and token.type == 'ai' and hasattr(token, 'content') and token.content:
                        # If we've seen tool calls, only yield the response after tools are complete
                        if seen_tool_calls and not tool_execution_complete:
                            continue  # Skip intermediate AI messages before tool execution
                        yield token.content
                    elif hasattr(token, 'content') and token.content:
                        # Handle messages without explicit type, but exclude tool-related ones
                        if not (hasattr(token, 'tool_calls') and token.tool_calls):
                            # Apply same filtering logic for non-typed messages
                            if seen_tool_calls and not tool_execution_complete:
                                continue
                            yield token.content
                            
                except Exception as token_error:
                    logger.error("Error processing token", error=str(token_error), session_id=session_id)
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

        # Use async timeout to prevent hanging
        try:
            state: StateSnapshot = await asyncio.wait_for(
                sync_to_async(self._graph.get_state)(config={"configurable": {"thread_id": session_id}}),
                timeout=5.0,  # 5 second timeout for history retrieval
            )
        except asyncio.TimeoutError:
            logger.warning("chat_history_timeout", session_id=session_id)
            return []
        except Exception as e:
            logger.error("chat_history_failed", session_id=session_id, error=str(e))
            return []

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
