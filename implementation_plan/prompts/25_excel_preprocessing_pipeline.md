# Prompt 25: Excel Preprocessing Pipeline

## Status
[POSTPONED] - not needed for provided sample PDFs

## Context

Real financial documents frequently arrive as Excel files (.xlsx, .xls) with formulas, hidden rows/columns, merged cells, forecast columns, and multi-year data. Our system currently only handles PDFs and JSON. The reference implementation at `~/projects/llm-service` solves this with an 8-step Excel-to-PDF pipeline that transforms raw Excel financial statements into clean, LLM-friendly PDFs. This prompt adapts that production-proven pipeline to our hexagonal architecture.

**Reference document:** `~/projects/llm-service/excel-preprocessing-pipeline.md`
**ADR:** `docs/adr/019_excel_preprocessing.md` (already exists, update status from "Proposed" to "Accepted")

## Objective

Add Excel file support through an 8-step preprocessing pipeline that converts Excel financial statements into clean PDFs before LLM extraction. The pipeline integrates with our existing `PreprocessNode` in the graph state machine and reuses the existing PDF extraction path.

## Requirements

### 1. Add Dependencies

In `pyproject.toml`, add to `dependencies`:

```toml
"openpyxl>=3.1.0",
"pandas>=2.0.0",
"python-dateutil>=2.8.0",
"Pillow>=10.0.0",
```

### 2. Create Preprocessing Configuration

**File:** `src/doc_extract/services/preprocessing_config.py`

This module centralizes all tunable parameters for the Excel preprocessing pipeline. Every threshold and keyword list is configurable in one place.

```python
"""Configuration for Excel preprocessing pipeline.

All thresholds and keywords are centralized here for easy tuning.
Reference: ~/projects/llm-service/excel-preprocessing-pipeline.md

ADR Reference: docs/adr/019_excel_preprocessing.md
"""

import re
from datetime import date

# ============================================================================
# FORECAST KEYWORDS
# Columns whose headers match these keywords (case-insensitive) are removed
# to prevent the LLM from extracting projected/budgeted values as actuals.
# ============================================================================
FORECAST_KEYWORDS = [
    "forecast",
    "budget",
    "projection",
    "plan",
    "goal",
    "target",
    "estimate",
    "projected",
    "planned",
    "estimated",
    "budgeted",
    "forecasted",
]

# ============================================================================
# THRESHOLDS
# ============================================================================
DESCRIPTION_COLUMN_TEXT_THRESHOLD = 0.6   # 60% text required to protect a column
EMPTY_COLUMN_THRESHOLD = 3                # Min non-empty cells to keep a column
INSIGNIFICANT_VALUE_THRESHOLD = 100       # Min absolute sum to keep a numeric column
MULTI_YEAR_THRESHOLD = 2                  # Min unique years before appending year to months

# ============================================================================
# PIPELINE SETTINGS
# ============================================================================
LIBREOFFICE_TIMEOUT = 300                 # Seconds per LibreOffice invocation
ENHANCED_PIPELINE_TIMEOUT = 1200          # Total timeout for full pipeline
MAX_ROWS_TO_SCAN = 100                    # Rows to scan for column analysis
MAX_HEADER_ROWS = 15                      # Rows to scan for forecast keywords
DESCRIPTION_COLUMN_RANGE = 5              # First N columns checked for description protection

# ============================================================================
# SUPPORTED EXTENSIONS
# ============================================================================
EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}
EXCEL_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
}

# ============================================================================
# DATE FILTERING
# ============================================================================
def get_date_cutoffs() -> tuple[date, date]:
    """Get date range to keep: prior year Jan 1 to start of next month.

    Example (Feb 25, 2026):
        cutoff_date = Jan 1, 2025  (keep 2025 onwards)
        future_date = Mar 1, 2026  (keep through Feb 2026)
    """
    today = date.today()
    prior_year = today.year - 1
    cutoff_date = date(prior_year, 1, 1)

    next_month = (today.month % 12) + 1
    next_month_year = today.year + (1 if next_month == 1 else 0)
    future_date = date(next_month_year, next_month, 1)

    return cutoff_date, future_date


# Pre-compiled patterns for date detection
YEAR_PATTERN = re.compile(r"202[0-9]")
MONTH_PATTERN = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", re.IGNORECASE
)
TOTAL_PATTERN = re.compile(r"^Total$", re.IGNORECASE)
MONTH_YEAR_PATTERN = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (202[0-9])",
    re.IGNORECASE,
)
```

