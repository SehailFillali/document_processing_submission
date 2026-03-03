# ADR 024: Native LLM PDF Ingestion over Local Text Extraction

## Status
**Accepted** - 2026-03-02

## Context
The document extraction pipeline needs to read PDF content from loan documents (W2s, paystubs, 1040s, closing disclosures, bank statements, title reports) and extract structured borrower profiles. The traditional approach would be to build a local text extraction layer — parsing PDFs into plain text before sending that text to an LLM. This ADR documents the deliberate choice to skip that layer and rely on native LLM PDF ingestion instead.

## Purpose
This decision impacts:
- **Pipeline complexity**: Whether we maintain a PDF parsing subsystem
- **Extraction quality**: How faithfully document structure (tables, forms, layout) is preserved
- **Operational cost**: Local compute vs. API token cost
- **Time to delivery**: Engineering effort spent on preprocessing vs. core extraction logic

## Decision: Native LLM PDF Ingestion

We send PDF documents directly to multimodal LLMs rather than implementing local text extraction. All three major providers now support native PDF input:

| Provider | Model | Max Size | Max Pages | How It Works |
|----------|-------|----------|-----------|--------------|
| **OpenAI** | GPT-4o, GPT-4o-mini | 50 MB | Context-limited | Extracts text + renders page images |
| **Google Gemini** | 1.5 Pro, 1.5 Flash, 2.0 Flash | 2 GB | 3,600 pages | Native multimodal processing |
| **Anthropic Claude** | Claude Opus 4, Sonnet 4 | 32 MB | 100 pages | Converts pages to images + extracts text |

For loan documents (typically 1-20 pages, under 10 MB), all three providers are well within their limits.

### Why This Is the Right Choice for MVP

1. **No lossy intermediate representation.** Local text extraction (pdfminer, pypdf, etc.) strips layout, loses table structure, and cannot handle scanned content. The LLM sees the document as-is — tables, forms, headers, and spatial relationships intact.

2. **Eliminates an entire subsystem.** A robust PDF parsing layer requires handling: digital vs. scanned PDFs, OCR fallback, table detection, reading order reconstruction, font encoding issues, and password-protected files. That is weeks of engineering for a capability the LLM already has.

3. **Form and table comprehension.** Loan documents are heavily form-based (W2 boxes, 1040 line items, closing disclosure tables). Multimodal LLMs interpret these visually with spatial understanding, which is superior to reconstructing table structure from extracted text coordinates.

4. **Scanned document handling.** Native vision capabilities handle scanned PDFs without requiring a separate OCR pipeline. The LLM reads the page image directly.

5. **Consistent with the architecture.** Our hexagonal design (ADR 001) and LLM provider strategy (ADR 003, 010) already abstract the LLM behind a port interface. The adapter is responsible for preparing the input — whether that means sending raw PDF bytes or base64-encoded content is an adapter implementation detail, not a pipeline concern.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| **Native LLM PDF ingestion (Chosen)** | Zero preprocessing, full layout fidelity, handles scans | Higher token cost, provider-dependent limits | N/A |
| pymupdf text extraction | Fast (10-100x faster than pdfminer-based), renders to images | AGPL license, loses layout for LLM, no table extraction | License restrictive for SaaS; text-only loses structure |
| pdfplumber | Best table extraction for digital PDFs, MIT license | Slow, no OCR, no scanned PDF support | Cannot handle scanned loan documents |
| pypdf | Pure Python, zero deps, good for split/merge | Poor text extraction quality, no tables, no OCR | Insufficient extraction quality for loan data |
| unstructured.io | Multi-format, element classification, OCR integration | Heavy deps (poppler, tesseract, libreoffice), still beta | Excessive complexity for MVP; heavy Docker image |
| docling (IBM) | MIT license, excellent table structure recognition, layout AI models | Heavy ML dependencies, GPU recommended, relatively new | Overkill for MVP; strong future candidate |
| marker | Highest benchmark scores on forms/financial docs, hybrid LLM mode | GPL license, GPU required, 3-5GB VRAM | License + GPU requirements impractical for MVP |
| Cloud OCR (Google Document AI) | Purpose-built lending processor, highest accuracy | Vendor lock-in, $0.065-1.50/page, data sovereignty | Cost and dependency inappropriate for MVP |

## Trade-offs Accepted

| Concern | Mitigation |
|---------|-----------|
| **Higher token cost** | gpt-4o-mini is $0.15/1M input tokens — a 10-page PDF costs ~$0.05. Acceptable for MVP volume. Cost tracking via Logfire (ADR 017) provides visibility. |
| **Provider page/size limits** | Loan documents are typically 1-20 pages, well under all provider limits. |
| **No offline capability** | Acceptable for MVP. Future phase adds local extraction for air-gapped deployments. |
| **OCR quality on degraded scans** | Multimodal LLMs handle typical scanned documents. Severely degraded scans would need dedicated OCR regardless. |

