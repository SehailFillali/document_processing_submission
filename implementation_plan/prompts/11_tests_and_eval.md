# Prompt 11: Tests and Evaluation - Golden Set Framework

## Status
[PARTIALLY_IMPLEMENTED] - missing conftest.py, evaluation metrics, sample data directory

## Context
Implementing the Evaluation-Driven Development (EDD) framework with golden set testing.

## Objective
Create test framework and evaluation scripts for measuring extraction accuracy.

## Requirements

### 1. Create Test Directory Structure
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── integration/
│   ├── __init__.py
│   ├── test_api.py          # API endpoint tests
│   └── test_end_to_end.py   # Full pipeline tests
├── unit/
│   ├── __init__.py
│   ├── test_domain.py       # Domain model tests
│   ├── test_adapters.py     # Adapter unit tests
│   └── test_graph.py        # State machine tests
└── evaluation/
    ├── __init__.py
    ├── data/
    │   ├── sample_loan_1.pdf
    │   ├── sample_loan_1_ground_truth.json
    │   ├── sample_loan_2.pdf
    │   └── sample_loan_2_ground_truth.json
    ├── run_eval.py          # Evaluation script
    ├── metrics.py           # Precision/recall calculation
    └── report.py            # Results formatting
```

### 2. Create Conftest with Fixtures
File: `tests/conftest.py`

```python
"""Shared test fixtures and configuration."""
import pytest
import tempfile
import shutil
from pathlib import Path

from doc_extract.core.config import Settings
from doc_extract.adapters.local_storage import LocalFileSystemAdapter
from doc_extract.adapters.sqlite_db import SQLiteAdapter


