"""This file contains the graph utilities for the application."""

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings
from app.schemas import Message


def get_message_role(msg) -> str:
    """Get role from either Message object or LangChain BaseMessage object.

    Args:
        msg: Message object (either our Message schema or LangChain BaseMessage)

    Returns:
        str: The role of the message (user, assistant, system, tool, or unknown)
    """
    if hasattr(msg, "role"):
        return msg.role
    elif hasattr(msg, "__class__"):
        # LangChain message types
        class_name = msg.__class__.__name__.lower()
        if "human" in class_name or "user" in class_name:
            return "user"
        elif "ai" in class_name or "assistant" in class_name:
            return "assistant"
        elif "system" in class_name:
            return "system"
        elif "tool" in class_name:
            return "tool"
    return "unknown"


def dump_messages(messages: list[Message]) -> list[dict]:
    """Dump the messages to a list of dictionaries.

    Args:
        messages (list[Message]): The messages to dump.

    Returns:
        list[dict]: The dumped messages.
    """
    return [message.model_dump() for message in messages]


def trim_messages_by_count(messages: list, context_window_size: int) -> list:
    """Trim messages to keep only the last N message pairs while preserving tool call sequences.

    Args:
        messages (list): The messages to trim (can be Message objects or LangChain BaseMessage objects).
        context_window_size (int): Number of message pairs to keep.

    Returns:
        list: The trimmed messages with preserved conversation flow and intact tool sequences.
    """
    from app.core.logging import logger
    
    if context_window_size <= 0 or len(messages) == 0:
        return messages

    # Separate system messages from conversation messages
    system_messages = [msg for msg in messages if get_message_role(msg) == "system"]
    conversation_messages = [msg for msg in messages if get_message_role(msg) != "system"]
    
    # If we have fewer conversation messages than the window allows, return all
    max_messages = context_window_size * 2  # context_window_size pairs = context_window_size * 2 messages

    if len(conversation_messages) <= max_messages:
        logger.debug(
            "trim_messages_no_trimming_needed",
            total_messages=len(messages),
            conversation_messages=len(conversation_messages),
            max_allowed=max_messages
        )
        return messages

    # Group messages into sequences to preserve tool call chains
    message_groups = []
    current_group = []
    
    for msg in conversation_messages:
        role = get_message_role(msg)
        current_group.append(msg)
        
        # End group when we hit a user message (start of new interaction)
        # or when we have a complete tool call sequence
        if role == "user" and len(current_group) > 1:
            # Save previous group and start new one with this user message
            message_groups.append(current_group[:-1])
            current_group = [msg]
        elif (role == "assistant" and 
              not (hasattr(msg, 'tool_calls') and msg.tool_calls)):
            # Assistant message without tool calls - complete group
            message_groups.append(current_group)
            current_group = []
        elif role == "tool":
            # Tool message might complete a sequence, check if more tool messages follow
            # We'll handle this in the next iteration
            continue
    
    # Add any remaining messages as the final group
    if current_group:
        message_groups.append(current_group)
    
    # Calculate how many complete groups we can fit in the context window
    total_messages_in_groups = 0
    groups_to_keep = []
    
    # Start from the end and work backwards
    for group in reversed(message_groups):
        if total_messages_in_groups + len(group) <= max_messages:
            groups_to_keep.append(group)
            total_messages_in_groups += len(group)
        else:
            break
    
    # If we can't fit any complete groups, take the last max_messages
    if not groups_to_keep:
        logger.debug(
            "trim_messages_fallback_to_simple_trim",
            max_messages=max_messages
        )
        trimmed_conversation = conversation_messages[-max_messages:]
    else:
        # Reverse to restore chronological order and flatten groups
        groups_to_keep.reverse()
        trimmed_conversation = [msg for group in groups_to_keep for msg in group]
    
    logger.debug(
        "trim_messages_completed",
        original_count=len(messages),
        trimmed_count=len(system_messages) + len(trimmed_conversation),
        groups_kept=len(groups_to_keep) if groups_to_keep else 0
    )

    return system_messages + trimmed_conversation


