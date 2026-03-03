# Prompt 22: Self-Correction Loop with Critique Agent

## Status
[COMPLETED]

## Context

Our current processing pipeline is linear: Preprocess → Extract → Validate → Done. The reference implementation (`~/projects/llm-service`) uses a self-correction loop where a "Critic" agent audits the extraction and, if the QA score is below a threshold, loops back to the extraction step with explicit feedback notes. This dramatically improves extraction accuracy.

This is a key "Head of Engineering" differentiator — showing we care about automated quality assurance, not just a one-shot extraction.

## Objective

Add a self-correction loop to the processing pipeline:
1. After extraction, run a Critic agent that verifies each extracted field against the source document
2. If QA score < 80%, loop back to extraction with feedback notes (max 2 retries)
3. Track retry count, feedback history, and QA scores in the response

## Requirements

### 1. Create Critic Agent

File: `src/doc_extract/agents/critic_agent.py`

```python
"""Critic agent for validating extractions against source documents.

Inspired by the production "Panel of Critics" pattern from llm-service.
Uses the same LLM to verify that extracted fields match the source document.

ADR Reference: docs/adr/020_multi_critic_panel.md
"""
import time
from pydantic import BaseModel, Field
from doc_extract.core.logging import logger


class FieldAssessment(BaseModel):
    """Assessment of a single extracted field."""
    field_name: str = Field(..., description="Name of the field being assessed")
    is_correct: bool = Field(..., description="True if extracted value matches source")
    correct_value: str | None = Field(None, description="Correct value if extraction was wrong")
    note: str | None = Field(None, description="Explanation of why the field is correct/incorrect")


class CritiqueResult(BaseModel):
    """Result from the Critic agent."""
    assessments: list[FieldAssessment] = Field(default_factory=list)
    overall_score: float = Field(0.0, description="Percentage of fields marked correct (0-100)")
    feedback_notes: list[str] = Field(default_factory=list, description="Feedback for re-extraction")


CRITIQUE_PROMPT = """You are a meticulous QA auditor for document extraction systems.

You are given:
1. A source document
2. An extraction result (JSON) claiming to represent structured data from that document

Your job is to verify EVERY extracted field against the source document.

For each field in the extraction:
- Check if the value matches what's in the document
- If incorrect, provide the correct value from the document
- If the field was not found in the document but a value was extracted, mark it as incorrect

Return your assessment as a list of FieldAssessment objects.

Be strict. Only mark a field as correct if you can verify it in the source document.
If previous feedback notes are provided, pay special attention to those fields.
"""


class CriticAgent:
    """Runs a critique of extracted data against the source document."""

    def __init__(self, llm_adapter=None):
        """Initialize with an LLM adapter (defaults to OpenAIAdapter)."""
        if llm_adapter is None:
            from doc_extract.adapters.openai_adapter import OpenAIAdapter
            self.llm = OpenAIAdapter()
        else:
            self.llm = llm_adapter

    async def critique(
        self,
        document_url: str,
        extracted_data: dict,
        feedback_history: list[str] | None = None,
    ) -> CritiqueResult:
        """Run critique of extraction against source document.

        Args:
            document_url: URL/path to the source document
            extracted_data: The extraction result to verify
            feedback_history: Previous feedback from failed critiques

        Returns:
            CritiqueResult with per-field assessments and overall score
        """
        start_time = time.time()

        # Build the critique prompt with context
        feedback_context = ""
        if feedback_history:
            feedback_context = (
                "\n\nPREVIOUS FEEDBACK (pay special attention to these fields):\n"
                + "\n".join(f"- {note}" for note in feedback_history)
            )

        import json
        user_message = (
            f"Source document: {document_url}\n\n"
            f"Extracted data to verify:\n{json.dumps(extracted_data, indent=2, default=str)}"
            f"{feedback_context}"
        )

        try:
            from openai import AsyncOpenAI
            import os

            client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": CRITIQUE_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "CritiqueResult",
                        "schema": CritiqueResult.model_json_schema(),
                    },
                },
            )

            result = CritiqueResult.model_validate_json(
                response.choices[0].message.content
            )

            # Calculate overall score
            if result.assessments:
                correct = sum(1 for a in result.assessments if a.is_correct)
                result.overall_score = (correct / len(result.assessments)) * 100

            # Build feedback notes from incorrect fields
            result.feedback_notes = [
                f"Field '{a.field_name}' was incorrect. "
                f"Correct value: {a.correct_value}. Note: {a.note}"
                for a in result.assessments
                if not a.is_correct
            ]

            processing_time = time.time() - start_time
            logger.info(
                f"Critique completed in {processing_time:.2f}s. "
                f"Score: {result.overall_score:.1f}% "
                f"({sum(1 for a in result.assessments if a.is_correct)}/{len(result.assessments)} correct)"
            )

            return result

        except Exception as e:
            logger.error(f"Critique failed: {e}")
            # On critique failure, return a passing result to avoid blocking
            return CritiqueResult(
                overall_score=100.0,
                feedback_notes=[f"Critique agent failed: {e}. Passing by default."],
            )
```

