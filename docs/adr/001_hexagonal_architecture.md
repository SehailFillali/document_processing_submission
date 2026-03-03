# ADR 001: Use Hexagonal Architecture

## Status
**Accepted** - 2026-03-02

## Context
We need to architect our document extraction system to be testable, maintainable, and extensible. The system must support multiple document types, different LLM providers, and various storage backends without tightly coupling business logic to infrastructure.

## Decision
We will use **Hexagonal Architecture** (Ports and Adapters pattern) to decouple core business logic from infrastructure concerns.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Hexagonal (Chosen)** | Testable, swappable adapters, clear boundaries | More abstraction overhead | N/A |
| Layered (MVC) | Simple, familiar | Tight coupling, hard to test | Poor testability for complex logic |
| Clean Architecture | Very clean separation | Overkill for scope | Too much ceremony |
| Monolithic Functions | No abstraction | Hard to test, tightly coupled | Can't swap providers |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Ports (Interfaces)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  Storage    │  │     LLM     │  │  Database   │       │
│  │    Port     │  │    Port     │  │    Port     │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   Adapters (Implementations)                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │    GCS      │  │   Gemini    │  │  SQLite    │         │
│  │  Adapter    │  │   Adapter   │  │  Adapter   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## Consequences

### Positive
- **Testability**: Core logic can be tested with mock adapters
- **Swappable Providers**: Change LLM or storage without touching business logic
- **Clear Boundaries**: Each layer has single responsibility
- **Extensible**: Add new document types or providers easily

### Negative
- **Initial Overhead**: More files and interfaces to create
- **Learning Curve**: Team needs to understand pattern

## Implementation

See `src/doc_extract/ports/` for interfaces and `src/doc_extract/adapters/` for implementations.

## Review Schedule
Review in 3 months to assess if architecture is meeting needs.
