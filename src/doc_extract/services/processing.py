"""Document processing service with self-correction loop.

Pipeline: Extract -> Critique -> (Retry if QA < threshold) -> Return
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

            EXTRACTION_REQUESTS.labels(status="success").inc()
            EXTRACTION_DURATION.labels(document_type="loan_application").observe(
                pipeline_time
            )
            ACTIVE_SUBMISSIONS.dec()

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
