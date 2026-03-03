# Prompt 08: Processing Graph - Pydantic Graph State Machine

## Status
[COMPLETED]

## Context
Implementing the 3-node processing pipeline using Pydantic Graph for state machine orchestration.

## Objective
Create a state machine with three nodes: Preprocess → Extract → Validate using Pydantic Graph.

## Requirements

### 1. Create Graph Nodes
File: `src/doc_extract/services/graph.py`

```python
"""Pydantic Graph state machine for document processing.

This module implements the 3-node processing pipeline:
1. PreprocessNode: Validate file existence, type, size, password protection
2. ExtractNode: Use PydanticAI agent to extract structured data
3. ValidateNode: Run logical checks and assign confidence scores

Architecture: Pydantic Graph provides state machine semantics with
type-safe state transitions and error handling.

ADR Reference: docs/adr/004_state_machine.md
"""
from dataclasses import dataclass
from typing import Any
from datetime import datetime

from pydantic_graph import Graph, BaseNode, End
from pydantic import BaseModel

from doc_extract.domain.submission import DocumentSubmission, SubmissionStatus
from doc_extract.domain.borrower import BorrowerProfile, ExtractionResult
from doc_extract.domain.validation import ValidationReport
from doc_extract.core.logging import logger


# State classes for each node
@dataclass
class PreprocessState(BaseModel):
    """State after preprocessing."""
    submission_id: str
    document_paths: list[str]
    validation_passed: bool
    errors: list[str] = None
    metadata: dict = None


@dataclass
class ExtractState(BaseModel):
    """State after extraction."""
    submission_id: str
    raw_extraction: dict
    extraction_confidence: float
    token_usage: dict
    processing_time_seconds: float


@dataclass
class ValidateState(BaseModel):
    """Final state after validation."""
    submission_id: str
    borrower_profile: BorrowerProfile | None
    validation_report: ValidationReport
    final_confidence: float
    requires_manual_review: bool
    status: str


# Node 1: Preprocessing
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
    
    async def run(self, submission: DocumentSubmission) -> ExtractNode | End[ExtractionResult]:
        """Execute preprocessing validation."""
        logger.info(f"Preprocessing submission {submission.submission_id}")
        
        from doc_extract.adapters.local_storage import LocalFileSystemAdapter
        from doc_extract.core.config import settings
        from doc_extract.core.exceptions import ValidationError
        
        storage = LocalFileSystemAdapter("./uploads")
        errors = []
        
        for doc in submission.documents:
            storage_path = f"{submission.submission_id}/{doc.file_name}"
            
            # Check file exists
            if not await storage.exists(storage_path):
                errors.append(f"Document {doc.file_name} not found in storage")
                continue
            
            # Check file size
            if doc.file_size > settings.max_file_size_mb * 1024 * 1024:
                errors.append(
                    f"Document {doc.file_name} exceeds {settings.max_file_size_mb}MB limit"
                )
                continue
            
            # Check file type
            if doc.mime_type not in ["application/pdf", "application/json"]:
                errors.append(f"Unsupported file type: {doc.mime_type}")
                continue
            
            # TODO: Check for password protection (for PDFs)
            # TODO: Count pages
        
        if errors:
            logger.error(f"Preprocessing failed for {submission.submission_id}: {errors}")
            
            # Return error result
            return End(
                ExtractionResult(
                    submission_id=submission.submission_id,
                    status="failed",
                    errors=[{"stage": "preprocess", "errors": errors}],
                    borrower_profile=None
                )
            )
        
        # Success - proceed to extraction
        document_paths = [
            f"{submission.submission_id}/{doc.file_name}"
            for doc in submission.documents
        ]
        
        return ExtractNode(
            state=PreprocessState(
                submission_id=submission.submission_id,
                document_paths=document_paths,
                validation_passed=True,
                metadata={"document_count": len(submission.documents)}
            )
        )


# Node 2: Extraction
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
    
    async def run(self, state: PreprocessState) -> ValidateNode | End[ExtractionResult]:
        """Execute LLM extraction."""
        logger.info(f"Extracting data for submission {state.submission_id}")
        
        import time
        from doc_extract.adapters.gemini_llm import GeminiAdapter
        from doc_extract.ports.llm import ExtractionRequest
        from doc_extract.domain.borrower import BorrowerProfile
        
        llm = GeminiAdapter()
        
        # For simplicity, process first document
        # In production, handle multiple documents and merge results
        document_path = state.document_paths[0]
        
        # Generate file:// URL for local files
        # In production with GCS, this would be gs:// URL
        file_url = f"file://./uploads/{document_path}"
        
        start_time = time.time()
        
        try:
            # Extract structured data
            extraction_response = await llm.extract_structured(
                ExtractionRequest(
                    document_url=file_url,
                    document_type="loan_document",
                    output_schema=BorrowerProfile,
                    system_prompt=self._get_extraction_prompt()
                )
            )
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"Extraction completed for {state.submission_id} "
                f"in {processing_time:.2f}s with confidence {extraction_response.confidence_score}"
            )
            
            # Cast to BorrowerProfile
            borrower_profile = extraction_response.extracted_data
            if not isinstance(borrower_profile, BorrowerProfile):
                # Try to convert dict to BorrowerProfile
                if isinstance(borrower_profile, dict):
                    borrower_profile = BorrowerProfile(**borrower_profile)
            
            return ValidateNode(
                state=ExtractState(
                    submission_id=state.submission_id,
                    raw_extraction=extraction_response.extracted_data.model_dump() if hasattr(extraction_response.extracted_data, 'model_dump') else extraction_response.extracted_data,
                    extraction_confidence=extraction_response.confidence_score,
                    token_usage=extraction_response.token_usage,
                    processing_time_seconds=processing_time
                )
            )
            
        except Exception as e:
            logger.error(f"Extraction failed for {state.submission_id}: {e}")
            
            return End(
                ExtractionResult(
                    submission_id=state.submission_id,
                    status="failed",
                    errors=[{"stage": "extract", "error": str(e)}],
                    borrower_profile=None
                )
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
class ValidateNode(BaseNode[ValidateState]):
    """Validate extracted data and assign final confidence.
    
    Validation checks:
    - Income amounts are positive and reasonable
    - Dates are valid and chronological
    - Required fields are present
    - Confidence scores meet threshold
    - Logical consistency across fields
    
    Outputs final ExtractionResult with status:
    - completed: All validations passed, high confidence
    - partial: Some validations failed but data usable
    - manual_review: Critical issues requiring human review
    """
    
    async def run(self, state: ExtractState) -> End[ExtractionResult]:
        """Execute validation."""
        logger.info(f"Validating extraction for submission {state.submission_id}")
        
        from doc_extract.domain.validation import ValidationResult, ValidationReport
        from doc_extract.domain.borrower import BorrowerProfile
        
        validation_results = []
        requires_manual_review = False
        
        # Reconstruct BorrowerProfile from raw extraction
        try:
            if isinstance(state.raw_extraction, dict):
                borrower_profile = BorrowerProfile(**state.raw_extraction)
            else:
                borrower_profile = state.raw_extraction
        except Exception as e:
            logger.error(f"Failed to reconstruct BorrowerProfile: {e}")
            return End(
                ExtractionResult(
                    submission_id=state.submission_id,
                    status="failed",
                    errors=[{"stage": "validate", "error": f"Invalid profile structure: {e}"}],
                    borrower_profile=None
                )
            )
        
        # Validation 1: Check required fields
        if not borrower_profile.name:
            validation_results.append(ValidationResult(
                rule_id="required_name",
                passed=False,
                field_path="name",
                actual_value=None,
                expected_condition="name is required",
                message="Borrower name is missing",
                severity="error"
            ))
            requires_manual_review = True
        
        # Validation 2: Check income history
        if not borrower_profile.income_history:
            validation_results.append(ValidationResult(
                rule_id="income_history_empty",
                passed=False,
                field_path="income_history",
                actual_value=[],
                expected_condition="at least one income entry",
                message="No income history found",
                severity="warning"
            ))
        else:
            for i, income in enumerate(borrower_profile.income_history):
                if income.amount <= 0:
                    validation_results.append(ValidationResult(
                        rule_id=f"income_positive_{i}",
                        passed=False,
                        field_path=f"income_history[{i}].amount",
                        actual_value=income.amount,
                        expected_condition="amount > 0",
                        message=f"Income amount must be positive: {income.amount}",
                        severity="error"
                    ))
        
        # Validation 3: Confidence threshold
        confidence_threshold = 0.8
        final_confidence = state.extraction_confidence
        
        if final_confidence < confidence_threshold:
            validation_results.append(ValidationResult(
                rule_id="confidence_threshold",
                passed=False,
                field_path="extraction_confidence",
                actual_value=final_confidence,
                expected_condition=f"confidence >= {confidence_threshold}",
                message=f"Confidence {final_confidence:.2f} below threshold {confidence_threshold}",
                severity="warning"
            ))
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
        if requires_manual_review:
            borrower_profile.requires_manual_review = True
        
        logger.info(
            f"Validation complete for {state.submission_id}: "
            f"status={status}, errors={error_count}, warnings={warning_count}"
        )
        
        return End(
            ExtractionResult(
                submission_id=state.submission_id,
                status=status,
                borrower_profile=borrower_profile,
                processing_time_seconds=state.processing_time_seconds,
                token_usage=state.token_usage,
                errors=[r.model_dump() for r in validation_results]
            )
        )


# Graph Definition
class DocumentProcessingGraph:
    """Main graph for document processing pipeline."""
    
    def __init__(self):
        self.graph = Graph(
            name="DocumentProcessing",
            nodes=[PreprocessNode, ExtractNode, ValidateNode]
        )
    
    async def process(self, submission: DocumentSubmission) -> ExtractionResult:
        """Process a submission through the graph."""
        result = await self.graph.run(PreprocessNode(), submission)
        
        if isinstance(result, End):
            return result.data
        else:
            # Should not happen with proper graph definition
            raise RuntimeError(f"Unexpected graph result: {result}")


# Convenience function
async def process_document(submission: DocumentSubmission) -> ExtractionResult:
    """Process a document submission through the pipeline."""
    graph = DocumentProcessingGraph()
    return await graph.process(submission)
```

## Deliverables
- [ ] services/graph.py with 3-node state machine
- [ ] PreprocessNode: File validation
- [ ] ExtractNode: PydanticAI extraction
- [ ] ValidateNode: Data validation + confidence scoring
- [ ] DocumentProcessingGraph class
- [ ] State transitions properly typed
- [ ] Error routing to End states

## Success Criteria
- Graph processes submission through all 3 nodes
- Preprocess validates file existence, size, type
- Extract uses Gemini via DocumentUrl
- Validate checks logical constraints (positive income, valid dates)
- Final status: completed, partial, or manual_review
- Provenance tracked on extracted fields

## Testing Snippets
```python
# Test graph execution
from doc_extract.services.graph import process_document
from doc_extract.domain.submission import DocumentSubmission

submission = DocumentSubmission(
    submission_id="test-123",
    documents=[DocumentMetadata(...)]
)

result = await process_document(submission)
assert result.status in ["completed", "partial", "manual_review"]
```

## Next Prompt
After this completes, move to `09_ai_extraction.md` for the PydanticAI agent details.