### 2. Modify ProcessingService to Add Retry Loop

File: `src/doc_extract/services/processing.py` (MODIFY)

Replace the existing `ProcessingService` with a version that includes the self-correction loop:

```python
"""Document processing service with self-correction loop.

Pipeline: Extract → Critique → (Retry if QA < threshold) → Return
Max retries: 2 (configurable)
QA threshold: 80% (configurable)

Inspired by the production graph at ~/projects/llm-service/src/llm_service/assistant/graph.py
where CritiqueNode loops back to ExtractionNode with feedback.

ADR Reference: docs/adr/020_multi_critic_panel.md
"""
import time
from doc_extract.adapters.local_storage import LocalFileSystemAdapter
from doc_extract.adapters.openai_adapter import OpenAIAdapter
from doc_extract.agents.critic_agent import CriticAgent, CritiqueResult
from doc_extract.core.logging import logger


# Configurable settings
QA_THRESHOLD = 80.0  # Score below which we retry
MAX_RETRIES = 2      # Maximum retry attempts


class ProcessingService:
    """Service for processing document extraction with self-correction."""

    def __init__(self):
        self.storage = LocalFileSystemAdapter()
        self.llm = OpenAIAdapter()
        self.critic = CriticAgent()
        logger.info("ProcessingService initialized with self-correction loop")

    async def process_submission(self, submission_id: str, storage_path: str) -> dict:
        """Process a document submission with self-correction loop.

        Flow:
        1. Download document
        2. Extract structured data
        3. Run critique agent
        4. If QA score < threshold and retries remaining -> go to step 2 with feedback
        5. Return final result with QA metadata
        """
        logger.info(f"Processing submission: {submission_id}")
        pipeline_start = time.time()

        try:
            await self.storage.download(storage_path)

            from doc_extract.domain.borrower import BorrowerProfile
            from doc_extract.ports.llm import ExtractionRequest

            document_url = f"file://{storage_path}"
            feedback_history: list[str] = []
            retry_count = 0
            best_result = None
            best_qa_score = 0.0
            critique_result: CritiqueResult | None = None

            while retry_count <= MAX_RETRIES:
                # Build extraction prompt with feedback from previous attempts
                system_prompt = None
                if feedback_history:
                    feedback_block = "\n".join(f"- {note}" for note in feedback_history)
                    system_prompt = (
                        "IMPORTANT: Previous extraction had errors. "
                        "Please correct the following issues:\n"
                        f"{feedback_block}\n\n"
                        "Re-extract all fields carefully, paying special attention "
                        "to the fields mentioned above."
                    )

                request = ExtractionRequest(
                    document_url=document_url,
                    document_type="loan_application",
                    output_schema=BorrowerProfile,
                    system_prompt=system_prompt,
                )

                # Step 1: Extract
                extraction_result = await self.llm.extract_structured(request)
                extracted_data = extraction_result.extracted_data.model_dump()

                # Step 2: Critique
                critique_result = await self.critic.critique(
                    document_url=document_url,
                    extracted_data=extracted_data,
                    feedback_history=feedback_history if feedback_history else None,
                )

                qa_score = critique_result.overall_score

                # Track best result
                if qa_score > best_qa_score:
                    best_qa_score = qa_score
                    best_result = extraction_result

                logger.info(
                    f"Attempt {retry_count + 1}: QA score = {qa_score:.1f}% "
                    f"(threshold: {QA_THRESHOLD}%)"
                )

                # Step 3: Decide whether to retry
                if qa_score >= QA_THRESHOLD:
                    logger.info(
                        f"QA threshold met on attempt {retry_count + 1}. "
                        f"Score: {qa_score:.1f}%"
                    )
                    break

                if retry_count < MAX_RETRIES:
                    logger.info(
                        f"QA score {qa_score:.1f}% below threshold. "
                        f"Retrying ({retry_count + 1}/{MAX_RETRIES})..."
                    )
                    feedback_history.extend(critique_result.feedback_notes)
                    retry_count += 1
                else:
                    logger.warning(
                        f"Max retries ({MAX_RETRIES}) reached. "
                        f"Using best result (QA: {best_qa_score:.1f}%)"
                    )
                    break

            pipeline_time = time.time() - pipeline_start

            return {
                "status": "success",
                "data": best_result.extracted_data.model_dump(),
                "confidence": best_result.confidence_score,
                "processing_time": pipeline_time,
                "qa_score": best_qa_score,
                "retry_count": retry_count,
                "critique": {
                    "assessments": [a.model_dump() for a in critique_result.assessments]
                    if critique_result
                    else [],
                    "feedback_history": feedback_history,
                },
            }

        except Exception as e:
            logger.error(f"Processing failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }

    async def validate_extraction(self, extracted_data: dict) -> dict:
        """Validate extracted data."""
        validation_errors = []
        if not extracted_data.get("name"):
            validation_errors.append("Missing borrower name")
        if not extracted_data.get("address"):
            validation_errors.append("Missing address")
        if extracted_data.get("income_history") is None:
            validation_errors.append("Missing income history")
        return {
            "passed": len(validation_errors) == 0,
            "errors": validation_errors,
            "requires_manual_review": len(validation_errors) > 0,
        }
```

