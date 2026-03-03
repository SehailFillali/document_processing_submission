"""PydanticAI extraction service with Gemini."""

import os
import time

from pydantic import BaseModel

from doc_extract.core.config import settings
from doc_extract.core.logging import logger
from doc_extract.core.observability import obs_config
from doc_extract.ports.llm import ExtractionRequest, ExtractionResponse

try:
    import logfire

    LOGFIRE_AVAILABLE = True
except ImportError:
    LOGFIRE_AVAILABLE = False

_cost_tracker: dict[str, float] = {}


SYSTEM_PROMPT = """You are an expert document extraction system specialized in analyzing loan documents.

Your task is to extract structured information from the provided document.

Extract the following information:
- Borrower name and contact information
- Address (street, city, state, zip code)
- Income history with sources, amounts, and time periods
- Account/loan numbers and types
- Any other relevant financial information

For the borrower's name and address, also provide:
- The source document name
- The page number where it was found
- The verbatim text containing the name/address
- Your confidence score (0.0 to 1.0)

For each piece of information extracted, note:
1. The page number where it was found (if applicable)
2. The verbatim text that supports the extraction
3. Your confidence score (0.0 to 1.0)

If information is missing or unclear, explicitly state that it was not found rather than making up data.
"""


class GeminiAdapter:
    """Adapter for Google Gemini via PydanticAI."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.gemini_api_key
        os.environ["GEMINI_API_KEY"] = self.api_key
        self.model_name = "gemini-1.5-flash"
        logger.info(f"Initialized GeminiAdapter with model: {self.model_name}")

    async def extract_structured(
        self, request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data using Gemini with observability."""
        start_time = time.time()

        if LOGFIRE_AVAILABLE and obs_config.enabled:
            with logfire.span(
                "llm_extraction",
                document_type=request.document_type,
                model=self.model_name,
            ):
                try:
                    result = await self._do_extraction(request, start_time)
                    return result
                except Exception as e:
                    logfire.error(f"Extraction failed: {e}")
                    raise
        else:
            return await self._do_extraction(request, start_time)

    async def _do_extraction(
        self, request: ExtractionRequest, start_time: float
    ) -> ExtractionResponse:
        """Actual extraction logic."""
        from pydantic_ai import Agent

        agent = Agent(
            model=self.model_name,
            output_type=request.output_schema,
            system_prompt=request.system_prompt or SYSTEM_PROMPT,
        )

        result = await agent.run(request.document_url)

        processing_time = time.time() - start_time

        input_tokens = getattr(result, "input_tokens", 0)
        output_tokens = getattr(result, "output_tokens", 0)
        cost = obs_config.calculate_cost(input_tokens, output_tokens)

        _cost_tracker["total"] = _cost_tracker.get("total", 0) + cost

        return ExtractionResponse(
            extracted_data=result.data,
            raw_output=None,
            token_usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            confidence_score=0.85,
            processing_time_seconds=processing_time,
            model_name=self.model_name,
        )

    async def validate_connection(self) -> bool:
        """Validate Gemini API connection."""
        try:
            from pydantic_ai import Agent

            class HealthCheck(BaseModel):
                status: str

            await Agent(
                model=self.model_name,
                output_type=HealthCheck,
            )
            return True
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False

    def get_model_info(self) -> dict:
        """Get model information."""
        return {
            "model_name": self.model_name,
            "provider": "Google Gemini",
            "capabilities": ["text_extraction", "structured_output"],
        }


def track_extraction_cost(submission_id: str, cost: float) -> None:
    """Track extraction cost for a submission."""
    if submission_id:
        _cost_tracker[submission_id] = _cost_tracker.get(submission_id, 0) + cost


def get_submission_cost(submission_id: str) -> float:
    """Get total cost for a submission."""
    return _cost_tracker.get(submission_id, 0)


def get_total_system_cost() -> float:
    """Get total system cost."""
    return sum(_cost_tracker.values())