@pytest.fixture
def temp_upload_dir():
    """Create temporary upload directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def local_storage(temp_upload_dir):
    """Create local storage adapter."""
    return LocalFileSystemAdapter(temp_upload_dir)


@pytest.fixture
def test_db():
    """Create test database."""
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    adapter = SQLiteAdapter(f"sqlite:///{temp_db.name}")
    yield adapter
    temp_db.close()
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
def sample_borrower_profile():
    """Sample borrower profile for testing."""
    from doc_extract.domain.borrower import (
        BorrowerProfile, Address, IncomeEntry, AccountInfo
    )
    from doc_extract.domain.base import Provenance
    
    return BorrowerProfile(
        borrower_id="test-123",
        name="John Doe",
        address=Address(
            street="123 Main St",
            city="San Francisco",
            state="CA",
            zip_code="94102"
        ),
        income_history=[
            IncomeEntry(
                amount=5000.0,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 1, 31),
                source="TechCorp Inc",
                provenance=Provenance(
                    source_document="loan.pdf",
                    source_page=2,
                    verbatim_text="Salary: $5,000",
                    confidence_score=0.95
                )
            )
        ],
        accounts=[
            AccountInfo(
                account_number="****1234",
                account_type="checking",
                institution="Chase Bank",
                provenance=Provenance(
                    source_document="loan.pdf",
                    source_page=3,
                    verbatim_text="Account: ****1234",
                    confidence_score=0.92
                )
            )
        ],
        source_documents=["loan.pdf"],
        extraction_confidence=0.93
    )


@pytest.fixture
def mock_gemini_adapter(monkeypatch):
    """Mock Gemini adapter for testing without API calls."""
    class MockGeminiAdapter:
        async def extract_structured(self, request):
            from doc_extract.ports.llm import ExtractionResponse
            from doc_extract.domain.borrower import BorrowerProfile
            from doc_extract.domain.base import Provenance
            
            # Return a mock profile
            profile = BorrowerProfile(
                borrower_id="mock-123",
                name="Jane Smith",
                address=None,  # Missing
                income_history=[],
                accounts=[],
                extraction_confidence=0.75
            )
            
            return ExtractionResponse(
                extracted_data=profile,
                token_usage={"input": 1000, "output": 500},
                confidence_score=0.75,
                processing_time_seconds=2.0,
                model_name="gemini-mock"
            )
        
        async def validate_connection(self):
            return True
    
    # Monkey patch
    import doc_extract.adapters.gemini_llm
    monkeypatch.setattr(
        doc_extract.adapters.gemini_llm,
        "GeminiAdapter",
        MockGeminiAdapter
    )
```

### 3. Create Evaluation Metrics
File: `tests/evaluation/metrics.py`

```python
"""Evaluation metrics for extraction accuracy."""
from typing import Any
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class FieldComparison:
    """Comparison result for a single field."""
    field_path: str
    expected: Any
    actual: Any
    match_type: str  # "exact", "partial", "missing", "extra"
    score: float  # 0.0 to 1.0


@dataclass
class ExtractionScore:
    """Overall extraction scores."""
    precision: float
    recall: float
    f1_score: float
    field_comparisons: list[FieldComparison]


def calculate_string_similarity(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, str(s1).lower(), str(s2).lower()).ratio()


def compare_borrower_profiles(
    expected: dict,
    actual: dict,
    field_weights: dict | None = None
) -> ExtractionScore:
    """Compare extracted profile against ground truth.
    
    Args:
        expected: Ground truth profile (dict)
        actual: Extracted profile (dict)
        field_weights: Optional weights for different fields
        
    Returns:
        ExtractionScore with precision, recall, F1
    """
    if field_weights is None:
        field_weights = {
            "name": 2.0,
            "address": 1.5,
            "ssn_last_four": 2.0,
            "income_history": 1.0,
            "accounts": 1.0
        }
    
    comparisons = []
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    
    # Compare name
    if "name" in expected or "name" in actual:
        name_score = calculate_string_similarity(
            expected.get("name", ""),
            actual.get("name", "")
        )
        comparisons.append(FieldComparison(
            field_path="name",
            expected=expected.get("name"),
            actual=actual.get("name"),
            match_type="exact" if name_score > 0.9 else "partial" if name_score > 0.5 else "missing",
            score=name_score
        ))
        
        weight = field_weights.get("name", 1.0)
        if name_score > 0.8:
            true_positives += weight
        elif actual.get("name"):
            false_positives += weight
        elif expected.get("name"):
            false_negatives += weight
    
    # Compare address fields
    expected_addr = expected.get("address", {})
    actual_addr = actual.get("address", {})
    
    for field in ["street", "city", "state", "zip_code"]:
        score = calculate_string_similarity(
            expected_addr.get(field, ""),
            actual_addr.get(field, "")
        )
        comparisons.append(FieldComparison(
            field_path=f"address.{field}",
            expected=expected_addr.get(field),
            actual=actual_addr.get(field),
            match_type="exact" if score > 0.9 else "partial" if score > 0.5 else "missing",
            score=score
        ))
    
    # Calculate metrics
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return ExtractionScore(
        precision=precision,
        recall=recall,
        f1_score=f1,
        field_comparisons=comparisons
    )


def format_score_report(score: ExtractionScore) -> str:
    """Format extraction score as readable report."""
    lines = [
        "=" * 60,
        "EXTRACTION EVALUATION REPORT",
        "=" * 60,
        f"Precision:  {score.precision:.2%}",
        f"Recall:     {score.recall:.2%}",
        f"F1 Score:   {score.f1_score:.2%}",
        "",
        "Field-by-Field Breakdown:",
        "-" * 60
    ]
    
    for comp in score.field_comparisons:
        status = "✓" if comp.score > 0.9 else "~" if comp.score > 0.5 else "✗"
        lines.append(
            f"{status} {comp.field_path:30s} "
            f"({comp.match_type:8s}) "
            f"Score: {comp.score:.2%}"
        )
    
    lines.append("=" * 60)
    return "\n".join(lines)
```

### 4. Create Evaluation Runner
File: `tests/evaluation/run_eval.py`

```python
#!/usr/bin/env python3
"""Evaluation runner - extracts from test documents and scores against ground truth.

Usage:
    just evaluate
    # or
    python -m tests.evaluation.run_eval

This script:
1. Loads test documents from tests/evaluation/data/
2. Runs extraction pipeline on each
3. Compares against ground truth JSON
4. Generates precision/recall report
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime

from doc_extract.services.extraction import ExtractionService
from tests.evaluation.metrics import compare_borrower_profiles, format_score_report


# Paths
EVAL_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"


