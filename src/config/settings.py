"""Configuration settings for the auto-marketing system."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Model Configuration
    model_id: str = "claude-opus-4-5-20251101"
    effort_level: str = "high"  # high for maximum quality
    max_tokens: int = 16384

    # Generation Parameters
    num_generators: int = 7  # 5-10 range
    variants_min: int = 2
    variants_max: int = 4

    # News Fetching
    news_hours_back: int = 48
    max_news_items: int = 5
    relevance_threshold: float = 0.6

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
