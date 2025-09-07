"""LLM provider abstraction layer for better testability and flexibility."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from langchain_core.language_models.base import BaseLanguageModel
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import Environment, settings
from app.core.logging import logger
from app.core.langgraph.tools import tools


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, model: str, temperature: float, max_tokens: Optional[int] = None):
        """Initialize the LLM provider.
        
        Args:
            model: Model name/identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._llm: Optional[BaseLanguageModel] = None
    
    @abstractmethod
    def _create_llm(self) -> BaseLanguageModel:
        """Create the actual LLM instance.
        
        Returns:
            Configured LLM instance
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Get the model name for metrics and logging.
        
        Returns:
            Model name string
        """
        pass
    
    def get_llm(self) -> BaseLanguageModel:
        """Get the LLM instance, creating it if necessary.
        
        Returns:
            Configured LLM instance with tools bound
        """
        if self._llm is None:
            self._llm = self._create_llm()
            # Bind tools to the LLM
            self._llm = self._llm.bind_tools(tools)
            logger.info(
                "llm_provider_initialized",
                provider=self.__class__.__name__,
                model=self.get_model_name(),
                environment=settings.ENVIRONMENT.value
            )
        return self._llm
    
    def _get_environment_kwargs(self) -> Dict[str, Any]:
        """Get environment-specific configuration kwargs.
        
        Returns:
            Dictionary of environment-specific settings
        """
        kwargs = {}
        
        # Development - optimize for cost
        if settings.ENVIRONMENT == Environment.DEVELOPMENT:
            kwargs["top_p"] = 0.8
            
        # Production - optimize for quality
        elif settings.ENVIRONMENT == Environment.PRODUCTION:
            kwargs["top_p"] = 0.95
            kwargs["presence_penalty"] = 0.1
            kwargs["frequency_penalty"] = 0.1
            
        return kwargs


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation."""
    
    def __init__(self, model: str, api_key: str, temperature: float, max_tokens: Optional[int] = None):
        """Initialize OpenAI provider.
        
        Args:
            model: OpenAI model name (e.g., "gpt-4o", "gpt-3.5-turbo")
            api_key: OpenAI API key
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key
    
    def _create_llm(self) -> BaseLanguageModel:
        """Create OpenAI ChatOpenAI instance.
        
        Returns:
            Configured ChatOpenAI instance
        """
        kwargs = {
            "model": self.model,
            "temperature": self.temperature,
            "api_key": self.api_key,
            **self._get_environment_kwargs(),
        }
        
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
            
        return ChatOpenAI(**kwargs)
    
    def get_model_name(self) -> str:
        """Get model name from OpenAI provider.
        
        Returns:
            Model name string
        """
        return self.model


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider implementation."""
    
    def __init__(self, model: str, api_key: str, temperature: float, max_tokens: Optional[int] = None):
        """Initialize Gemini provider.
        
        Args:
            model: Gemini model name (e.g., "gemini-1.5-flash", "gemini-1.5-pro")
            api_key: Google API key
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
        """
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key
    
    def _create_llm(self) -> BaseLanguageModel:
        """Create Gemini ChatGoogleGenerativeAI instance.
        
        Returns:
            Configured ChatGoogleGenerativeAI instance
        """
        kwargs = {
            "model": self.model,
            "temperature": self.temperature,
            "google_api_key": self.api_key,
            **self._get_environment_kwargs(),
        }
        
        if self.max_tokens:
            kwargs["max_output_tokens"] = self.max_tokens
            
        return ChatGoogleGenerativeAI(**kwargs)
    
    def get_model_name(self) -> str:
        """Get model name from Gemini provider.
        
        Returns:
            Model name string
        """
        return self.model


def create_llm_provider() -> LLMProvider:
    """Factory function to create appropriate LLM provider based on configuration.
    
    Returns:
        Configured LLM provider instance
        
    Raises:
        ValueError: If provider type is not supported
    """
    provider_type = settings.LLM_PROVIDER.lower()
    
    if provider_type == "openai":
        return OpenAIProvider(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            temperature=settings.DEFAULT_LLM_TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
        )
    elif provider_type == "gemini":
        return GeminiProvider(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            temperature=settings.DEFAULT_LLM_TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_type}")