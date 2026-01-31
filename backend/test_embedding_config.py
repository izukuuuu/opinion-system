
import sys
import os
from pathlib import Path
import asyncio

# Add backend directory to path so we can import src
sys.path.append(str(Path(__file__).parent))

try:
    from src.utils.rag.embedding import get_embedding_client_settings, get_sync_client, get_async_client
    from src.utils.rag.ragrouter.router_retrieve_data import EmbeddingGenerator as RouterEmbeddingGen
    # from src.utils.rag.tagrag.tag_retrieve_data import Retriever as TagRetriever # Needs dummy DB or mocks, skipping for now
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

def test_config():
    print("Testing config loading...")
    try:
        api_key, base_url, model, provider, dimension = get_embedding_client_settings()
        print(f"Provider: {provider}")
        print(f"Model: {model}")
        print(f"Base URL: {base_url}")
        print(f"Dimension: {dimension}")
        
        if not api_key:
            print("WARNING: API Key is missing!")
        else:
            print("API Key is set (masked): " + api_key[:8] + "...")
            
    except Exception as e:
        print(f"Config loading failed: {e}")

def test_clients():
    print("\nTesting client instantiation...")
    try:
        client, model, dim = get_sync_client()
        print(f"Sync client created. Model: {model}, Dim: {dim}")
    except Exception as e:
        print(f"Failed to create sync client: {e}")

    try:
        print("Testing Router Embedding Generator...")
        from src.utils.logging.logging import setup_logger
        logger = setup_logger("test_router", "test")
        
        gen = RouterEmbeddingGen(logger=logger)
        if gen.client:
            print(f"Router EmbeddingGenerator initialized with model: {gen.model_name}")
        else:
            print("Router EmbeddingGenerator failed to init client")
            
    except Exception as e:
        print(f"Failed to test RouterGen: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_config()
    test_clients()
