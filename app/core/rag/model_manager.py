"""Simplified model loading and management for RAG system."""

import os
import asyncio
from typing import Optional, Dict, Any

from llama_index.core.llms.llm import LLM
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.embeddings import BaseEmbedding

from app.core.config import settings
from app.core.logging import logger


class ModelManager:
    """Simplified model manager without singleton pattern."""
    
    def __init__(self):
        """Initialize model manager with device detection."""
        self._device = self._detect_device()
        self._batch_size = self._get_batch_size()
        self._embedding_model: Optional[BaseEmbedding] = None
        self._llm_model: Optional[LLM] = None
        
        logger.debug(
            "model_manager_initialized",
            device=self._device,
            batch_size=self._batch_size,
            embedding_model=settings.HF_EMBED,
            llm_model=settings.GEMINI_MODEL,
        )
    
    def _detect_device(self) -> str:
        """Detect available compute device."""
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                logger.info("gpu_detected", device_count=torch.cuda.device_count())
            else:
                device = "cpu"
                logger.info("using_cpu", reason="CUDA not available")
            return device
        except ImportError:
            logger.warning("torch_not_available", fallback="cpu")
            return "cpu"
    
    def _get_batch_size(self) -> int:
        """Get optimal batch size based on device."""
        return 4 if self._device == "cuda" else 2
    
    def get_embedding_model(self) -> BaseEmbedding:
        """Get cached embedding model instance.
        
        Returns:
            BaseEmbedding: Configured Qwen embedding model
        """
        if self._embedding_model is None:
            try:
                # Set tokenizers parallelism to avoid warnings
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                
                # Initialize HuggingFace embedding model
                self._embedding_model = HuggingFaceEmbedding(
                    model_name=settings.HF_EMBED,
                    device=self._device,
                    embed_batch_size=self._batch_size,
                    normalize=True,  # Normalize embeddings for better similarity search
                )
                
                logger.info(
                    "embedding_model_loaded",
                    model=settings.HF_EMBED,
                    device=self._device,
                    batch_size=self._batch_size,
                    dimensions=768,  # Qwen embedding dimensions
                )
                
            except Exception as e:
                logger.error("embedding_model_load_failed", error=str(e))
                raise RuntimeError(f"Failed to load embedding model: {e}") from e
        
        return self._embedding_model
    
    def get_llm_model(self) -> LLM:
        """Get cached LLM model instance.
        
        Returns:
            LLM: Configured Gemini LLM model
        """
        if self._llm_model is None:
            try:
                if not settings.GEMINI_KEY:
                    raise ValueError("GEMINI_KEY not configured")
                
                # Initialize Gemini LLM
                self._llm_model = GoogleGenAI(
                    model=settings.GEMINI_MODEL,
                    api_key=settings.GEMINI_KEY,
                    temperature=settings.DEFAULT_LLM_TEMPERATURE,
                    max_tokens=settings.MAX_TOKENS,
                )
                
                logger.info(
                    "llm_model_loaded", 
                    model=settings.GEMINI_MODEL,
                    temperature=settings.DEFAULT_LLM_TEMPERATURE,
                    max_tokens=settings.MAX_TOKENS,
                    context_window="32K",
                )
                
            except Exception as e:
                logger.error("llm_model_load_failed", error=str(e))
                raise RuntimeError(f"Failed to load LLM model: {e}") from e
        
        return self._llm_model
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models.
        
        Returns:
            Dict[str, Any]: Model information including dimensions, device, etc.
        """
        return {
            "embedding": {
                "model": settings.HF_EMBED,
                "dimensions": 768,
                "device": self._device,
                "batch_size": self._batch_size,
            },
            "llm": {
                "model": settings.GEMINI_MODEL,
                "temperature": settings.DEFAULT_LLM_TEMPERATURE,
                "max_tokens": settings.MAX_TOKENS,
                "context_window": "32K",
            },
            "device": self._device,
        }
    
    async def test_models(self) -> Dict[str, bool]:
        """Test if models can be loaded and used.
        
        Returns:
            Dict[str, bool]: Test results for each model
        """
        results = {"embedding": False, "llm": False}
        
        # Test embedding model
        try:
            embedding_model = self.get_embedding_model()
            # Test with a simple text
            test_embedding = await asyncio.to_thread(
                embedding_model.get_text_embedding, "test"
            )
            results["embedding"] = len(test_embedding) == 768
            logger.info("embedding_model_test_passed")
        except Exception as e:
            logger.error("embedding_model_test_failed", error=str(e))
        
        # Test LLM model  
        try:
            llm_model = self.get_llm_model()
            # Test with a simple prompt
            response = await llm_model.acomplete("Hello")
            results["llm"] = bool(response.text.strip())
            logger.info("llm_model_test_passed")
        except Exception as e:
            logger.error("llm_model_test_failed", error=str(e))
        
        return results


# Global model manager instance
_model_manager = None

def get_model_manager() -> ModelManager:
    """Get global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager