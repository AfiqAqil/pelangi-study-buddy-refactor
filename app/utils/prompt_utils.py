"""Utility functions for loading and formatting prompts from YAML files."""

import os
import yaml
from typing import Dict, Any
from functools import lru_cache


@lru_cache(maxsize=128)
def load_prompt_file(file_path: str) -> Dict[str, Any]:
    """
    Load and cache a YAML prompt file.
    
    Args:
        file_path: Absolute path to the YAML file
        
    Returns:
        Dict containing the loaded YAML data
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_prompt_file_path(filename: str) -> str:
    """
    Get the full path to a prompt file in the prompts directory.
    
    Args:
        filename: Name of the YAML file (e.g., 'rag_prompts.yaml')
        
    Returns:
        Absolute path to the prompt file
    """
    prompts_dir = os.path.join(
        os.path.dirname(__file__), 
        "..", "core", "prompts"
    )
    return os.path.abspath(os.path.join(prompts_dir, filename))


def load_prompts(filename: str) -> Dict[str, Any]:
    """
    Load prompts from a YAML file in the prompts directory.
    
    Args:
        filename: Name of the YAML file (e.g., 'rag_prompts.yaml')
        
    Returns:
        Dict containing the loaded prompts
    """
    file_path = get_prompt_file_path(filename)
    return load_prompt_file(file_path)


def get_prompt_template(
    filename: str, 
    prompt_key: str, 
    language: str = "en"
) -> str:
    """
    Get a specific prompt template from a YAML file.
    
    Args:
        filename: Name of the YAML file (e.g., 'rag_prompts.yaml')
        prompt_key: Key path to the prompt (e.g., 'rag_prompts')
        language: Language code (default: 'en')
        
    Returns:
        The prompt template string
    """
    prompts = load_prompts(filename)
    
    # Navigate to the prompt using the key
    prompt_section = prompts[prompt_key]
    
    # Get language-specific prompt or fallback to English
    if isinstance(prompt_section, dict):
        template = prompt_section.get(language, prompt_section.get("en", ""))
    else:
        template = prompt_section
    
    return template.strip() if template else ""


def format_prompt(template: str, **kwargs) -> str:
    """
    Format a prompt template with provided variables.
    
    Args:
        template: The prompt template string
        **kwargs: Variables to substitute in the template
        
    Returns:
        Formatted prompt string
    """
    return template.format(**kwargs)
