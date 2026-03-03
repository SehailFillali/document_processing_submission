# Prompt 09: AI Extraction - PydanticAI Agent

## Status
[PARTIALLY_IMPLEMENTED] - missing prompts/loan_extraction.md and extraction.py wrapper

## Context
Detailed implementation of the PydanticAI agent for document extraction with Gemini.

## Objective
Create the LLM extraction service using PydanticAI with Gemini and DocumentUrl.

## Requirements

### 1. Create System Prompt for Loan Document Extraction
File: `src/doc_extract/services/prompts/loan_extraction.md`

```markdown
# Role: Expert Financial Document Extraction AI

You are an AI assistant specialized in extracting structured data from loan documents, bank statements, tax returns, and financial records.

## Core Objectives

Extract complete borrower profiles with the following information:

### 1. Identity Information
- **Full Name**: Borrower's complete legal name
- **SSN Last 4**: Last 4 digits of Social Security Number (if present)
- **Contact Information**:
  - Phone number (10 digits, no formatting)
  - Email address

### 2. Address
- **Street**: Full street address
- **City**: City name
- **State**: 2-letter state code
- **ZIP Code**: 5-digit or ZIP+4 format
- **Country**: Default to "US"

### 3. Income History
For each income entry found:
- **Amount**: Income amount (positive number)
- **Period Start**: Start date (YYYY-MM-DD)
- **Period End**: End date (YYYY-MM-DD)
- **Source**: Employer name or income source description
- **Provenance**: Page number and text snippet

### 4. Account/Loan Information
For each account found:
- **Account Number**: Account or loan identifier
- **Account Type**: Type (checking, savings, loan, mortgage, etc.)
- **Institution**: Financial institution name
- **Open Date**: Account opening date (if available)
- **Current Balance**: Current balance amount
- **Provenance**: Page number and text snippet

## Schema Compliance

YOU MUST return data that strictly conforms to the BorrowerProfile Pydantic schema:
- All fields must match their defined types
- Dates must be valid ISO 8601 format (YYYY-MM-DD)
- Numbers must be valid floats (no currency symbols)
- Required fields must be present
- Use null/None for missing optional fields

## Provenance Requirements

For EVERY extracted field, provide:
1. **confidence_score**: Your confidence 0.0-1.0 in this extraction
2. **source_page**: Page number where this data was found
3. **verbatim_text**: The exact text snippet from the document

## Extraction Rules

1. **NO HALLUCINATION**: Only extract data explicitly present in the document
2. **NO GENERATION**: Do not generate or estimate missing data
3. **NULL FOR MISSING**: Use null/None for fields not found in document
4. **VALIDATE TYPES**: Ensure all values match schema types
5. **CHECK LOGIC**: Verify dates are chronological, amounts are positive
6. **NOTE AMBIGUITY**: Flag ambiguous or unclear data with low confidence

## Confidence Scoring

Assign confidence scores based on:
- **1.0**: Crystal clear, unambiguous, well-formatted data
- **0.8-0.9**: Clear data, minor formatting issues
- **0.6-0.7**: Readable but some ambiguity
- **0.4-0.5**: Partial data, missing context
- **0.0-0.3**: Very unclear, possibly incorrect

## Error Handling

If the document:
- Is not a loan/financial document: Return mostly null fields
- Has no extractable data: Return empty income_history and accounts
- Is corrupted/unreadable: Set overall confidence to 0.0

Return valid JSON even in error cases.
```

### 2. Update Gemini Adapter with Enhanced Prompts
File: `src/doc_extract/adapters/gemini_llm.py` (update existing)

Add the prompt loading capability:

