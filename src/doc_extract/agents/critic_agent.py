"""Critic agent for validating extractions against source documents.

Inspired by the production "Panel of Critics" pattern from llm-service.
Uses the same LLM to verify that extracted fields match the source document.

ADR Reference: docs/adr/020_multi_critic_panel.md
"""

import base64
import json
import os
import time
from typing import Any

from pydantic import BaseModel, Field

from doc_extract.core.logging import logger


class FieldAssessment(BaseModel):
    """Assessment of a single extracted field."""

    field_name: str = Field(..., description="Name of the field being assessed")
    is_correct: bool = Field(..., description="True if extracted value matches source")
    correct_value: Any = Field(
        None, description="Correct value if extraction was wrong"
    )
    note: str | None = Field(
        None, description="Explanation of why the field is correct/incorrect"
    )


class CritiqueResult(BaseModel):
    """Result from the Critic agent."""

    assessments: list[FieldAssessment] = Field(default_factory=list)
    overall_score: float = Field(
        0.0, description="Percentage of fields marked correct (0-100)"
    )
    feedback_notes: list[str] = Field(
        default_factory=list, description="Feedback for re-extraction"
    )


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
        self.model_name = os.environ.get("OPENAI_CRITIC_MODEL", "gpt-4o")
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
        document_content: bytes | None = None,
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

        text_message = (
            f"Extracted data to verify:\n"
            f"{json.dumps(extracted_data, indent=2, default=str)}"
            f"{feedback_context}"
        )

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

            # Build user content: include PDF file block when available
            if document_content:
                b64_data = base64.b64encode(document_content).decode()
                filename = (
                    document_url.split("/")[-1]
                    if "/" in document_url
                    else "document.pdf"
                )
                user_content: str | list = [
                    {
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": f"data:application/pdf;base64,{b64_data}",
                        },
                    },
                    {
                        "type": "text",
                        "text": text_message,
                    },
                ]
            else:
                # Fallback: send document_url as text (existing behavior)
                user_content = f"Source document: {document_url}\n\n{text_message}"

            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": CRITIQUE_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "CritiqueResult",
                        "schema": CritiqueResult.model_json_schema(),
                    },
                },
            )

            raw_content = response.choices[0].message.content
            if raw_content is None:
                raise ValueError("Critique response content is empty")

            result = CritiqueResult.model_validate_json(raw_content)

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
                f"({sum(1 for a in result.assessments if a.is_correct)}"
                f"/{len(result.assessments)} correct)"
            )

            return result

        except Exception as e:
            logger.error(f"Critique failed: {e}")
            # On critique failure, return a passing result to avoid blocking
            return CritiqueResult(
                overall_score=100.0,
                feedback_notes=[f"Critique agent failed: {e}. Passing by default."],
            )
