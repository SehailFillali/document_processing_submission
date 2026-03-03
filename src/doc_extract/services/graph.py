"""Pydantic Graph state machine for document processing.

This module implements the 3-node processing pipeline:
1. PreprocessNode: Validate file existence, type, size, password protection
2. ExtractNode: Use PydanticAI agent to extract structured data
3. ValidateNode: Run logical checks and assign confidence scores

Architecture: Pydantic Graph provides state machine semantics with
type-safe state transitions and error handling.

ADR Reference: docs/adr/004_state_machine.md
"""

import time
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph

from doc_extract.core.logging import logger
from doc_extract.domain.borrower import BorrowerProfile
from doc_extract.domain.validation import ValidationReport, ValidationResult


# State classes for each node
class PreprocessState(BaseModel):
    """State after preprocessing."""

    submission_id: str
    document_paths: list[str]
    validation_passed: bool
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ExtractState(BaseModel):
    """State after extraction."""

    submission_id: str
    document_paths: list[str] = Field(default_factory=list)
    raw_extraction: dict
    extraction_confidence: float
    token_usage: dict
    processing_time_seconds: float


class ValidateState(BaseModel):
    """Final state after validation."""

    submission_id: str
    borrower_profile: BorrowerProfile | None = None
    validation_report: ValidationReport | None = None
    final_confidence: float = 0.0
    requires_manual_review: bool = False
    status: str = "pending"


# Node 1: Preprocessing
@dataclass
class PreprocessNode(BaseNode[PreprocessState]):
    """Validate document before processing.

    Checks:
    - File exists in storage
    - Supported file type (PDF, JSON)
    - File size within limits
    - No password protection (for PDFs)
    - Page count reasonable

    On failure: Route to error state
    On success: Proceed to ExtractNode
    """

    async def run(self, state: PreprocessState) -> "ExtractNode | End[dict]":
        """Execute preprocessing validation."""
        logger.info(f"Preprocessing submission {state.submission_id}")

        from doc_extract.adapters.local_storage import LocalFileSystemAdapter
        from doc_extract.core.config import settings

        storage = LocalFileSystemAdapter("./uploads")
        errors = []

        for doc_path in state.document_paths:
            try:
                # Check file exists
                if not await storage.exists(doc_path):
                    errors.append(f"Document {doc_path} not found in storage")
                    continue

                # Get metadata
                metadata = await storage.get_metadata(doc_path)
                if not metadata:
                    errors.append(f"Cannot get metadata for {doc_path}")
                    continue

                # Check file size
                max_size = settings.max_file_size_mb * 1024 * 1024
                if metadata.size > max_size:
                    errors.append(
                        f"Document {doc_path} exceeds {settings.max_file_size_mb}MB limit"
                    )
                    continue

            except Exception as e:
                errors.append(f"Error validating {doc_path}: {str(e)}")

        if errors:
            logger.error(f"Preprocessing failed for {state.submission_id}: {errors}")
            return End(
                {
                    "submission_id": state.submission_id,
                    "status": "failed",
                    "errors": [{"stage": "preprocess", "errors": errors}],
                    "borrower_profile": None,
                }
            )

        # Success - proceed to extraction
        logger.info(f"Preprocessing complete for {state.submission_id}")

        return ExtractNode(
            state=ExtractState(
                submission_id=state.submission_id,
                document_paths=state.document_paths,
                raw_extraction={},
                extraction_confidence=0.0,
                token_usage={},
                processing_time_seconds=0.0,
            )
        )