### 3. Create Excel Preprocessing Module

**File:** `src/doc_extract/services/excel_preprocessing.py`

This is the core module. It implements the 8-step pipeline from the reference implementation, adapted to our architecture.

#### 3.1 Module structure and imports

```python
"""Excel preprocessing pipeline: 8-step Excel-to-PDF conversion.

Transforms raw Excel financial statements into clean, LLM-friendly PDFs.
Solves: formula evaluation, hidden data, forecast filtering, date ambiguity.

Pipeline:
    1. Pre-processing   (openpyxl)     - Unhide, unmerge, clear print areas
    2. Formula eval     (LibreOffice)  - Excel -> ODS, recalculate formulas
    3. Value extraction (pandas)       - ODS -> pure-value workbook
    4. Description protection          - Identify text-heavy columns
    5. Multi-year context              - Append year to standalone months
    6. Column/row removal              - Remove old dates, forecasts, empties
    7. Formatting                      - Round, auto-size, page setup
    8. PDF conversion   (LibreOffice)  - Final Excel -> PDF

Reference: ~/projects/llm-service/excel-preprocessing-pipeline.md
ADR Reference: docs/adr/019_excel_preprocessing.md
"""

import io
import os
import subprocess
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from doc_extract.core.logging import logger
from doc_extract.services.preprocessing_config import (
    DESCRIPTION_COLUMN_RANGE,
    DESCRIPTION_COLUMN_TEXT_THRESHOLD,
    EMPTY_COLUMN_THRESHOLD,
    EXCEL_EXTENSIONS,
    FORECAST_KEYWORDS,
    INSIGNIFICANT_VALUE_THRESHOLD,
    LIBREOFFICE_TIMEOUT,
    MAX_HEADER_ROWS,
    MAX_ROWS_TO_SCAN,
    MONTH_PATTERN,
    MULTI_YEAR_THRESHOLD,
    TOTAL_PATTERN,
    YEAR_PATTERN,
    get_date_cutoffs,
)
```

#### 3.2 Main entry point

```python
def convert_excel_to_pdf(excel_bytes: bytes, timeout: int = 300) -> bytes:
    """Convert Excel file to clean, LLM-friendly PDF via 8-step pipeline.

    Args:
        excel_bytes: Raw Excel file content.
        timeout: Seconds per LibreOffice invocation (default 300).

    Returns:
        PDF file content as bytes.

    Raises:
        ValueError: If file is password-protected or invalid.
        RuntimeError: If LibreOffice is not available or conversion fails.
        subprocess.TimeoutExpired: If LibreOffice exceeds timeout.
    """
    excel_size_mb = len(excel_bytes) / (1024 * 1024)
    pipeline_start = time.time()
    logger.info(f"[TIMING] Starting Excel to PDF conversion ({excel_size_mb:.2f} MB)")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Load workbook (detects password-protected files)
            try:
                wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
            except Exception as e:
                if "encrypted" in str(e).lower() or "password" in str(e).lower():
                    raise ValueError(
                        "Password-protected Excel files are not supported."
                    ) from e
                raise

            sheet_names = wb.sheetnames

            # Steps 1-7: Enhanced preprocessing
            t1 = time.time()
            preprocess_workbook(wb)
            logger.info(f"[TIMING] Step 1 (preprocess): {time.time() - t1:.2f}s")

            t2 = time.time()
            ods_path = evaluate_formulas(wb, tmpdir, timeout)
            logger.info(f"[TIMING] Step 2 (formula eval): {time.time() - t2:.2f}s")

            t3 = time.time()
            final_wb = extract_values(ods_path, sheet_names)
            logger.info(f"[TIMING] Step 3 (value extract): {time.time() - t3:.2f}s")

            t4 = time.time()
            for sheet in final_wb.worksheets:
                protected = protect_description_columns(sheet)
                add_year_context(sheet, protected)
                remove_unwanted_columns(sheet, protected)
                remove_empty_rows(sheet)
            logger.info(f"[TIMING] Steps 4-6 (cleanup): {time.time() - t4:.2f}s")

            t7 = time.time()
            format_workbook(final_wb)
            logger.info(f"[TIMING] Step 7 (formatting): {time.time() - t7:.2f}s")

        except (ValueError, RuntimeError):
            raise  # Re-raise password/LibreOffice errors
        except Exception as e:
            logger.warning(
                f"Enhanced preprocessing failed, falling back to original: {e}"
            )
            # Fallback: use original Excel file for PDF conversion
            final_wb = None
            fallback_path = os.path.join(tmpdir, "final.xlsx")
            with open(fallback_path, "wb") as f:
                f.write(excel_bytes)

        # Step 8: PDF conversion (always attempted)
        if final_wb is not None:
            final_path = os.path.join(tmpdir, "final.xlsx")
            final_wb.save(final_path)

        pdf_bytes = convert_to_pdf(
            os.path.join(tmpdir, "final.xlsx"), tmpdir, timeout
        )

        total_time = time.time() - pipeline_start
        pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
        logger.info(
            f"[TIMING] PDF created: {pdf_size_mb:.2f} MB "
            f"in {total_time:.2f}s total"
        )

        return pdf_bytes
```

