"""Configuration settings for the auto-marketing system."""

import os
from pathlib import Path
from typing import Any
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    vertexai_project: str = os.getenv("VERTEXAI_PROJECT", "")
    vertexai_location: str = os.getenv("VERTEXAI_LOCATION", "us-central1")

    # Model Configuration
    model_id: str = "claude-opus-4-5-20251101"
    effort_level: str = "high"  # high for maximum quality
    max_tokens: int = 16384

    # LiteLLM Model Configuration
    filter_model: str = "gemini/gemini-3-flash-preview"

    # Available models for UI selector (first one is default)
    available_generation_models: list[dict[str, Any]] = [
        {"id": "gemini/gemini-3-pro-preview", "name": "Gemini 3 Pro", "provider": "google"},
        {"id": "claude-opus-4-5-20251101", "name": "Claude Opus 4.5", "provider": "anthropic"},
    ]

    # Generation Parameters
    num_generators: int = 7  # 5-10 range
    variants_min: int = 2
    variants_max: int = 4

    # News Fetching
    news_hours_back: int = 48
    max_news_items: int = 5
    relevance_threshold: float = 0.6

    # Blog Fetching
    blog_days_back: int = 14  # 2 weeks for blog posts
    include_blog_feeds: bool = True  # Enable OPML blog feeds

    # Embedding Pre-filter
    embedding_enabled: bool = True
    embedding_model: str = "vertex_ai/text-embedding-005"  # Vertex AI embedding model
    embedding_top_k: int = 20  # Articles to pass to AI filter
    embedding_batch_size: int = 100  # Max embeddings per API call

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent
    src_dir: Path = project_root / "src"
    data_dir: Path = project_root / "data"
    output_dir: Path = project_root / "output" / "runs"
    config_dir: Path = src_dir / "config"

    # Config files
    personas_file: Path = config_dir / "personas.yaml"
    creativity_file: Path = config_dir / "creativity.yaml"

    class Config:
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()
