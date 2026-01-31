
"""
Unified embedding utility for RAG systems.
Handles configuration loading and client initialization for both OpenAI and Qwen (via compatible interface).
"""
import os
from typing import Optional, Tuple, List, Union
from openai import OpenAI, AsyncOpenAI
from ..setting.settings import settings
from ..setting.env_loader import get_api_key, get_openai_api_key, get_openai_base_url
from ..logging.logging import log_error, log_success

def get_embedding_config() -> dict:
    """
    Get the current embedding configuration from global settings.
    """
    llm_config = settings.get_llm_config()
    return llm_config.get('embedding_llm', {})

def get_embedding_client_settings() -> Tuple[str, str, str, str, int]:
    """
    Resolve embedding settings based on provider.
    
    Returns:
        Tuple[api_key, base_url, model, provider, dimension]
    """
    config = get_embedding_config()
    provider = config.get('provider', 'qwen')
    model = config.get('model', '')
    dimension = int(config.get('dimension', 1024))
    
    if provider == 'openai':
        api_key = get_openai_api_key()
        base_url = config.get('base_url') or get_openai_base_url() or "https://api.openai.com/v1"
        if not model:
            model = "text-embedding-3-small"
    else:
        # Default to qwen/dashscope
        api_key = get_api_key()
        # Use compatible mode endpoint for Qwen by default if using OpenAI SDK
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if not model:
            model = "text-embedding-v4"
            
    return api_key, base_url, model, provider, dimension

def get_sync_client() -> Tuple[OpenAI, str, int]:
    """
    Get a synchronous OpenAI client configured for embeddings.
    
    Returns:
        Tuple[OpenAI, model_name, dimension]
    """
    api_key, base_url, model, _, dimension = get_embedding_client_settings()
    
    if not api_key:
        raise ValueError("API Key not found for embedding provider")
        
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model, dimension

def get_async_client() -> Tuple[AsyncOpenAI, str, int]:
    """
    Get an asynchronous OpenAI client configured for embeddings.
    
    Returns:
        Tuple[AsyncOpenAI, model_name, dimension]
    """
    api_key, base_url, model, _, dimension = get_embedding_client_settings()
    
    if not api_key:
        raise ValueError("API Key not found for embedding provider")
        
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return client, model, dimension

def generate_embedding_sync(client: OpenAI, text: str, model: str) -> List[float]:
    """
    Generate embedding synchronously.
    """
    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        # Return zeros or re-raise? 
        # For now re-raise so caller can handle or log
        raise e

async def generate_embedding_async(client: AsyncOpenAI, text: str, model: str) -> List[float]:
    """
    Generate embedding asynchronously.
    """
    text = text.replace("\n", " ")
    try:
        response = await client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        raise e
