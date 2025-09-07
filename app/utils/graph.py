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
    """Trim messages to keep only the last N message pairs (user+assistant).

    Args:
        messages (list): The messages to trim (can be Message objects or LangChain BaseMessage objects).
        context_window_size (int): Number of message pairs to keep.

    Returns:
        list: The trimmed messages with preserved conversation flow.
    """
    if context_window_size <= 0 or len(messages) == 0:
        return messages

    # Filter out system messages for counting and processing
    non_system_messages = [msg for msg in messages if get_message_role(msg) not in ["system", "tool"]]

    # If we have fewer messages than the window size, return all
    max_messages = context_window_size * 2  # context_window_size pairs = context_window_size * 2 messages

    if len(non_system_messages) <= max_messages:
        return messages

    # Take the last N message pairs, maintaining user->assistant flow
    # Start from the end and work backwards to maintain proper pairing
    trimmed_non_system = non_system_messages[-max_messages:]

    # Reconstruct with any system messages preserved
    system_messages = [msg for msg in messages if get_message_role(msg) in ["system", "tool"]]

    return system_messages + trimmed_non_system


def prepare_messages(messages: list, llm: BaseChatModel, system_prompt: str) -> list:
    """Prepare the messages for the LLM with context window trimming and sequence validation.

    Args:
        messages (list): The messages to prepare (can be Message objects or LangChain BaseMessage objects).
        llm (BaseChatModel): The LLM to use.
        system_prompt (str): The system prompt to use.

    Returns:
        list: The prepared messages (returns Message objects when possible).
    """
    # Apply context window trimming first
    windowed_messages = trim_messages_by_count(messages, settings.CONTEXT_WINDOW_SIZE)

    # Add system prompt and return
    system_message = Message(role="system", content=system_prompt)

    # Remove any existing system messages and add our system prompt at the beginning
    non_system_messages = [msg for msg in windowed_messages if get_message_role(msg) != "system"]
    
    # Validate and fix message sequence for LLM compatibility (especially Gemini)
    cleaned_messages = _validate_message_sequence(non_system_messages)

    return [system_message] + cleaned_messages


def _validate_message_sequence(messages: list) -> list:
    """Validate and fix message sequence to ensure LLM compatibility.
    
    Ensures that:
    1. Assistant messages with tool_calls are followed by tool messages
    2. Tool messages are followed by assistant messages
    3. No incomplete tool call sequences are sent to the LLM
    
    Args:
        messages (list): The messages to validate
        
    Returns:
        list: Cleaned message sequence safe for LLM processing
    """
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
            
            while (j < len(messages) and 
                   get_message_role(messages[j]) == "tool"):
                tool_msg = messages[j]
                if (hasattr(tool_msg, 'tool_call_id') and 
                    tool_msg.tool_call_id in tool_call_ids):
                    found_tool_responses.append(tool_msg)
                j += 1
            
            # If we found complete tool responses, include the sequence
            if len(found_tool_responses) == len(tool_call_ids):
                cleaned.append(current_msg)
                cleaned.extend(found_tool_responses)
                i = j
            else:
                # Incomplete tool call sequence - skip the assistant message with tool calls
                # This prevents sending invalid sequences to the LLM
                i += 1
        else:
            # Regular message (user, assistant without tools, etc.)
            cleaned.append(current_msg)
            i += 1
    
    return cleaned
