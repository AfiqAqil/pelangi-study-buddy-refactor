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
    if hasattr(msg, 'role'):
        return msg.role
    elif hasattr(msg, '__class__'):
        # LangChain message types
        class_name = msg.__class__.__name__.lower()
        if 'human' in class_name or 'user' in class_name:
            return 'user'
        elif 'ai' in class_name or 'assistant' in class_name:
            return 'assistant' 
        elif 'system' in class_name:
            return 'system'
        elif 'tool' in class_name:
            return 'tool'
    return 'unknown'


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
    """Prepare the messages for the LLM with context window trimming.

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
    
    return [system_message] + non_system_messages