#### 3.3 Step 1: Pre-processing (unhide, unmerge, clear print areas)

Implement `preprocess_workbook(wb)` following the reference implementation exactly:
- Clear print areas on all sheets
- Unhide all rows and columns
- Clear outline levels (grouped/collapsed sections)
- Unmerge all cells (preserve top-left value)

See reference: `excel-preprocessing-pipeline.md` Step 1 code example.

#### 3.4 Step 2: Formula evaluation via LibreOffice

Implement `evaluate_formulas(wb, tmpdir, timeout) -> str`:
- Save preprocessed workbook to `{tmpdir}/preprocessed.xlsx`
- Run `soffice --headless --convert-to ods --outdir {tmpdir} preprocessed.xlsx`
- Verify ODS file was created
- Return path to ODS file

**Critical:** Check for `soffice` availability first. If not found, raise `RuntimeError("LibreOffice (soffice) is not installed or not in PATH")`. This allows the calling code to fall back gracefully.

#### 3.5 Step 3: Value extraction (pandas + openpyxl)

Implement `extract_values(ods_path, sheet_names) -> openpyxl.Workbook`:
- Read each sheet from ODS with `pandas.read_excel(ods_path, sheet_name=name, header=None)`
- Create new openpyxl workbook with pure values (no formulas)
- Handle special cases:
  - `pd.Timestamp` / `datetime` / `date` → date string `YYYY-MM-DD`
  - `pd.isna(value)` → `None` (empty cell)

#### 3.6 Step 4: Description column protection

Implement `protect_description_columns(sheet) -> set[int]`:
- Check first `DESCRIPTION_COLUMN_RANGE` columns (default 5)
- Scan first `MAX_ROWS_TO_SCAN` rows (default 100)
- Skip empty cells and zeros
- Calculate `text_percentage = text_count / total_count`
- Protect column if `text_percentage >= DESCRIPTION_COLUMN_TEXT_THRESHOLD` (0.6)
- Return set of protected column indices

#### 3.7 Step 5: Multi-year context

Implement `add_year_context(sheet, protected_cols)`:
- Scan first 10 rows for years (2020-2029) using `YEAR_PATTERN`
- Skip if `< MULTI_YEAR_THRESHOLD` unique years found
- Scan column-by-column, top-to-bottom, tracking `current_year`
- Append year to standalone months: `"Jan"` → `"Jan 2025"`
- Append year to standalone `"Total"`: `"Total"` → `"Total 2025"`

#### 3.8 Step 6: Column and row removal

Implement `remove_unwanted_columns(sheet, protected_cols)` and `remove_empty_rows(sheet)`:

**CRITICAL: Index shifting prevention.** Collect ALL column indices to delete across all four sub-steps, subtract protected columns, then delete in **reverse sorted order** in a single pass.

