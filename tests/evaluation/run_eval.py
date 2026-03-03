"""Evaluation framework for document extraction.

This module provides tools to measure extraction quality:
- Golden set evaluation
- Precision/Recall metrics
- Confidence calibration
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from doc_extract.core.logging import logger
from doc_extract.domain.borrower import BorrowerProfile


@dataclass
class EvaluationResult:
    """Result of evaluating a single extraction."""

    document_id: str
    expected: dict
    actual: dict
    field_scores: dict = field(default_factory=dict)
    overall_score: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0


@dataclass
class EvaluationSummary:
    """Summary of evaluation across all documents."""

    total_documents: int
    average_precision: float
    average_recall: float
    average_f1: float
    field_metrics: dict
    results: list[EvaluationResult]


class GoldenSetEvaluator:
    """Evaluate extraction against golden set of labeled documents."""

    def __init__(self, golden_set_path: str):
        """Initialize with path to golden set JSON."""
        self.golden_set_path = Path(golden_set_path)
        self.golden_data = self._load_golden_set()

    def _load_golden_set(self) -> dict:
        """Load golden set from JSON file."""
        if not self.golden_set_path.exists():
            logger.warning(f"Golden set not found: {self.golden_set_path}")
            return {}

        with open(self.golden_set_path) as f:
            return json.load(f)

    def evaluate_extraction(
        self, document_id: str, extracted_profile: BorrowerProfile
    ) -> EvaluationResult:
        """Evaluate a single extraction against golden data."""
        expected = self.golden_data.get(document_id, {})
        actual = (
            extracted_profile.model_dump()
            if hasattr(extracted_profile, "model_dump")
            else extracted_profile
        )

        # Calculate field-level scores
        field_scores = {}
        for field_name in expected:
            expected_val = expected[field_name]
            actual_val = actual.get(field_name)

            if expected_val is None and actual_val is None:
                score = 1.0
            elif expected_val is None or actual_val is None:
                score = 0.0
            elif expected_val == actual_val:
                score = 1.0
            else:
                score = self._calculate_similarity(expected_val, actual_val)

            field_scores[field_name] = score

        # Calculate overall metrics
        overall_score = (
            sum(field_scores.values()) / len(field_scores) if field_scores else 0.0
        )

        # Precision: How many extracted fields are correct?
        correct = sum(1 for s in field_scores.values() if s >= 0.8)
        precision = correct / len(field_scores) if field_scores else 0.0

        # Recall: How many expected fields were extracted?
        recall = correct / len(expected) if expected else 0.0

        # F1 Score
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return EvaluationResult(
            document_id=document_id,
            expected=expected,
            actual=actual,
            field_scores=field_scores,
            overall_score=overall_score,
            precision=precision,
            recall=recall,
            f1_score=f1,
        )

    def _calculate_similarity(self, expected: Any, actual: Any) -> float:
        """Calculate similarity between expected and actual values."""
        if isinstance(expected, dict) and isinstance(actual, dict):
            # For nested dicts, compare keys
            expected_keys = set(expected.keys())
            actual_keys = set(actual.keys())
            if expected_keys == actual_keys:
                return 1.0
            intersection = len(expected_keys & actual_keys)
            return intersection / len(expected_keys | actual_keys)

        if isinstance(expected, list) and isinstance(actual, list):
            # For lists, check overlap
            if not expected:
                return 1.0 if not actual else 0.0
            matches = sum(1 for e in expected if e in actual)
            return matches / max(len(expected), len(actual))

        # Simple equality
        return 1.0 if expected == actual else 0.0

    def evaluate_batch(
        self, extractions: dict[str, BorrowerProfile]
    ) -> EvaluationSummary:
        """Evaluate multiple extractions."""
        results = []

        for doc_id, profile in extractions.items():
            result = self.evaluate_extraction(doc_id, profile)
            results.append(result)

        # Aggregate metrics
        avg_precision = (
            sum(r.precision for r in results) / len(results) if results else 0.0
        )
        avg_recall = sum(r.recall for r in results) / len(results) if results else 0.0
        avg_f1 = sum(r.f1_score for r in results) / len(results) if results else 0.0

        # Field-level metrics
        field_metrics = {}
        if results and results[0].field_scores:
            for field_name in results[0].field_scores:
                scores = [r.field_scores.get(field_name, 0.0) for r in results]
                field_metrics[field_name] = {
                    "mean": sum(scores) / len(scores),
                    "min": min(scores),
                    "max": max(scores),
                }

        return EvaluationSummary(
            total_documents=len(results),
            average_precision=avg_precision,
            average_recall=avg_recall,
            average_f1=avg_f1,
            field_metrics=field_metrics,
            results=results,
        )


def run_evaluation(
    golden_set_path: str, output_path: str | None = None
) -> EvaluationSummary:
    """Run evaluation and optionally save results."""
    evaluator = GoldenSetEvaluator(golden_set_path)

    logger.info(f"Loaded golden set with {len(evaluator.golden_data)} documents")

    # This would be populated from actual extractions
    # For now, return empty summary
    summary = EvaluationSummary(
        total_documents=0,
        average_precision=0.0,
        average_recall=0.0,
        average_f1=0.0,
        field_metrics={},
        results=[],
    )

    if output_path:
        output_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "total_documents": summary.total_documents,
                "average_precision": summary.average_precision,
                "average_recall": summary.average_recall,
                "average_f1": summary.average_f1,
                "field_metrics": summary.field_metrics,
            },
        }
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Evaluation results saved to {output_path}")

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run extraction evaluation")
    parser.add_argument("--golden-set", required=True, help="Path to golden set JSON")
    parser.add_argument("--output", help="Path to save results JSON")
    args = parser.parse_args()

    run_evaluation(args.golden_set, args.output)
