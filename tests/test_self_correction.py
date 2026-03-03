"""Tests for self-correction loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from doc_extract.agents.critic_agent import (
    CriticAgent,
    CritiqueResult,
    FieldAssessment,
)
from doc_extract.services.processing import MAX_RETRIES, QA_THRESHOLD, ProcessingService

# -- CriticAgent unit tests --


class TestCriticAgentModels:
    """Test CritiqueResult and FieldAssessment models."""

    def test_field_assessment_correct(self):
        """Correct field assessment has is_correct=True."""
        a = FieldAssessment(field_name="name", is_correct=True)
        assert a.is_correct is True
        assert a.correct_value is None

    def test_field_assessment_incorrect(self):
        """Incorrect assessment carries correct_value."""
        a = FieldAssessment(
            field_name="name",
            is_correct=False,
            correct_value="Jane Doe",
            note="Name was misspelled",
        )
        assert a.is_correct is False
        assert a.correct_value == "Jane Doe"

    def test_critique_result_defaults(self):
        """CritiqueResult has sensible defaults."""
        r = CritiqueResult()
        assert r.overall_score == 0.0
        assert r.assessments == []
        assert r.feedback_notes == []

    def test_critique_result_with_assessments(self):
        """CritiqueResult computes from assessments."""
        r = CritiqueResult(
            assessments=[
                FieldAssessment(field_name="name", is_correct=True),
                FieldAssessment(field_name="address", is_correct=False),
            ],
            overall_score=50.0,
            feedback_notes=["address was wrong"],
        )
        assert r.overall_score == 50.0
        assert len(r.assessments) == 2


class TestCriticAgentInit:
    """Test CriticAgent initialization."""

    def test_default_llm(self):
        """Default init uses OpenAIAdapter."""
        agent = CriticAgent()
        from doc_extract.adapters.openai_adapter import OpenAIAdapter

        assert isinstance(agent.llm, OpenAIAdapter)

    def test_custom_llm(self):
        """Custom LLM adapter is used when provided."""
        mock_llm = MagicMock()
        agent = CriticAgent(llm_adapter=mock_llm)
        assert agent.llm is mock_llm


class TestCriticAgentCritique:
    """Test CriticAgent.critique() with mocked OpenAI."""

    @pytest.mark.asyncio
    async def test_critique_success(self):
        """Successful critique returns scored result."""
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 30

        critique_json = CritiqueResult(
            assessments=[
                FieldAssessment(field_name="name", is_correct=True),
                FieldAssessment(
                    field_name="address",
                    is_correct=False,
                    correct_value="456 Oak Ave",
                    note="Wrong street",
                ),
            ],
            overall_score=0.0,  # Will be recalculated
        ).model_dump_json()

        mock_message = MagicMock()
        mock_message.content = critique_json

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        agent = CriticAgent(llm_adapter=MagicMock())

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await agent.critique(
                document_url="file://test.pdf",
                extracted_data={"name": "John", "address": "123 Main St"},
            )

        assert isinstance(result, CritiqueResult)
        assert result.overall_score == 50.0  # 1 out of 2 correct
        assert len(result.feedback_notes) == 1
        assert "address" in result.feedback_notes[0]

    @pytest.mark.asyncio
    async def test_critique_with_feedback_history(self):
        """Critique includes previous feedback in the prompt."""
        critique_json = CritiqueResult(
            assessments=[
                FieldAssessment(field_name="name", is_correct=True),
            ],
        ).model_dump_json()

        mock_message = MagicMock()
        mock_message.content = critique_json
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        agent = CriticAgent(llm_adapter=MagicMock())

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await agent.critique(
                document_url="file://test.pdf",
                extracted_data={"name": "John"},
                feedback_history=["Name was wrong previously"],
            )

        assert result.overall_score == 100.0

        # Verify the feedback was included in the API call
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "PREVIOUS FEEDBACK" in user_msg
        assert "Name was wrong previously" in user_msg

    @pytest.mark.asyncio
    async def test_critique_failure_returns_passing(self):
        """On API error, critique returns passing result to avoid blocking."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("API down")
        )

        agent = CriticAgent(llm_adapter=MagicMock())

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await agent.critique(
                document_url="file://test.pdf",
                extracted_data={"name": "John"},
            )

        assert result.overall_score == 100.0
        assert any("failed" in note.lower() for note in result.feedback_notes)


# -- ProcessingService self-correction tests --


def _make_extraction_result(data_dict, confidence=0.85, time_seconds=1.0):
    """Helper to create a mock ExtractionResponse."""
    mock_result = MagicMock()
    mock_result.extracted_data = MagicMock()
    mock_result.extracted_data.model_dump.return_value = data_dict
    mock_result.confidence_score = confidence
    mock_result.processing_time_seconds = time_seconds
    mock_result.token_usage = {"prompt_tokens": 100, "completion_tokens": 50}
    return mock_result