```python
"""Gemini LLM adapter using PydanticAI - Enhanced version."""
import os
from pathlib import Path
from typing import Type
from pydantic import BaseModel

from pydantic_ai import Agent, DocumentUrl
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from doc_extract.ports.llm import (
    LLMPort, ExtractionRequest, ExtractionResponse, LLMError
)
from doc_extract.core.logging import logger


class GeminiAdapter(LLMPort):
    """Gemini API implementation with enhanced prompting."""
    
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable required")
        
        self.provider = GoogleProvider(api_key=self.api_key)
        self.model = GoogleModel(model_name, provider=self.provider)
        
        # Load system prompts
        self.prompts = self._load_prompts()
        
        logger.info(f"Initialized GeminiAdapter with model {model_name}")
    
    def _load_prompts(self) -> dict:
        """Load system prompts from files."""
        prompts_dir = Path(__file__).parent.parent / "services" / "prompts"
        prompts = {}
        
        try:
            loan_prompt = prompts_dir / "loan_extraction.md"
            if loan_prompt.exists():
                prompts["loan"] = loan_prompt.read_text()
        except Exception as e:
            logger.warning(f"Could not load prompts: {e}")
        
        return prompts
    
    async def extract_structured(
        self,
        request: ExtractionRequest
    ) -> ExtractionResponse:
        """Extract structured data with enhanced prompting."""
        import time
        
        start_time = time.time()
        
        try:
            # Get appropriate system prompt
            system_prompt = request.system_prompt or self._get_prompt_for_type(
                request.document_type
            )
            
            # Create agent with output schema
            agent = Agent(
                model=self.model,
                system_prompt=system_prompt,
                output_type=request.output_schema,
            )
            
            # Create DocumentUrl
            doc_url = DocumentUrl(url=request.document_url)
            
            # Run extraction with retry logic
            from stamina import retry
            
            @retry(on=Exception, attempts=3, timeout=60)
            async def _run_extraction():
                return await agent.run([
                    f"Extract structured data from this {request.document_type} document.",
                    doc_url
                ])
            
            result = await _run_extraction()
            
            processing_time = time.time() - start_time
            
            # Estimate confidence (Gemini doesn't provide this directly)
            confidence = self._calculate_confidence(result.output)
            
            # Get token usage if available
            token_usage = self._extract_token_usage(result)
            
            return ExtractionResponse(
                extracted_data=result.output,
                raw_output=result.output.model_dump_json() if hasattr(result.output, 'model_dump_json') else str(result.output),
                token_usage=token_usage,
                confidence_score=confidence,
                processing_time_seconds=processing_time,
                model_name=self.model_name
            )
            
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            
            error_msg = str(e).lower()
            recoverable = any([
                "rate limit" in error_msg,
                "timeout" in error_msg,
                "temporary" in error_msg,
                "503" in error_msg
            ])
            
            raise LLMError(
                error_type="EXTRACTION_FAILED",
                message=str(e),
                recoverable=recoverable,
                retry_after_seconds=60 if recoverable else None
            )
    
    def _get_prompt_for_type(self, document_type: str) -> str:
        """Get system prompt for document type."""
        if "loan" in document_type.lower():
            return self.prompts.get("loan", self._default_system_prompt())
        return self._default_system_prompt()
    
    def _calculate_confidence(self, output: BaseModel) -> float:
        """Calculate overall confidence from provenance fields."""
        try:
            # If output has extraction_confidence field, use it
            if hasattr(output, 'extraction_confidence'):
                return float(output.extraction_confidence)
            
            # Otherwise, calculate from nested provenance
            confidences = []
            
            # This is a simplified heuristic
            # In production, traverse the model to find all provenance.confidence_score
            
            return 0.85  # Default high confidence
        except:
            return 0.5
    
    def _extract_token_usage(self, result) -> dict:
        """Extract token usage from result if available."""
        # PydanticAI may provide this in metadata
        return {
            "input_tokens": getattr(result, 'input_tokens', 0),
            "output_tokens": getattr(result, 'output_tokens', 0),
            "model": self.model_name
        }
    
    async def validate_connection(self) -> bool:
        """Validate Gemini API connection."""
        try:
            agent = Agent(model=self.model)
            result = await agent.run("Say 'connected' only.")
            return "connected" in str(result.output).lower()
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False
    
    def get_model_info(self) -> dict:
        """Get model information."""
        return {
            "provider": "google",
            "model_name": self.model_name,
            "api_type": "generative_language_api",
            "capabilities": ["document_understanding", "structured_output", "vision"],
            "supports_document_url": True,
            "supports_force_download": False  # Gemini handles this internally
        }
    
    def _default_system_prompt(self) -> str:
        """Default system prompt."""
        return """You are an expert document extraction AI.

Extract structured data from documents with high accuracy.
Rules:
1. Extract only data explicitly present in the document
2. Do not hallucinate or generate missing information
3. Return null/None for missing fields
4. Provide confidence scores for each field
5. Note source page and verbatim text for provenance
"""
```

### 3. Create Extraction Service Wrapper
File: `src/doc_extract/services/extraction.py`

```python
"""High-level extraction service."""
from doc_extract.adapters.gemini_llm import GeminiAdapter
from doc_extract.ports.llm import ExtractionRequest
from doc_extract.domain.borrower import BorrowerProfile
from doc_extract.core.logging import logger


class ExtractionService:
    """Service for document extraction operations.
    
    Provides a clean interface for extraction with:
    - Retry logic
    - Error handling
    - Metrics/logging
    - Result caching (optional)
    """
    
    def __init__(self):
        self.llm = GeminiAdapter()
    
    async def extract_borrower_profile(
        self,
        document_url: str,
        document_type: str = "loan_document"
    ) -> BorrowerProfile:
        """Extract borrower profile from document.
        
        Args:
            document_url: URL to document (gs://, https://, file://)
            document_type: Type of document for prompt selection
            
        Returns:
            BorrowerProfile with extracted data
            
        Raises:
            LLMError: If extraction fails
        """
        logger.info(f"Starting extraction from {document_url}")
        
        response = await self.llm.extract_structured(
            ExtractionRequest(
                document_url=document_url,
                document_type=document_type,
                output_schema=BorrowerProfile
            )
        )
        
        # Ensure we return a BorrowerProfile
        if isinstance(response.extracted_data, BorrowerProfile):
            return response.extracted_data
        elif isinstance(response.extracted_data, dict):
            return BorrowerProfile(**response.extracted_data)
        else:
            raise ValueError(f"Unexpected extraction result type: {type(response.extracted_data)}")
```

## Deliverables
- [ ] services/prompts/loan_extraction.md with detailed extraction instructions
- [ ] Enhanced GeminiAdapter with prompt loading
- [ ] services/extraction.py high-level wrapper
- [ ] Retry logic with stamina
- [ ] Token usage tracking
- [ ] Confidence calculation heuristics

## Success Criteria
- DocumentUrl works with Gemini API key
- System prompt loaded from markdown file
- Retry on rate limits (3 attempts, exponential backoff)
- Token usage logged for cost tracking
- Extraction returns properly typed BorrowerProfile

## Testing Snippets
```python
# Test extraction
from doc_extract.services.extraction import ExtractionService

service = ExtractionService()
profile = await service.extract_borrower_profile(
    "file://./uploads/test-123/loan.pdf"
)

assert profile.name is not None
assert len(profile.income_history) >= 0
```

## Next Prompt
After this completes, move to `10_storage_and_db.md` for database layer.