Sub-steps (all check `protected_cols` before deletion):
1. **Prior year columns** — Remove columns with dates before `cutoff_date` (Jan 1 of prior year) or after `future_date` (start of next month). Check all rows for `date` objects and date strings using `MONTH_YEAR_PATTERN`.
2. **Forecast columns** — Remove columns where any cell in the first `MAX_HEADER_ROWS` rows matches a `FORECAST_KEYWORDS` entry (case-insensitive substring match).
3. **Empty columns** — Remove columns with fewer than `EMPTY_COLUMN_THRESHOLD` non-empty cells in the first `MAX_ROWS_TO_SCAN` rows.
4. **Insignificant value columns** — Remove numeric columns where `abs(sum) < INSIGNIFICANT_VALUE_THRESHOLD`. Skip text-heavy columns (more text cells than numeric cells). Skip columns with sum = 0.

Then `remove_empty_rows(sheet)`:
- Delete rows where ALL cells are empty
- Delete **bottom-to-top** to prevent index shifting

```python
# Correct deletion pattern:
all_cols_to_delete = set()
all_cols_to_delete.update(prior_year_cols)
all_cols_to_delete.update(forecast_cols)
all_cols_to_delete.update(empty_cols)
all_cols_to_delete.update(insignificant_cols)

# Never delete protected columns
all_cols_to_delete -= protected_cols

# Delete in reverse order to prevent index shifting
for col_idx in sorted(all_cols_to_delete, reverse=True):
    sheet.delete_cols(col_idx)
```

#### 3.9 Step 7: Formatting

Implement `format_workbook(wb)`:
- **Percentages** (values between -1 and 1, excluding 0) → set to `0` (prevents LLM interpreting 0.53 as $530K)
- **Decimals** → round to 2 decimal places
- **Text** → strip leading/trailing whitespace
- **Column widths** → auto-size based on content (first `MAX_ROWS_TO_SCAN` rows), min width 10
- **Cell alignment** → horizontal `left`, vertical `top`, no wrapping
- **Page setup** → landscape, Letter paper, `fitToPage=True`, `fitToWidth=1`, `fitToHeight=0`
- **Margins** → 0.25" all sides

#### 3.10 Step 8: PDF conversion

Implement `convert_to_pdf(xlsx_path, tmpdir, timeout) -> bytes`:
- Run `soffice --headless --convert-to pdf:calc_pdf_Export --outdir {tmpdir} {xlsx_path}`
- Check for password/encrypted error in stderr
- Verify PDF file was created
- Read and return PDF bytes

### 4. Create Preprocessing Port

**File:** Add to `src/doc_extract/ports/preprocessing.py`

```python
"""Preprocessing port - abstraction for document format conversion."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PreprocessingResult:
    """Result of document preprocessing."""

    converted_bytes: bytes
    original_format: str
    converted_format: str
    steps_applied: list[str]
    processing_time_seconds: float
    warnings: list[str]


class PreprocessingPort(ABC):
    """Port for document preprocessing/format conversion.

    Implementations:
        - ExcelPreprocessor: Excel -> PDF via 8-step pipeline
        - (Future) ImagePreprocessor: Image -> PDF via Pillow
    """

    @abstractmethod
    def is_applicable(self, file_name: str, mime_type: str) -> bool:
        """Check if this preprocessor handles the given file type."""
        pass

    @abstractmethod
    def preprocess(self, file_bytes: bytes, file_name: str) -> PreprocessingResult:
        """Convert file to LLM-friendly format.

        Args:
            file_bytes: Raw file content.
            file_name: Original file name (for extension detection).

        Returns:
            PreprocessingResult with converted bytes and metadata.

        Raises:
            ValueError: If file is invalid (password-protected, corrupted).
            RuntimeError: If external dependencies are missing.
        """
        pass
```

### 5. Create Excel Preprocessor Adapter

**File:** `src/doc_extract/adapters/excel_preprocessor.py`