class TestProcessingServiceSelfCorrection:
    """Test the self-correction loop in ProcessingService."""

    @pytest.mark.asyncio
    async def test_passes_on_first_attempt(self):
        """High QA score means no retry."""
        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock()

        extraction = _make_extraction_result({"name": "John", "address": "123 Main"})
        service.llm = MagicMock()
        service.llm.extract_structured = AsyncMock(return_value=extraction)

        high_score = CritiqueResult(
            assessments=[FieldAssessment(field_name="name", is_correct=True)],
            overall_score=95.0,
        )
        service.critic = MagicMock()
        service.critic.critique = AsyncMock(return_value=high_score)

        result = await service.process_submission("sub-1", "path/to/doc.pdf")

        assert result["status"] == "success"
        assert result["qa_score"] == 95.0
        assert result["retry_count"] == 0
        service.llm.extract_structured.assert_awaited_once()
        service.critic.critique.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_on_low_score(self):
        """Low QA score triggers retry with feedback."""
        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock()

        extraction = _make_extraction_result({"name": "John"})
        service.llm = MagicMock()
        service.llm.extract_structured = AsyncMock(return_value=extraction)

        low_score = CritiqueResult(
            assessments=[
                FieldAssessment(
                    field_name="name",
                    is_correct=False,
                    correct_value="Jane",
                    note="Wrong name",
                ),
            ],
            overall_score=0.0,
            feedback_notes=["Field 'name' was incorrect."],
        )
        high_score = CritiqueResult(
            assessments=[FieldAssessment(field_name="name", is_correct=True)],
            overall_score=95.0,
        )
        service.critic = MagicMock()
        service.critic.critique = AsyncMock(side_effect=[low_score, high_score])

        result = await service.process_submission("sub-1", "path/to/doc.pdf")

        assert result["status"] == "success"
        assert result["qa_score"] == 95.0
        assert result["retry_count"] == 1
        assert service.llm.extract_structured.await_count == 2
        assert service.critic.critique.await_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_respected(self):
        """After MAX_RETRIES, uses best result."""
        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock()

        extraction = _make_extraction_result({"name": "John"})
        service.llm = MagicMock()
        service.llm.extract_structured = AsyncMock(return_value=extraction)

        # Always returns low score
        low_score = CritiqueResult(
            assessments=[
                FieldAssessment(field_name="name", is_correct=False),
            ],
            overall_score=30.0,
            feedback_notes=["name is wrong"],
        )
        service.critic = MagicMock()
        service.critic.critique = AsyncMock(return_value=low_score)

        result = await service.process_submission("sub-1", "path/to/doc.pdf")

        assert result["status"] == "success"
        assert result["qa_score"] == 30.0
        assert result["retry_count"] == MAX_RETRIES
        # 1 initial + MAX_RETRIES retries
        assert service.llm.extract_structured.await_count == MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_best_result_kept_across_retries(self):
        """Best QA score result is returned even if later attempts are worse."""
        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock()

        # First extraction has better data
        good_extraction = _make_extraction_result({"name": "Jane"}, confidence=0.90)
        bad_extraction = _make_extraction_result({"name": "???"}, confidence=0.50)
        service.llm = MagicMock()
        service.llm.extract_structured = AsyncMock(
            side_effect=[good_extraction, bad_extraction, bad_extraction]
        )

        # Scores: 60 -> 20 -> 20 (first attempt is best)
        scores = [
            CritiqueResult(
                assessments=[FieldAssessment(field_name="name", is_correct=False)],
                overall_score=60.0,
                feedback_notes=["name is wrong"],
            ),
            CritiqueResult(
                assessments=[FieldAssessment(field_name="name", is_correct=False)],
                overall_score=20.0,
                feedback_notes=["name is still wrong"],
            ),
            CritiqueResult(
                assessments=[FieldAssessment(field_name="name", is_correct=False)],
                overall_score=20.0,
                feedback_notes=["name is still wrong"],
            ),
        ]
        service.critic = MagicMock()
        service.critic.critique = AsyncMock(side_effect=scores)

        result = await service.process_submission("sub-1", "path/to/doc.pdf")

        assert result["status"] == "success"
        assert result["qa_score"] == 60.0
        assert result["confidence"] == 0.90  # From the best extraction

    @pytest.mark.asyncio
    async def test_processing_failure_returns_error(self):
        """Exception during processing returns error dict."""
        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock(side_effect=FileNotFoundError("missing"))

        result = await service.process_submission("sub-1", "nonexistent.pdf")

        assert result["status"] == "failed"
        assert "missing" in result["error"]

    @pytest.mark.asyncio
    async def test_critique_metadata_in_response(self):
        """Response includes critique assessments and feedback history."""
        service = ProcessingService()
        service.storage = MagicMock()
        service.storage.download = AsyncMock()

        extraction = _make_extraction_result({"name": "John"})
        service.llm = MagicMock()
        service.llm.extract_structured = AsyncMock(return_value=extraction)

        critique = CritiqueResult(
            assessments=[
                FieldAssessment(field_name="name", is_correct=True, note="Looks good"),
            ],
            overall_score=100.0,
        )
        service.critic = MagicMock()
        service.critic.critique = AsyncMock(return_value=critique)

        result = await service.process_submission("sub-1", "path/to/doc.pdf")

        assert "critique" in result
        assert len(result["critique"]["assessments"]) == 1
        assert result["critique"]["assessments"][0]["field_name"] == "name"
        assert result["critique"]["feedback_history"] == []


class TestQAThresholdConfig:
    """Test that QA_THRESHOLD and MAX_RETRIES are configurable."""

    def test_qa_threshold_value(self):
        """QA threshold is set to 80%."""
        assert QA_THRESHOLD == 80.0

    def test_max_retries_value(self):
        """Max retries is set to 2."""
        assert MAX_RETRIES == 2
