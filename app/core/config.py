"""
Configuration management using Pydantic BaseSettings
"""

from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "AI Content Automation Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # API Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 5000
    
    # CORS - allow all origins (development; tighten in production)
    CORS_ORIGINS: List[str] = ["*"]
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/content_db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Translation services
    libretranslate_url: Optional[str] = None
    huggingface_api_url: str = "https://api-inference.huggingface.co"
    huggingface_api_token: Optional[str] = None
    translation_cache_ttl_s: int = 86400
    translation_timeout_libre_s: float = 15.0
    translation_timeout_hf_s: float = 30.0
    
    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    
    # Vector Database
    vector_db_type: str = "chroma"  # 'chroma' or 'qdrant'
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    qdrant_url: str = "http://localhost:6333"
    
    # Ollama (for local LLM) — Replit-internal server runs on 8008
    ollama_base_url: str = "http://127.0.0.1:8008"
    ollama_model: str = "mistral"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    # External API Keys
    google_trends_enabled: bool = True
    youtube_api_key: Optional[str] = None
    x_api_key: Optional[str] = None
    instagram_api_key: Optional[str] = None
    tiktok_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Create global settings instance
settings = Settings()
