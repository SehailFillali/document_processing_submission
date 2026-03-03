# ADR 019: Excel-to-PDF Preprocessing (Future)

## Status
**Proposed** - 2026-03-02 (Not yet implemented)

## Context
Real financial documents frequently arrive as Excel files (.xlsx, .xls) with formulas, hidden columns, restrictive print areas, and forecast data that shouldn't be extracted. The reference implementation at ~/projects/llm-service handles this with LibreOffice headless conversion.

## Purpose
Enable processing of Excel documents alongside PDFs, which is critical for real-world loan document processing.

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| **LibreOffice headless (Planned)** | Calculates formulas, renders to PDF | Requires LibreOffice in container |
| openpyxl text extraction | Pure Python, no system deps | Loses formatting, can't calculate formulas |
| pandas read_excel | Good for tabular data | Loses document structure |
| Cloud-based conversion (Google Docs API) | No local deps | Latency, cost, external dependency |

## Planned Approach

1. **Pre-process with openpyxl**: Clear print areas, remove forecast columns, force black text
2. **Convert with LibreOffice**: Calculate formulas, export to PDF
3. **Upload converted PDF**: Store as artifact, process through existing pipeline

### Key Features from Reference Implementation

- **Forecast column detection and removal**: Keywords: forecast, projection, budget, plan. Scans header rows (1-15) and removes matching columns to prevent the LLM from extracting projected (non-actual) values
- **Print area clearing**: Many Excel files have restrictive print areas that hide data columns. Clearing them ensures all data is visible in the PDF output
- **Black text forcing**: Forces all cell text to black (`#000000`) for LLM readability. Removes light grey/colored text that may be invisible in PDF
- **Password-protected file detection**: Rejects encrypted files early with a clear error message rather than failing silently downstream
- **LibreOffice formula calculation**: The key advantage over pure-Python approaches — LibreOffice actually evaluates formulas during conversion, so computed financial totals appear correctly in the PDF

### Preprocessing Pipeline Pattern

```python
class Preprocessor:
    """Pipeline of registered validation/transformation steps."""
    def __init__(self):
        self._validators = []

    def register(self, func):
        self._validators.append(func)

    def __call__(self, payload) -> ProcessingPayload:
        current = payload
        for func in self._validators:
            result = func(current)
            if result is not None:  # Transformation
                current = result
            # else: validation-only (raises on failure)
        return current
```

This pattern cleanly separates validation (raise on failure) from transformation (return modified payload).

## Conclusion
LibreOffice headless is the correct approach because it calculates Excel formulas (critical for financial data) and produces a PDF that the existing LLM pipeline can process without changes. The preprocessing pipeline pattern allows adding new steps without modifying existing ones.

## Consequences

### Positive
- Supports real-world financial document formats
- Formula calculation ensures accurate values
- Forecast filtering reduces LLM confusion
- Reuses existing PDF extraction pipeline

### Negative
- Adds ~200MB to Docker image (LibreOffice)
- Conversion adds 5-15 seconds of latency
- Requires tempfile handling for conversion

## Implementation Timeline
Phase 2: After MVP submission. Requires adding LibreOffice to Dockerfile and `openpyxl` + `Pillow` to dependencies.
