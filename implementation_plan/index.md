# Implementation Plan: Document Extraction System

## Overview
A resilient, event-driven document extraction platform for unstructured data using modern Python stack with PydanticAI and Gemini API.

## Target Role
Founding Head of Engineering

## Core Philosophy
- **4-Hour Rule is a Trap:** Testing instincts, leadership, and architectural rigor
- **Defense-in-Depth:** Every choice justified in ADRs
- **Developer Experience:** Single command setup
- **Production-Ready System:** Not just a script

## Scope & Constraints
- **Deadline:** 7 days from receipt
- **Expected Effort:** 4-8 hours actual implementation
- **MVP Storage:** SQLite (not BigQuery)
- **IaC:** Terraform scaffolding only (no execution)
- **Event-Driven:** Documented in ADRs, not fully implemented

## Assignment Requirements Mapping

### Deliverable 1: System Design Document
- ✅ Architecture overview with component diagram
- ✅ Data pipeline (ingestion → processing → storage → retrieval)
- ✅ AI/LLM integration strategy (PydanticAI + Gemini API Key)
- ✅ Format variability handling (via DocumentUrl)
- ✅ Scaling 10x and 100x (Cloud Run + GCS + Pub/Sub)
- ✅ Technical trade-offs (7 ADRs)
- ✅ Error handling & data quality (Negative Space + Validation)

### Deliverable 2: Working Implementation
- ✅ Document ingestion pipeline (FastAPI + SHA-256 hashing)
- ✅ Extraction logic (PydanticAI + Gemini)
- ✅ Structured output (Pydantic v2)
- ✅ Query interface (FastAPI endpoints)
- ✅ Test coverage (Evaluation framework)

### Deliverable 3: README
- ✅ Setup instructions
- ✅ Architectural decisions summary
- ✅ Quick start guide

## Hidden Traps Analysis

1. **Context Window Limits:** 200-page documents → Chunking strategy required
2. **Hallucinations:** LLM inventing PII → Strict Pydantic validation + provenance
3. **Mixed Formats:** Scanned PDFs vs text-searchable → DocumentUrl handles this
4. **Idempotency:** Same file uploaded twice → SHA-256 hashing
5. **Schema Evolution:** Future document types → Hexagonal architecture enables swap
6. **Memory Limits:** Large files → Generators + streaming
7. **Cost Guardrails:** Token counting → Logfire observability
8. **Partial Success:** Some pages fail, others succeed → Structured error responses

## Tech Stack Summary

### Tier 1: Modern Baseline
- **Package Manager:** `uv` (Rust-based, 10-100x faster)
- **Task Runner:** `just` (replaces Make)
- **Validation:** `pydantic v2` (strict mode)
- **API:** `FastAPI` (async native)
- **Agent:** `PydanticAI` (enforced JSON schemas)
- **State Machine:** `Pydantic Graph`
- **Logging:** `loguru` (structured JSON)

### Tier 2: Paradigms
- **Negative Space Programming:** Fail fast with assertions
- **Graceful Degradation:** Non-critical paths log WARNING
- **Resilience:** `stamina` for exponential backoff
- **Idempotency:** Safe re-runs without corruption

### Tier 3: Scale
- **Concurrency:** `asyncio` + `httpx`
- **Caching:** SQLite for dev, Redis documented for prod
- **Chunking:** Generators for large files

## Execution Prompts Index

1. **01_project_setup.md** - Justfile, pyproject.toml, folder structure
2. **02_project_scaffold.md** - Docker, compose, basic structure
3. **03_domain_models.md** - Pydantic models for BorrowerProfile
4. **04_ports_interfaces.md** - Hexagonal architecture ports
5. **05_adapters_local.md** - Local implementations
6. **06_adapters_production.md** - GCS, Pub/Sub scaffolding
7. **07_api_endpoints.md** - FastAPI routes (Ingest, Query)
8. **08_processing_graph.md** - Pydantic Graph (3-node state machine)
9. **09_ai_extraction.md** - PydanticAI agent with Gemini
10. **10_storage_and_db.md** - SQLite/Postgres for MVP
11. **11_tests_and_eval.md** - Evaluation framework (Golden Set)
12. **12_terraform_scaffold.md** - Terraform files (scaffolding only)
13. **13_cicd_workflows.md** - GitHub Actions
14. **14_adrs.md** - All 7 ADR documents
15. **15_documentation.md** - README.md and SYSTEM_DESIGN.md
16. **16_test_coverage.md** - Increase test coverage to 80%+
17. **17_minio_integration.md** - MinIO blob storage integration
18. **18_circuit_breaker.md** - Circuit breaker & resilience patterns
19. **19_logfire_cost_tracking.md** - Logfire observability & cost tracking
20. **20_error_codes_rate_limiting.md** - Structured error codes & rate limiting
21. **21_code_quality_fixes.md** - Fix type errors and API consistency issues
22. **22_self_correction_loop.md** - Self-correction loop with critique agent
23. **23_prometheus_metrics.md** - Prometheus metrics endpoint and middleware
24. **24_datetime_deprecation_fixes.md** - Fix all datetime.utcnow() deprecation warnings
25. **25_excel_preprocessing_pipeline.md** - Excel-to-PDF preprocessing pipeline (8-step)
26. **26_assignment_compliance_fixes.md** - Fix all assignment requirement gaps (PDF ingestion, trade-offs, provenance, docs)

---

**Phase:** Prompts 01-23 executed. Prompts 24-26 ready for execution.
**Next Step:** Execute prompt 26 (critical compliance fixes), then 24-25, then final review.