## Future Phase: Local PDF Preprocessing Pipeline

When document volume, cost pressure, or accuracy requirements exceed what native LLM ingestion provides, the following hybrid approach is recommended.

### Trigger Conditions
- Processing >1,000 documents/day (token cost becomes significant)
- Encountering document types where LLM extraction accuracy drops below 90%
- Air-gapped deployment requirements
- Need for deterministic text extraction (regulatory/audit compliance)

### Recommended Approach: Hybrid Text + Vision

```
PDF Input
    |
    +---> pymupdf: Fast text extraction + page rendering
    |         |
    |         +-- Text extracted? ---> Send text to LLM (cheaper, faster)
    |         |
    |         +-- Empty/garbled? ---> Scanned document detected
    |                 |
    |                 +---> OCR fallback (PaddleOCR or Tesseract)
    |                         |
    |                         +---> Send OCR text + page images to LLM
    |
    +---> Complex tables detected? ---> docling / marker for structure
                                            |
                                            +---> Send structured markdown to LLM
```

### Library Assessment for Future Implementation

#### Tier 1: Primary Candidates

| Library | License | Strength | Loan Doc Fit |
|---------|---------|----------|--------------|
| **docling** (IBM) v2.76+ | MIT | Layout AI, table structure (TableFormer), multi-format, MCP server | Excellent — table recognition critical for loan schedules |
| **marker** v1.10+ | GPL-3.0 / Commercial | Highest benchmarks on forms (88.01 heuristic), financial docs (95.37), hybrid LLM mode | Excellent — but GPL requires commercial license for SaaS |
| **pymupdf** v1.27+ | AGPL / Commercial | Fastest extraction (10-100x), page rendering, optional OCR | Good for text + image extraction; license needs evaluation |

#### Tier 2: Specialized

| Library | License | Strength | Use Case |
|---------|---------|----------|----------|
| **pdfplumber** v0.11+ | MIT | Best table extraction for digital PDFs, spatial analysis | Extract specific tables when docling/marker unavailable |
| **surya** | GPL-3.0 | OCR + layout detection + reading order, powers marker | Custom pipelines needing component-level control |
| **pypdf** v6.7+ | BSD-3 | PDF manipulation (split, merge, encrypt) | Splitting multi-document loan packages |

#### Tier 3: Cloud OCR (Production Scale)

| Service | Pricing | Strength | Use Case |
|---------|---------|----------|----------|
| **Google Document AI** | $0.065-1.50/page | Purpose-built lending document processor | Production: extracts borrower info, income, property details out-of-the-box |
| **Amazon Textract** | ~$1.50/page | Form key-value extraction, signature detection | Production: HIPAA/SOC2 compliant, key-value maps to loan fields |
| **Azure Document Intelligence** | $0.01-1.50/page | Custom model training, pre-built invoice/ID models | Production: custom models for proprietary loan forms |

### Hybrid Strategy Rationale

The best future approach combines local preprocessing with LLM interpretation:

1. **pymupdf** for fast text extraction and page-to-image rendering (determines if document is digital or scanned)
2. **docling** or **marker** for complex table/form structure extraction (converts to structured markdown)
3. **LLM** for semantic field extraction from the structured text (cheaper than sending raw PDF)
4. **LLM vision fallback** for pages where text extraction fails or produces garbled output

This reduces token cost by 60-80% (sending extracted text vs. full PDF) while maintaining extraction quality through the LLM's semantic understanding.

## Consequences

### Positive
- Zero preprocessing infrastructure to build and maintain
- Full document fidelity — layout, tables, forms preserved
- Handles both digital and scanned PDFs without branching logic
- Faster time to working implementation
- Consistent with hexagonal architecture — adapter handles format details

### Negative
- Higher per-document token cost than text-only LLM calls
- Dependent on provider multimodal capabilities
- No offline/air-gapped processing
- Less control over exactly what text the LLM "sees"

## Related ADRs
- [ADR 001 - Hexagonal Architecture](001_hexagonal_architecture.md): Port/adapter pattern isolates PDF handling
- [ADR 003 - LLM Provider](003_llm_provider.md): PydanticAI + OpenAI/Gemini strategy
- [ADR 010 - LLM Provider Selection](010_llm_provider_selection.md): Model selection rationale
- [ADR 019 - Excel Preprocessing](019_excel_preprocessing.md): Future work for non-PDF formats

## Review Schedule
Revisit when any trigger condition is met (>1K docs/day, accuracy drops below 90%, air-gapped deployment needed, or regulatory requirement for deterministic extraction).
