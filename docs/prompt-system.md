# Modular Prompt System

This document shows how to use the clean, modular prompt utilities across your chatbot.

## Quick Import

```python
# Import the core functions you need
from app.utils.prompt_utils import load_prompts, get_prompt_template, format_prompt

# Or import from utils
from app.utils import load_prompts, get_prompt_template, format_prompt
```

## Core Functions

### 1. `load_prompts(filename)` - Load YAML files
```python
prompts = load_prompts('rag_prompts.yaml')
```

### 2. `get_prompt_template(filename, key, language)` - Get specific templates
```python
template = get_prompt_template('rag_prompts.yaml', 'rag_prompts', 'en')
```

### 3. `format_prompt(template, **kwargs)` - Format with variables
```python
result = format_prompt(template, query="What is math?", context="Math is...")
```

## Usage Examples

### 1. RAG Prompts (Current implementation)
```python
from app.utils import get_prompt_template, format_prompt

# Get template and format it
template = get_prompt_template('rag_prompts.yaml', 'rag_prompts', language)
formatted_prompt = format_prompt(template, query=query, context=context)
```

### 2. Any Other Prompt Type
```python
from app.utils import get_prompt_template, format_prompt

# For chat prompts
template = get_prompt_template('chat_prompts.yaml', 'chat_prompts', 'ms')
prompt = format_prompt(template, message=message, history=history)

# For system prompts  
template = get_prompt_template('system_prompts.yaml', 'welcome_message', 'zh')
prompt = format_prompt(template, user_name=name, subject=subject)
```

### 3. Direct YAML Loading
```python
from app.utils import load_prompts

# Load any prompt file and work with it directly
prompts = load_prompts('rag_prompts.yaml')
en_template = prompts['rag_prompts']['en']
```

## Creating New Prompt Types

Just create new YAML files and use the same three functions:

**chat_prompts.yaml:**
```yaml
chat_prompts:
  en: |
    You are a helpful study assistant. 
    Previous conversation: {history}
    User message: {message}
    Please respond helpfully:
  
  ms: |
    Anda adalah pembantu belajar yang membantu.
    Perbualan sebelumnya: {history}
    Mesej pengguna: {message}
    Sila berikan respons yang membantu:
```

**Usage:**
```python
from app.utils import get_prompt_template, format_prompt

template = get_prompt_template('chat_prompts.yaml', 'chat_prompts', 'ms')
response = format_prompt(template, message="Help me", history="Previous chat...")
```

## Benefits

1. **Simple**: Only 3 core functions to remember
2. **Generic**: `format_prompt` works for all cases
3. **No special functions**: No need for `format_rag_prompt`, `format_chat_prompt`, etc.
4. **Consistent**: Same pattern everywhere
5. **Pure YAML**: All prompts in YAML files
6. **Cached**: Performance optimized
7. **Multilingual**: Easy language support