### 3. Create __init__.py for agents module

File: `src/doc_extract/agents/__init__.py`

```python
"""Agent modules for document extraction."""
```

### 4. Update API Response to Include QA Metadata

In `src/doc_extract/api/main.py`, the `process_submission` already returns a dict that gets stored. The new fields (`qa_score`, `retry_count`, `critique`) will be available in the response automatically if the `QueryResponse` model is updated or the raw dict is returned.

### 5. Update Tests

Add test for self-correction loop in `tests/test_self_correction.py`:

```python
"""Tests for self-correction loop."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from doc_extract.agents.critic_agent import CriticAgent, CritiqueResult, FieldAssessment
from doc_extract.services.processing import ProcessingService


@pytest.mark.asyncio
async def test_critique_passes_on_first_attempt():
    """Test extraction succeeds without retry when QA score is high."""
    # Mock LLM and Critic to return high-quality results
    ...


@pytest.mark.asyncio
async def test_self_correction_retries_on_low_score():
    """Test that low QA score triggers retry with feedback."""
    ...


@pytest.mark.asyncio
async def test_max_retries_respected():
    """Test that max retries limit is enforced."""
    ...


@pytest.mark.asyncio
async def test_best_result_kept_across_retries():
    """Test that the best result across all attempts is returned."""
    ...
```

## Verification

```bash
# All tests must pass
just test

# Type check
pyright src/doc_extract/

# Manual test
just dev
curl -X POST http://localhost:8000/api/v1/documents/upload -F "file=@test.pdf"
# Response should include qa_score and retry_count
```

## Constraints
- **NO REGRESSION** — Existing endpoints and tests must continue to work
- **Graceful degradation** — If critique agent fails, return extraction result anyway
- **Configurable** — QA_THRESHOLD and MAX_RETRIES should be configurable
- **Observable** — Log each retry attempt with QA score