async def run_evaluation():
    """Run full evaluation suite."""
    print("=" * 60)
    print("DOCUMENT EXTRACTION EVALUATION")
    print("=" * 60)
    
    # Ensure results directory exists
    RESULTS_DIR.mkdir(exist_ok=True)
    
    # Find all test cases
    pdf_files = list(EVAL_DIR.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No test PDFs found in {EVAL_DIR}")
        print("Add PDF files with corresponding _ground_truth.json files")
        return
    
    print(f"\nFound {len(pdf_files)} test documents\n")
    
    service = ExtractionService()
    all_scores = []
    
    for pdf_file in pdf_files:
        # Find ground truth
        ground_truth_file = pdf_file.with_suffix("_ground_truth.json")
        
        if not ground_truth_file.exists():
            print(f"⚠ Skipping {pdf_file.name} - no ground truth found")
            continue
        
        print(f"Processing: {pdf_file.name}")
        
        # Load ground truth
        with open(ground_truth_file) as f:
            ground_truth = json.load(f)
        
        # Run extraction
        file_url = f"file://{pdf_file.absolute()}"
        
        try:
            extracted_profile = await service.extract_borrower_profile(file_url)
            extracted_dict = extracted_profile.model_dump()
            
            # Compare
            score = compare_borrower_profiles(ground_truth, extracted_dict)
            all_scores.append(score)
            
            # Print results
            print(format_score_report(score))
            print()
            
        except Exception as e:
            print(f"✗ Error processing {pdf_file.name}: {e}\n")
    
    # Calculate aggregate scores
    if all_scores:
        avg_precision = sum(s.precision for s in all_scores) / len(all_scores)
        avg_recall = sum(s.recall for s in all_scores) / len(all_scores)
        avg_f1 = sum(s.f1_score for s in all_scores) / len(all_scores)
        
        print("=" * 60)
        print("AGGREGATE RESULTS")
        print("=" * 60)
        print(f"Documents Evaluated: {len(all_scores)}")
        print(f"Average Precision:   {avg_precision:.2%}")
        print(f"Average Recall:      {avg_recall:.2%}")
        print(f"Average F1 Score:    {avg_f1:.2%}")
        print("=" * 60)
        
        # Save results
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "documents_evaluated": len(all_scores),
            "aggregate_scores": {
                "precision": avg_precision,
                "recall": avg_recall,
                "f1_score": avg_f1
            },
            "individual_scores": [
                {
                    "precision": s.precision,
                    "recall": s.recall,
                    "f1_score": s.f1_score,
                    "fields": [
                        {"path": c.field_path, "score": c.score}
                        for c in s.field_comparisons
                    ]
                }
                for s in all_scores
            ]
        }
        
        results_file = RESULTS_DIR / f"eval_results_{datetime.utcnow():%Y%m%d_%H%M%S}.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"\nResults saved to: {results_file}")
        
        # Exit with error code if F1 < 0.8
        if avg_f1 < 0.8:
            print("\n⚠ WARNING: F1 score below 80% threshold")
            return 1
    else:
        print("No evaluations completed")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_evaluation())
    exit(exit_code)
```

### 5. Create Sample Ground Truth
File: `tests/evaluation/data/sample_loan_1_ground_truth.json`

```json
{
  "borrower_id": "sample-001",
  "name": "Robert Johnson",
  "ssn_last_four": "7890",
  "address": {
    "street": "456 Oak Avenue, Suite 100",
    "city": "Austin",
    "state": "TX",
    "zip_code": "78701",
    "country": "US"
  },
  "phone": "5125551234",
  "email": "robert.johnson@email.com",
  "income_history": [
    {
      "amount": 8500.00,
      "period_start": "2024-01-01",
      "period_end": "2024-01-31",
      "source": "TechCorp Solutions Inc"
    }
  ],
  "accounts": [
    {
      "account_number": "****4567",
      "account_type": "checking",
      "institution": "Bank of America",
      "current_balance": 12500.00
    }
  ]
}
```

## Deliverables
- [ ] tests/conftest.py with fixtures
- [ ] tests/evaluation/metrics.py with precision/recall/F1
- [ ] tests/evaluation/run_eval.py evaluation script
- [ ] tests/evaluation/data/ with sample ground truth
- [ ] just evaluate command in Justfile

## Success Criteria
- `just evaluate` runs successfully
- Precision, Recall, F1 calculated for each test document
- Field-by-field breakdown shows which fields match
- Aggregate scores across all test documents
- Results saved to JSON for tracking
- Exit code 1 if F1 < 80%

## Testing Snippets
```python
# Run evaluation
just evaluate

# Expected output:
# Documents Evaluated: 2
# Average Precision:   0.85
# Average Recall:      0.82
# Average F1 Score:    0.83
```

## Next Prompt
After this completes, move to `12_terraform_scaffold.md` for infrastructure scaffolding.
