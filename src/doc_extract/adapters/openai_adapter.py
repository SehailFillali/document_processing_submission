"""OpenAI extraction service."""

import base64
import os
import time

from doc_extract.core.logging import logger
from doc_extract.ports.llm import ExtractionRequest, ExtractionResponse, LLMError

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

QUALITY RULES (MUST FOLLOW):
- If a field has a value, provide provenance for it whenever the schema supports provenance.
- Do not output null provenance for populated `name`, `address`, income entries, or account entries unless the document is genuinely unreadable.
- Populate `source_documents` with the actual source filename(s) used.
- `income_history` should contain actual income sources only (wages, salary, self-employment, bonuses).
- Do NOT treat taxes/withholdings/deductions (e.g., Medicare tax, Social Security tax, federal withholding) as income entries.
- If evidence is missing, return null/empty for that value rather than guessing.

For each extracted value, include:
1. Source page number
2. Verbatim supporting text
3. Confidence score (0.0 to 1.0)

If information is missing or unclear, explicitly state it was not found rather than inventing data.
"""


class OpenAIAdapter:
    """Adapter for OpenAI GPT models."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
        logger.info(f"Initialized OpenAIAdapter with model: {self.model_name}")

    async def extract_structured(
        self, request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data using OpenAI."""
        start_time = time.time()

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

            schema_json = request.output_schema.model_json_schema()

            # Build user message content
            if request.document_content:
                # Native PDF ingestion via Chat Completions file content block
                b64_data = base64.b64encode(request.document_content).decode()
                filename = (
                    request.document_url.split("/")[-1]
                    if "/" in request.document_url
                    else "document.pdf"
                )
                user_content = [
                    {
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": f"data:application/pdf;base64,{b64_data}",
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract all structured borrower data from this document.",
                    },
                ]
            else:
                # Fallback: send document_url as text (for testing / non-file inputs)
                user_content = (
                    f"Extract structured data from this document: "
                    f"{request.document_url}"
                )

            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": request.system_prompt or SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.output_schema.__name__,
                        "schema": schema_json,
                    },
                },
            )

            raw_content = response.choices[0].message.content
            if raw_content is None:
                raise LLMError(
                    message="OpenAI returned empty response content",
                    error_type="EMPTY_RESPONSE",
                    recoverable=True,
                )

            extracted_data = request.output_schema.model_validate_json(raw_content)

            processing_time = time.time() - start_time

            return ExtractionResponse(
                extracted_data=extracted_data,
                raw_output=raw_content,
                token_usage={
                    "prompt_tokens": response.usage.prompt_tokens
                    if response.usage
                    else 0,
                    "completion_tokens": (
                        response.usage.completion_tokens if response.usage else 0
                    ),
                    "total_tokens": response.usage.total_tokens
                    if response.usage
                    else 0,
                },
                confidence_score=0.85,
                processing_time_seconds=processing_time,
                model_name=self.model_name,
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise LLMError(
                message=f"Extraction failed: {str(e)}",
                error_type="EXTRACTION_ERROR",
                recoverable=True,
            ) from e

    async def validate_connection(self) -> bool:
        """Validate OpenAI API connection."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)
            await client.models.list()
            return True
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False

    def get_model_info(self) -> dict:
        """Get model information."""
        return {
            "model_name": self.model_name,
            "provider": "OpenAI",
            "capabilities": ["text_extraction", "structured_output"],
        }