def prepare_messages(messages: list, llm: BaseChatModel, system_prompt: str) -> list:
    """Prepare the messages for the LLM with context window trimming and sequence validation.

    Args:
        messages (list): The messages to prepare (can be Message objects or LangChain BaseMessage objects).
        llm (BaseChatModel): The LLM to use.
        system_prompt (str): The system prompt to use.

    Returns:
        list: The prepared messages (returns Message objects when possible).
    """
    from app.core.logging import logger
    
    logger.debug(
        "prepare_messages_started",
        input_message_count=len(messages),
        context_window_size=settings.CONTEXT_WINDOW_SIZE
    )
    
    # Apply context window trimming first
    windowed_messages = trim_messages_by_count(messages, settings.CONTEXT_WINDOW_SIZE)
    
    logger.debug(
        "prepare_messages_windowed",
        windowed_message_count=len(windowed_messages),
        trimmed_count=len(messages) - len(windowed_messages)
    )

    # Add system prompt and return
    system_message = Message(role="system", content=system_prompt)

    # Remove any existing system messages and add our system prompt at the beginning
    non_system_messages = [msg for msg in windowed_messages if get_message_role(msg) != "system"]
    
    logger.debug(
        "prepare_messages_pre_validation",
        non_system_message_count=len(non_system_messages),
        roles_breakdown={
            role: len([msg for msg in non_system_messages if get_message_role(msg) == role])
            for role in ["user", "assistant", "tool"]
        }
    )
    
    # Validate and fix message sequence for LLM compatibility (especially Gemini)
    cleaned_messages = _validate_message_sequence(non_system_messages)
    
    final_messages = [system_message] + cleaned_messages
    
    logger.debug(
        "prepare_messages_completed",
        final_message_count=len(final_messages),
        final_roles_breakdown={
            role: len([msg for msg in final_messages if get_message_role(msg) == role])
            for role in ["system", "user", "assistant", "tool"]
        }
    )

    return final_messages


def _validate_message_sequence(messages: list) -> list:
    """Validate and fix message sequence to ensure LLM compatibility.
    
    Ensures that:
    1. Assistant messages with tool_calls are followed by tool messages
    2. Tool messages are followed by assistant messages
    3. Missing tool responses are handled gracefully with placeholder responses
    
    Args:
        messages (list): The messages to validate
        
    Returns:
        list: Cleaned message sequence safe for LLM processing
    """
    from app.core.logging import logger
    
    if not messages:
        return messages
        
    cleaned = []
    i = 0
    
    while i < len(messages):
        current_msg = messages[i]
        current_role = get_message_role(current_msg)
        
        # If this is an assistant message with tool calls
        if (current_role == "assistant" and 
            hasattr(current_msg, 'tool_calls') and 
            current_msg.tool_calls):
            
            # Look ahead to see if there are corresponding tool responses
            tool_call_ids = [tc.get('id') if isinstance(tc, dict) else tc['id'] 
                           for tc in current_msg.tool_calls]
            
            # Find all consecutive tool messages that respond to these calls
            j = i + 1
            found_tool_responses = []
            found_tool_ids = set()
            
            while (j < len(messages) and 
                   get_message_role(messages[j]) == "tool"):
                tool_msg = messages[j]
                tool_call_id = getattr(tool_msg, 'tool_call_id', None)
                if tool_call_id and tool_call_id in tool_call_ids:
                    found_tool_responses.append(tool_msg)
                    found_tool_ids.add(tool_call_id)
                j += 1
            
            # Add the assistant message
            cleaned.append(current_msg)
            
            # Add found tool responses
            cleaned.extend(found_tool_responses)
            
            # Create placeholder responses for missing tool calls
            missing_tool_ids = set(tool_call_ids) - found_tool_ids
            if missing_tool_ids:
                logger.debug(
                    "creating_placeholder_tool_responses",
                    missing_count=len(missing_tool_ids),
                    missing_ids=list(missing_tool_ids)
                )
                
                for tool_call_id in missing_tool_ids:
                    # Find the corresponding tool call to get the name
                    tool_name = "unknown_tool"
                    for tc in current_msg.tool_calls:
                        if tc.get('id') == tool_call_id:
                            tool_name = tc.get('function', {}).get('name', 'unknown_tool')
                            break
                    
                    # Create placeholder tool response
                    placeholder_response = Message(
                        role="tool",
                        content=f"Tool response not available (tool: {tool_name})",
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                    cleaned.append(placeholder_response)
            
            i = j
        else:
            # Regular message (user, assistant without tools, etc.)
            cleaned.append(current_msg)
            i += 1
    
    logger.debug(
        "message_sequence_validation_complete",
        original_count=len(messages),
        cleaned_count=len(cleaned)
    )
    
    return cleaned