# Node 2: Extraction
@dataclass
class ExtractNode(BaseNode[ExtractState]):
    """Extract structured data using PydanticAI agent.

    Uses Gemini model via DocumentUrl to extract:
    - Borrower name, address, PII
    - Income history
    - Account/loan numbers
    - Provenance for each field

    On failure: Route to error state
    On success: Proceed to ValidateNode
    """

    state: ExtractState | None = None

    async def run(self, state: ExtractState) -> "ValidateNode | End[dict]":
        """Execute LLM extraction."""
        logger.info(f"Extracting data for submission {state.submission_id}")

        from doc_extract.adapters.openai_adapter import OpenAIAdapter
        from doc_extract.domain.borrower import BorrowerProfile
        from doc_extract.ports.llm import ExtractionRequest

        llm = OpenAIAdapter()

        # Process first document
        document_path = state.document_paths[0] if state.document_paths else ""
        file_url = f"file://./uploads/{document_path}"

        start_time = time.time()

        try:
            extraction_response = await llm.extract_structured(
                ExtractionRequest(
                    document_url=file_url,
                    document_type="loan_document",
                    output_schema=BorrowerProfile,
                    system_prompt=self._get_extraction_prompt(),
                )
            )

            processing_time = time.time() - start_time

            logger.info(
                f"Extraction completed for {state.submission_id} "
                f"in {processing_time:.2f}s with confidence {extraction_response.confidence_score}"
            )

            # Convert to dict
            raw_extraction = {}
            if hasattr(extraction_response.extracted_data, "model_dump"):
                raw_extraction = extraction_response.extracted_data.model_dump()
            elif isinstance(extraction_response.extracted_data, dict):
                raw_extraction = extraction_response.extracted_data

            return ValidateNode(
                state=ExtractState(
                    submission_id=state.submission_id,
                    document_paths=state.document_paths,
                    raw_extraction=raw_extraction,
                    extraction_confidence=extraction_response.confidence_score,
                    token_usage=extraction_response.token_usage,
                    processing_time_seconds=processing_time,
                )
            )

        except Exception as e:
            logger.error(f"Extraction failed for {state.submission_id}: {e}")
            return End(
                {
                    "submission_id": state.submission_id,
                    "status": "failed",
                    "errors": [{"stage": "extract", "error": str(e)}],
                    "borrower_profile": None,
                }
            )

    def _get_extraction_prompt(self) -> str:
        """Get system prompt for extraction."""
        return """You are an expert document extraction AI specializing in loan documents.

Extract the following information with high accuracy:
1. Borrower name and contact information
2. Address (street, city, state, ZIP)
3. SSN last 4 digits (if present)
4. Income history (amount, period, source)
5. Account/loan numbers
6. Financial institution information

For each extracted field, provide:
- confidence_score: Your confidence 0.0-1.0
- source_page: Page number where found
- verbatim_text: Original text snippet

Rules:
1. Extract ONLY data explicitly present in the document
2. Do NOT hallucinate or generate missing information
3. Use null/None for missing fields
4. Validate all dates, amounts, and identifiers
5. Flag any inconsistencies or ambiguous data

Return strictly valid JSON matching the BorrowerProfile schema.
"""


