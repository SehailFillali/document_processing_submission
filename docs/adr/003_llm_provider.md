# ADR 003: Use PydanticAI with OpenAI/Gemini for Extraction

## Status
**Accepted** - 2026-03-02

## Context
We need an AI/LLM provider for document extraction that can:
- Parse unstructured PDFs into structured data
- Enforce output schemas (Pydantic models)
- Provide confidence scores
- Handle various document types

## Decision
We will use **PydanticAI** with OpenAI GPT-4o as primary model, Gemini as fallback. PydanticAI provides:
- Native Pydantic schema enforcement
- Type-safe agent definitions
- Easy provider swapping

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **PydanticAI + OpenAI (Chosen)** | Schema enforcement, easy API | Cost | N/A |
| PydanticAI + VertexAI | Enterprise ready | GCP setup required | Overkill for MVP |
| LangChain + OpenAI | Flexible | Complex, less type-safe | Overengineering |
| Manual API calls | Full control | Reinventing wheel | Time sink |

## Model Selection

| Model | Use Case | Cost | Context |
|-------|----------|------|---------|
| gpt-4o-mini | Production | Low | Fast, cheap extraction |
| gpt-4o | Complex docs | Medium | Higher accuracy |
| gemini-1.5-flash | Fallback | Low | Google ecosystem |

## Implementation

```python
from pydantic_ai import Agent
from pydantic import BaseModel

class BorrowerProfile(BaseModel):
    name: str
    address: Address
    income_history: list[IncomeEntry]

agent = Agent(
    model="gpt-4o-mini",
    result_type=BorrowerProfile,
    system_prompt="Extract loan document data..."
)

result = await agent.run(document_url)
# result.data is validated BorrowerProfile
```

## Consequences

- **Positive**: Schema enforcement at API level, easy provider swap
- **Negative**: API costs, dependency on external service

## Review Schedule
Quarterly review of model performance and costs.