```python
"""Excel preprocessor adapter implementing PreprocessingPort."""

import time
from pathlib import Path

from doc_extract.ports.preprocessing import PreprocessingPort, PreprocessingResult
from doc_extract.services.excel_preprocessing import convert_excel_to_pdf
from doc_extract.services.preprocessing_config import (
    EXCEL_EXTENSIONS,
    EXCEL_MIME_TYPES,
    ENHANCED_PIPELINE_TIMEOUT,
)


class ExcelPreprocessor(PreprocessingPort):
    """Converts Excel files to clean PDFs via the 8-step pipeline."""

    def is_applicable(self, file_name: str, mime_type: str) -> bool:
        ext = Path(file_name).suffix.lower()
        return ext in EXCEL_EXTENSIONS or mime_type in EXCEL_MIME_TYPES

    def preprocess(self, file_bytes: bytes, file_name: str) -> PreprocessingResult:
        start = time.time()
        pdf_bytes = convert_excel_to_pdf(
            file_bytes, timeout=ENHANCED_PIPELINE_TIMEOUT
        )
        return PreprocessingResult(
            converted_bytes=pdf_bytes,
            original_format=Path(file_name).suffix.lower(),
            converted_format=".pdf",
            steps_applied=[
                "preprocess_workbook",
                "evaluate_formulas",
                "extract_values",
                "protect_description_columns",
                "add_year_context",
                "remove_unwanted_columns",
                "format_workbook",
                "convert_to_pdf",
            ],
            processing_time_seconds=time.time() - start,
            warnings=[],
        )
```

### 6. Integrate with Graph PreprocessNode

**File:** Modify `src/doc_extract/services/graph.py`

In `PreprocessNode.run()`, after the existing file validation checks and before returning `ExtractNode`, add Excel detection and conversion:

```python
# In PreprocessNode.run(), after metadata validation passes:

from doc_extract.adapters.excel_preprocessor import ExcelPreprocessor
from doc_extract.services.preprocessing_config import EXCEL_EXTENSIONS

for i, doc_path in enumerate(state.document_paths):
    ext = Path(doc_path).suffix.lower()
    if ext in EXCEL_EXTENSIONS:
        logger.info(f"Excel file detected: {doc_path}. Running preprocessing.")
        try:
            preprocessor = ExcelPreprocessor()
            file_bytes = await storage.download(doc_path)
            result = preprocessor.preprocess(file_bytes, doc_path)

            # Upload converted PDF alongside original
            pdf_path = doc_path.rsplit(".", 1)[0] + "_converted.pdf"
            from io import BytesIO
            await storage.upload(
                BytesIO(result.converted_bytes),
                pdf_path,
                content_type="application/pdf",
            )

            # Replace the document path with the converted PDF
            state.document_paths[i] = pdf_path
            state.metadata["excel_preprocessing"] = {
                "original_file": doc_path,
                "converted_file": pdf_path,
                "steps_applied": result.steps_applied,
                "processing_time": result.processing_time_seconds,
            }
            logger.info(
                f"Excel preprocessing complete: {doc_path} -> {pdf_path} "
                f"({result.processing_time_seconds:.2f}s)"
            )
        except ValueError as e:
            # Password-protected or invalid file
            errors.append(f"Excel preprocessing failed for {doc_path}: {e}")
        except RuntimeError as e:
            # LibreOffice not available — log warning but continue with raw file
            logger.warning(
                f"LibreOffice not available, skipping Excel preprocessing: {e}"
            )
```

### 7. Integrate with API Upload Endpoint

**File:** Modify `src/doc_extract/api/main.py`

Update the `upload_document` endpoint to accept Excel files. The current endpoint accepts any file -- the preprocessing happens in the graph. But we should update the `DocumentType` validation to recognize Excel MIME types, and the Swagger docs should mention Excel support.

Add to the upload endpoint's docstring:
```python
"""Upload a document for processing.

Supported formats:
    - PDF (.pdf)
    - Excel (.xlsx, .xls, .xlsm) -- automatically converted to PDF
    - JSON (.json)
"""
```

### 8. Update Dockerfile

**File:** Modify `Dockerfile`

Add LibreOffice to the Docker image. This adds ~200MB but is required for formula evaluation and PDF conversion.

```dockerfile
FROM python:3.11-slim-bookworm AS build

SHELL ["/bin/sh", "-exc"]

# Install LibreOffice (headless) for Excel preprocessing
RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice-calc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# ... rest of Dockerfile unchanged
```

**Note:** Use `libreoffice-calc` (not full `libreoffice`) to minimize image size. This installs only the Calc component needed for Excel processing.

### 9. Add Tests

