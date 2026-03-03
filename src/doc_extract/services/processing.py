"""Document processing service with self-correction loop.

Pipeline: Extract -> Critique -> (Retry if QA < threshold) -> Return
Max retries: 2 (configurable)
QA threshold: 80% (configurable)

Inspired by the production graph at ~/projects/llm-service/src/llm_service/assistant/graph.py
where CritiqueNode loops back to ExtractionNode with feedback.

ADR Reference: docs/adr/020_multi_critic_panel.md
"""

import time
from pathlib import Path
from typing import cast

from doc_extract.adapters.local_storage import LocalFileSystemAdapter
from doc_extract.adapters.openai_adapter import OpenAIAdapter, SYSTEM_PROMPT
from doc_extract.agents.critic_agent import CriticAgent, CritiqueResult
from doc_extract.core.logging import logger
from doc_extract.core.prometheus import (
    ACTIVE_SUBMISSIONS,
    EXTRACTION_DURATION,
    EXTRACTION_REQUESTS,
    QA_SCORE,
    RETRY_COUNT,
)

# Configurable settings
QA_THRESHOLD = 80.0  # Score below which we retry
MAX_RETRIES = 2  # Maximum retry attempts

PLACEHOLDER_SOURCE_MARKERS = (
    "sample document",
    "demo purposes",
)

NON_INCOME_MARKERS = (
    "withheld",
    "withholding",
    "federal income tax",
    "social security tax",
    "medicare tax",
    "fica",
)


EXTRACTION_GUARDRAILS = """
Additional extraction guardrails:
- Populate provenance fields whenever a value is extracted (name/address/income/accounts).
- Populate source_documents with the actual document filename used.
- Do not classify taxes/withholdings/deductions as income (e.g., Medicare tax, SS tax, withholding).
- If a value cannot be verified in the document, leave it null/empty rather than guessing.
""".strip()


def _is_placeholder_source(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_SOURCE_MARKERS)


def _looks_like_non_income(label: str | None, evidence: str | None) -> bool:
    haystack = f"{label or ''} {evidence or ''}".lower()
    return any(marker in haystack for marker in NON_INCOME_MARKERS)


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
        ACTIVE_SUBMISSIONS.inc()

        try:
            # Download document content
            file_bytes = await self.storage.download(storage_path)

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
                        f"{SYSTEM_PROMPT}\n\n"
                        f"{EXTRACTION_GUARDRAILS}\n\n"
                        "IMPORTANT: Previous extraction had errors. "
                        "Please correct the following issues:\n"
                        f"{feedback_block}\n\n"
                        "Re-extract all fields carefully, paying special attention "
                        "to the fields mentioned above."
                    ).strip()
                else:
                    system_prompt = (
                        f"{SYSTEM_PROMPT}\n\n{EXTRACTION_GUARDRAILS}"
                    ).strip()

                request = ExtractionRequest(
                    document_url=document_url,
                    document_type="loan_application",
                    output_schema=BorrowerProfile,
                    system_prompt=system_prompt,
                    document_content=file_bytes,
                )

                # Step 1: Extract
                extraction_result = await self.llm.extract_structured(request)
                extracted_data = extraction_result.extracted_data.model_dump()

                # Step 2: Critique
                critique_result = await self.critic.critique(
                    document_url=document_url,
                    extracted_data=extracted_data,
                    feedback_history=feedback_history if feedback_history else None,
                    document_content=file_bytes,
                )

                qa_score = critique_result.overall_score
                QA_SCORE.observe(qa_score)

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
                    RETRY_COUNT.inc()
                else:
                    logger.warning(
                        f"Max retries ({MAX_RETRIES}) reached. "
                        f"Using best result (QA: {best_qa_score:.1f}%)"
                    )
                    break

            pipeline_time = time.time() - pipeline_start

            if best_result is None:
                raise RuntimeError("No extraction result produced")

            # Deterministic output hygiene to avoid placeholder provenance and
            # common misclassification of tax withholdings as income.
            profile = cast(BorrowerProfile, best_result.extracted_data)
            source_filename = Path(storage_path).name
            if "_" in source_filename:
                source_filename = source_filename.split("_", 1)[1]

            validation_notes: list[str] = []

            if not profile.source_documents or any(
                _is_placeholder_source(doc) for doc in profile.source_documents
            ):
                profile.source_documents = [source_filename]

            if profile.name and profile.name_provenance is None:
                validation_notes.append("Missing provenance for borrower name")
                profile.requires_manual_review = True

            if profile.address and profile.address_provenance is None:
                validation_notes.append("Missing provenance for borrower address")
                profile.requires_manual_review = True

            for prov in (profile.name_provenance, profile.address_provenance):
                if prov and _is_placeholder_source(prov.source_document):
                    prov.source_document = source_filename

            filtered_income = []
            removed_non_income = 0
            for income in profile.income_history:
                evidence = (
                    income.provenance.verbatim_text if income.provenance else None
                )
                if _looks_like_non_income(income.source, evidence):
                    removed_non_income += 1
                    continue

                if income.provenance and _is_placeholder_source(
                    income.provenance.source_document
                ):
                    income.provenance.source_document = source_filename

                filtered_income.append(income)

            if removed_non_income:
                validation_notes.append(
                    f"Removed {removed_non_income} withholding/tax entries from income_history"
                )
                profile.requires_manual_review = True

            profile.income_history = filtered_income

            for account in profile.accounts:
                if account.provenance and _is_placeholder_source(
                    account.provenance.source_document
                ):
                    account.provenance.source_document = source_filename

            for note in validation_notes:
                if note not in profile.validation_errors:
                    profile.validation_errors.append(note)

            profile.extraction_confidence = profile.calculate_overall_confidence()

            EXTRACTION_REQUESTS.labels(status="success").inc()
            EXTRACTION_DURATION.labels(document_type="loan_application").observe(
                pipeline_time
            )
            ACTIVE_SUBMISSIONS.dec()

            return {
                "status": "success",
                "data": profile.model_dump(),
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
            EXTRACTION_REQUESTS.labels(status="failed").inc()
            ACTIVE_SUBMISSIONS.dec()
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