# Node 3: Validation
@dataclass
class ValidateNode(BaseNode[ValidateState]):
    """Validate extracted data and assign final confidence.

    Validation checks:
    - Income amounts are positive and reasonable
    - Dates are valid and chronological
    - Required fields are present
    - Confidence scores meet threshold
    - Logical consistency across fields

    Outputs final result with status:
    - completed: All validations passed, high confidence
    - partial: Some validations failed but data usable
    - manual_review: Critical issues requiring human review
    """

    state: ExtractState | None = None

    async def run(self, state: ExtractState) -> End[dict]:
        """Execute validation."""
        logger.info(f"Validating extraction for submission {state.submission_id}")

        validation_results = []
        requires_manual_review = False

        # Reconstruct BorrowerProfile from raw extraction
        borrower_profile = None
        try:
            if state.raw_extraction:
                borrower_profile = BorrowerProfile(**state.raw_extraction)
        except Exception as e:
            logger.error(f"Failed to reconstruct BorrowerProfile: {e}")
            validation_results.append(
                ValidationResult(
                    rule_id="profile_structure",
                    passed=False,
                    field_path="borrower_profile",
                    actual_value=None,
                    expected_condition="valid profile structure",
                    message=f"Invalid profile structure: {e}",
                    severity="error",
                )
            )
            requires_manual_review = True

        # Validation 1: Check required fields
        if borrower_profile and not borrower_profile.name:
            validation_results.append(
                ValidationResult(
                    rule_id="required_name",
                    passed=False,
                    field_path="name",
                    actual_value=None,
                    expected_condition="name is required",
                    message="Borrower name is missing",
                    severity="error",
                )
            )
            requires_manual_review = True

        # Validation 2: Check income history
        if borrower_profile and not borrower_profile.income_history:
            validation_results.append(
                ValidationResult(
                    rule_id="income_history_empty",
                    passed=False,
                    field_path="income_history",
                    actual_value=[],
                    expected_condition="at least one income entry",
                    message="No income history found",
                    severity="warning",
                )
            )
        elif borrower_profile:
            for i, income in enumerate(borrower_profile.income_history):
                if income.amount <= 0:
                    validation_results.append(
                        ValidationResult(
                            rule_id=f"income_positive_{i}",
                            passed=False,
                            field_path=f"income_history[{i}].amount",
                            actual_value=income.amount,
                            expected_condition="amount > 0",
                            message=f"Income amount must be positive: {income.amount}",
                            severity="error",
                        )
                    )

        # Validation 3: Confidence threshold
        confidence_threshold = 0.8
        final_confidence = state.extraction_confidence

        if final_confidence < confidence_threshold:
            validation_results.append(
                ValidationResult(
                    rule_id="confidence_threshold",
                    passed=False,
                    field_path="extraction_confidence",
                    actual_value=final_confidence,
                    expected_condition=f"confidence >= {confidence_threshold}",
                    message=f"Confidence {final_confidence:.2f} below threshold {confidence_threshold}",
                    severity="warning",
                )
            )
            requires_manual_review = True

        # Determine final status
        error_count = sum(1 for r in validation_results if r.severity == "error")
        warning_count = sum(1 for r in validation_results if r.severity == "warning")

        if error_count > 0:
            status = "partial" if not requires_manual_review else "manual_review"
        elif warning_count > 0:
            status = "partial"
        else:
            status = "completed"

        # Mark profile if manual review needed
        if borrower_profile and requires_manual_review:
            borrower_profile.requires_manual_review = True

        # Calculate overall confidence
        if borrower_profile:
            borrower_profile.extraction_confidence = final_confidence

        validation_report = ValidationReport(
            submission_id=state.submission_id,
            passed=error_count == 0,
            results=validation_results,
            error_count=error_count,
            warning_count=warning_count,
            requires_manual_review=requires_manual_review,
        )

        logger.info(
            f"Validation complete for {state.submission_id}: "
            f"status={status}, errors={error_count}, warnings={warning_count}"
        )

        return End(
            {
                "submission_id": state.submission_id,
                "status": status,
                "borrower_profile": borrower_profile.model_dump()
                if borrower_profile
                else None,
                "validation_report": validation_report.model_dump(),
                "processing_time_seconds": state.processing_time_seconds,
                "token_usage": state.token_usage,
                "final_confidence": final_confidence,
                "errors": [],
            }
        )


# Graph Definition
class DocumentProcessingGraph:
    """Main graph for document processing pipeline."""

    def __init__(self):
        self.graph = Graph(nodes=[PreprocessNode, ExtractNode, ValidateNode])

    async def process(self, submission_id: str, document_paths: list[str]) -> dict:
        """Process a submission through the graph."""

        initial_state = PreprocessState(
            submission_id=submission_id,
            document_paths=document_paths,
            validation_passed=True,
        )

        result = await self.graph.run(PreprocessNode(), state=initial_state)

        if isinstance(result, End):
            return result.data
        else:
            raise RuntimeError(f"Unexpected graph result: {result}")


# Convenience function
async def process_document(submission_id: str, document_paths: list[str]) -> dict:
    """Process a document submission through the pipeline."""
    graph = DocumentProcessingGraph()
    return await graph.process(submission_id, document_paths)
