"""Configuration management using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Provider
    gemini_api_key: str | None = Field(
        None, description="Gemini API key from Google AI Studio"
    )
    openai_api_key: str | None = Field(None, description="OpenAI API key")

    # App Config
    environment: str = Field(
        default="local", description="Environment: local, dev, staging, production"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    server_ip: str = Field(default="0.0.0.0", description="Server bind IP")
    server_port: int = Field(default=8000, description="Server port")

    # Database
    database_url: str = Field(
        default="sqlite:///./data/extraction.db", description="Database connection URL"
    )

    # Optional: GCP
    google_cloud_project: str | None = Field(default=None, description="GCP project ID")
    gcs_bucket_name: str | None = Field(
        default=None, description="GCS bucket for uploads"
    )

    # Processing
    max_file_size_mb: int = Field(
        default=50, description="Maximum file upload size in MB"
    )
    allowed_extensions: list[str] = Field(
        default=[".pdf", ".json"], description="Allowed file extensions"
    )

    # Storage Configuration
    storage_backend: str = Field(
        default="local", description="Storage backend: local, minio, s3"
    )

    # MinIO Configuration
    minio_endpoint: str = Field(
        default="localhost:9000", description="MinIO server endpoint"
    )
    minio_access_key: str = Field(default="minioadmin", description="MinIO access key")
    minio_secret_key: str = Field(default="minioadmin", description="MinIO secret key")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    minio_bucket_name: str = Field(
        default="documents", description="Default MinIO bucket name"
    )

    # AWS S3 Configuration (for production)
    aws_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    aws_secret_access_key: str | None = Field(
        default=None, description="AWS secret access key"
    )
    aws_s3_bucket: str | None = Field(default=None, description="S3 bucket name")
    aws_region: str = Field(default="us-east-1", description="AWS region")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
settings = Settings()