**File:** `tests/test_excel_preprocessing.py`

```python
"""Tests for Excel preprocessing pipeline.

Tests cover:
- File type detection (Excel vs non-Excel)
- Password-protected file rejection
- Graceful fallback on preprocessing failure
- LibreOffice availability check
- Configuration values
- Column protection logic
- Date filtering logic
- Forecast keyword detection
- Multi-year context appending
- Index shifting prevention in column deletion
"""
```

#### Test cases to implement:

1. **`test_is_applicable_detects_excel_files`** — `ExcelPreprocessor.is_applicable()` returns True for `.xlsx`, `.xls`, `.xlsm` and Excel MIME types.

2. **`test_is_applicable_rejects_non_excel`** — Returns False for `.pdf`, `.json`, `.txt`, `application/pdf`.

3. **`test_password_protected_raises_valueerror`** — `convert_excel_to_pdf()` raises `ValueError` with "password" in the message when given an encrypted file. (Mock `openpyxl.load_workbook` to raise with "encrypted" in the error message.)

4. **`test_preprocess_workbook_unhides_rows`** — Create an openpyxl workbook with hidden rows, run `preprocess_workbook()`, verify all rows are unhidden.

5. **`test_preprocess_workbook_unmerges_cells`** — Create workbook with merged cells, run `preprocess_workbook()`, verify cells are unmerged and top-left value preserved.

6. **`test_preprocess_workbook_clears_print_areas`** — Create workbook with print area set, verify it's cleared after preprocessing.

7. **`test_protect_description_columns_identifies_text_columns`** — Create a sheet with column A = 80% text, column B = 100% numeric. Verify A is protected, B is not.

8. **`test_protect_description_columns_skips_empty_and_zero`** — Empty cells and zero values are excluded from the text percentage calculation.

9. **`test_add_year_context_appends_year_to_months`** — Create a sheet with `2022, Jan, Feb, 2023, Jan, Feb`. Verify output is `2022, Jan 2022, Feb 2022, 2023, Jan 2023, Feb 2023`.

10. **`test_add_year_context_skips_single_year`** — If only one year is found, no changes are made (threshold = 2).

11. **`test_remove_unwanted_columns_deletes_forecast`** — Create sheet with header "Budget Q1". Verify column is deleted.

12. **`test_remove_unwanted_columns_preserves_protected`** — Create sheet where a forecast column overlaps with a protected description column. Verify it is NOT deleted.

13. **`test_remove_unwanted_columns_reverse_deletion_order`** — Create sheet with 3 columns to delete at indices 2, 5, 8. Verify deletion happens in reverse (8, 5, 2) so indices don't shift.

14. **`test_format_workbook_zeroes_percentages`** — Cell with value `0.53` becomes `0`. Cell with value `1234.56789` becomes `1234.57`. Cell with value `0` stays `0`.

15. **`test_format_workbook_page_setup`** — After formatting, verify landscape orientation, fitToPage=True, fitToWidth=1, margins=0.25.

16. **`test_date_cutoffs_current_year`** — Mock `date.today()` to `2026-02-25`. Verify `cutoff_date = 2025-01-01` and `future_date = 2026-03-01`.

17. **`test_graceful_fallback_on_error`** — Mock `preprocess_workbook` to raise an exception. Verify `convert_excel_to_pdf` still attempts PDF conversion using the original file (the `except` branch in the main entry point).

18. **`test_libreoffice_not_found`** — Mock `subprocess.run` to raise `FileNotFoundError`. Verify a `RuntimeError` is raised with a message about LibreOffice not being installed.

19. **`test_config_values`** — Verify `FORECAST_KEYWORDS` contains at least the core 6: forecast, budget, projection, plan, goal, target.

20. **`test_preprocessing_result_dataclass`** — Verify `PreprocessingResult` fields are populated correctly.

**Test structure:** All tests that involve LibreOffice subprocess calls should mock `subprocess.run`. All tests that involve openpyxl workbook manipulation should create real in-memory workbooks with `openpyxl.Workbook()`. No tests should require actual files on disk or LibreOffice to be installed.

### 10. Add Prometheus Metrics

**File:** Add to `src/doc_extract/core/prometheus.py`

