"""LLM port - abstraction for AI model operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class ExtractionRequest:
    """Request for LLM extraction."""

    document_url: str
    document_type: str
    output_schema: type[BaseModel]
    system_prompt: str | None = None
    validation_rules: list | None = None
    document_content: bytes | None = None  # Raw file bytes for native PDF ingestion


@dataclass
class ExtractionResponse:
    """Response from LLM extraction."""

    extracted_data: BaseModel
    token_usage: dict
    confidence_score: float
    processing_time_seconds: float
    model_name: str
    raw_output: str | None = None


class LLMError(Exception):
    """Structured LLM error."""

    def __init__(
        self,
        message: str,
        error_type: str,
        recoverable: bool,
        retry_after_seconds: int | None = None,
    ):
        self.message = message
        self.error_type = error_type
        self.recoverable = recoverable
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class LLMPort(ABC):
    """Port for LLM operations.

    This abstracts away the specific LLM provider (Gemini, OpenAI, etc.)
    and provides a unified interface for document extraction.

    Implementations:
        - GeminiAdapter: Google Gemini via API key
        - OpenAIAdapter: OpenAI GPT models
        - VertexAIAdapter: Google Vertex AI (service account)
    """

    @abstractmethod
    async def extract_structured(
        self, request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data from a document.

        Args:
            request: Extraction request with document URL and schema

        Returns:
            ExtractionResponse with validated data

        Raises:
            LLMError: If extraction fails
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate that LLM service is accessible.

        Returns:
            True if connection is valid
        """
        pass

    @abstractmethod
    def get_model_info(self) -> dict:
        """Get information about the configured model.

        Returns:
            Dict with model name, version, capabilities
        """
        pass
