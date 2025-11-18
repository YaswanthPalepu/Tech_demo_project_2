"""
Ollama Embedding Client

Provides embedding generation using Ollama's local API.
Compatible with the codebase indexer and semantic retriever.
"""

import requests
import os
from typing import List, Dict, Any
import time


class OllamaEmbeddingClient:
    """Client for generating embeddings using Ollama."""

    def __init__(
        self,
        host: str = None,
        model: str = None,
        vector_dim: int = None
    ):
        """
        Initialize Ollama embedding client.

        Args:
            host: Ollama host URL (defaults to OLLAMA_HOST env var)
            model: Embedding model name (defaults to OLLAMA_EMBED_MODEL env var)
            vector_dim: Vector dimension (defaults to VECTOR_DIM env var)
        """
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:latest")
        self.vector_dim = int(vector_dim or os.getenv("VECTOR_DIM", "1024"))

        # Ensure host doesn't end with slash
        self.host = self.host.rstrip('/')

        self.embeddings_url = f"{self.host}/api/embeddings"

    def create_embedding(
        self,
        input_text: str,
        model: str = None
    ) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            input_text: Text to embed
            model: Model to use (defaults to instance model)

        Returns:
            Embedding vector as list of floats
        """
        model = model or self.model

        payload = {
            "model": model,
            "prompt": input_text
        }

        try:
            response = requests.post(
                self.embeddings_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            embedding = data.get("embedding", [])

            if not embedding:
                raise ValueError("Empty embedding returned from Ollama")

            return embedding

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama embedding request failed: {e}")
        except (KeyError, ValueError) as e:
            raise RuntimeError(f"Invalid Ollama response format: {e}")

    def create_embeddings_batch(
        self,
        input_texts: List[str],
        model: str = None,
        max_retries: int = 3
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            input_texts: List of texts to embed
            model: Model to use (defaults to instance model)
            max_retries: Maximum retry attempts per text

        Returns:
            List of embedding vectors
        """
        embeddings = []

        for i, text in enumerate(input_texts):
            retry_count = 0
            while retry_count < max_retries:
                try:
                    embedding = self.create_embedding(text, model)
                    embeddings.append(embedding)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        # Fallback: return zero vector
                        print(f"  ⚠️  Failed to embed text {i+1}/{len(input_texts)} after {max_retries} retries: {e}")
                        embeddings.append([0.0] * self.vector_dim)
                        break
                    else:
                        # Wait before retry
                        time.sleep(2 ** retry_count)  # Exponential backoff

        return embeddings


class OllamaOpenAIAdapter:
    """
    Adapter to make Ollama client compatible with OpenAI client interface.

    This allows us to use Ollama embeddings with code written for OpenAI.
    """

    def __init__(
        self,
        host: str = None,
        model: str = None,
        vector_dim: int = None
    ):
        self.client = OllamaEmbeddingClient(host, model, vector_dim)
        self.embeddings = self  # For client.embeddings.create() pattern

    def create(
        self,
        model: str,
        input: List[str]
    ):
        """
        Create embeddings (OpenAI-compatible interface).

        Args:
            model: Model name (overrides instance model)
            input: List of texts to embed

        Returns:
            Response object compatible with OpenAI format
        """
        # Handle single string input
        if isinstance(input, str):
            input = [input]

        # Generate embeddings
        embeddings = self.client.create_embeddings_batch(input, model)

        # Return OpenAI-compatible response
        return OllamaEmbeddingResponse(embeddings)


class OllamaEmbeddingResponse:
    """Response object compatible with OpenAI embedding response format."""

    def __init__(self, embeddings: List[List[float]]):
        self.data = [
            OllamaEmbeddingData(i, embedding)
            for i, embedding in enumerate(embeddings)
        ]


class OllamaEmbeddingData:
    """Data object compatible with OpenAI embedding data format."""

    def __init__(self, index: int, embedding: List[float]):
        self.index = index
        self.embedding = embedding


def get_ollama_client() -> OllamaOpenAIAdapter:
    """
    Get Ollama client with OpenAI-compatible interface.

    Returns:
        OllamaOpenAIAdapter instance
    """
    return OllamaOpenAIAdapter()


def test_ollama_connection() -> bool:
    """
    Test connection to Ollama server.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        client = get_ollama_client()

        # Try a simple embedding
        test_text = "Hello, world!"
        response = client.create(
            model=os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:latest"),
            input=[test_text]
        )

        if response.data and len(response.data) > 0:
            print(f"✓ Ollama connection successful!")
            print(f"  Embedding dimension: {len(response.data[0].embedding)}")
            return True
        else:
            print("✗ Ollama returned empty response")
            return False

    except Exception as e:
        print(f"✗ Ollama connection failed: {e}")
        return False


if __name__ == "__main__":
    # Test the client
    print("Testing Ollama embedding client...")
    print(f"Host: {os.getenv('OLLAMA_HOST', 'http://localhost:11434')}")
    print(f"Model: {os.getenv('OLLAMA_EMBED_MODEL', 'qwen3-embedding:latest')}")
    print()

    success = test_ollama_connection()

    if success:
        print("\n✅ Client is ready to use!")
    else:
        print("\n❌ Client setup failed. Check your Ollama configuration.")