```python
# --- Excel Preprocessing Metrics ---

EXCEL_PREPROCESSING_DURATION = Histogram(
    "excel_preprocessing_duration_seconds",
    "Time spent on Excel preprocessing pipeline",
    buckets=[1, 5, 10, 15, 30, 60, 120, 300],
)

EXCEL_PREPROCESSING_REQUESTS = Counter(
    "excel_preprocessing_total",
    "Total Excel preprocessing attempts",
    ["status"],  # success, failed, fallback
)

EXCEL_COLUMNS_REMOVED = Counter(
    "excel_columns_removed_total",
    "Total columns removed during preprocessing",
    ["reason"],  # prior_year, forecast, empty, insignificant
)
```

Instrument the pipeline in `excel_preprocessing.py`:
- Record `EXCEL_PREPROCESSING_DURATION` at the end of `convert_excel_to_pdf()`
- Increment `EXCEL_PREPROCESSING_REQUESTS` with `status=success|failed|fallback`
- Increment `EXCEL_COLUMNS_REMOVED` in `remove_unwanted_columns()` for each deletion reason

### 11. Update Documentation

#### 11.1 Update ADR 019

**File:** `docs/adr/019_excel_preprocessing.md`

Change status from `Proposed` to `Accepted`. Add implementation references:
- `src/doc_extract/services/excel_preprocessing.py`
- `src/doc_extract/services/preprocessing_config.py`
- `src/doc_extract/ports/preprocessing.py`
- `src/doc_extract/adapters/excel_preprocessor.py`
- `tests/test_excel_preprocessing.py`

#### 11.2 Update README.md

Add `.xlsx`, `.xls`, `.xlsm` to the supported formats in:
- The Quick Start section's upload example
- The API Endpoints table description for `/api/v1/documents/upload`

#### 11.3 Update SYSTEM_DESIGN.md

Add a new subsection under "2. Data Pipeline" describing the Excel preprocessing pipeline with the 8-step flow diagram.

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add openpyxl, pandas, python-dateutil, Pillow |
| `services/preprocessing_config.py` | Create | All thresholds, keywords, date logic |
| `services/excel_preprocessing.py` | Create | 8-step pipeline (~350-450 lines) |
| `ports/preprocessing.py` | Create | PreprocessingPort + PreprocessingResult |
| `adapters/excel_preprocessor.py` | Create | ExcelPreprocessor adapter |
| `services/graph.py` | Modify | Add Excel detection in PreprocessNode |
| `api/main.py` | Modify | Update docstring for Excel support |
| `Dockerfile` | Modify | Add libreoffice-calc |
| `tests/test_excel_preprocessing.py` | Create | 20 test cases (~400-500 lines) |
| `core/prometheus.py` | Modify | Add 3 Excel preprocessing metrics |
| `docs/adr/019_excel_preprocessing.md` | Modify | Status: Proposed -> Accepted |
| `README.md` | Modify | Add Excel to supported formats |
| `SYSTEM_DESIGN.md` | Modify | Add preprocessing pipeline section |

## Verification

```bash
# All existing tests must still pass
just test

# New Excel preprocessing tests pass
uv run pytest tests/test_excel_preprocessing.py -v

# Verify LibreOffice available in Docker
docker build -t doc-extract:latest .
docker run --rm doc-extract:latest soffice --version

# Verify no regressions
uv run pytest tests/ -q
```

## Constraints

- **NO REGRESSION** — All 236 existing tests must continue to pass
- **Graceful degradation** — If LibreOffice is not installed, the system must still work for PDF files. Excel upload should fail with a clear error, not crash.
- **Hexagonal architecture** — Excel preprocessing goes through the `PreprocessingPort`, not hardcoded in the graph or API
- **Configuration centralized** — All thresholds in `preprocessing_config.py`, not scattered across the pipeline
- **Index shifting** — Column deletion MUST use the reverse-sorted single-pass pattern. This is a known bug source (see reference implementation git history: `8031f6b fix: prevent column index shifting`)
- **Temporary files** — All temp files in `tempfile.TemporaryDirectory()` context manager. No leaked temp files.
- **No new system dependency for tests** — Tests must mock subprocess/LibreOffice calls. CI should not require LibreOffice installed.
