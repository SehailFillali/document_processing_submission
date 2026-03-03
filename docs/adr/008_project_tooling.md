# ADR 008: Project Tooling Selection (uv + just)

## Status
**Accepted** - 2026-03-02

## Context
We need to select modern, efficient tooling for dependency management and task automation. The goal is to maximize developer productivity while maintaining simplicity for a small team with limited setup time.

## Purpose
This decision impacts:
- **Developer Experience**: How quickly new team members can get started
- **Build Performance**: How fast dependencies install and tests run
- **Maintainability**: How easy it is to add new commands or dependencies

## Alternatives Considered

| Alternative | Description | Installation Time | Learning Curve | Ecosystem |
|-------------|-------------|------------------|----------------|-----------|
| **uv + just (Chosen)** | Rust-based package manager + command runner | ~5 seconds | Low | Growing rapidly |
| pip + Makefile | Traditional Python tools | ~30+ seconds | Low | Mature but slow |
| Poetry | Python-native dependency management | ~20 seconds | Medium | Strong but slow |
| PDM | Modern Python package manager | ~15 seconds | Medium | Good |
| pipenv | Python's official recommendation | ~25 seconds | Medium | Stable but dated |
| conda | Data science focused | ~60+ seconds | High | Very large |

## Detailed Pros and Cons

### uv + just (Chosen)

**Pros:**
- **10-100x faster dependency resolution** (Rust-based)
- Single command setup (`just setup` = `uv sync`)
- No virtual environment activation needed
- Editable installs by default
- Modern lockfile format
- just recipes are shell-agnostic and self-documenting
- Built-in parallel task execution

**Cons:**
- uv is relatively new (2023) - less community knowledge
- Some edge cases in dependency resolution (rare)
- just isn't as widely known as Make in some communities

### pip + Makefile

**Pros:**
- Universal compatibility
- Make is well-known
- No new tools to learn

**Cons:**
- Slow (no caching, no parallel resolution)
- Makefile syntax is brittle and hard to read
- No lockfile by default (needs pip-tools)
- Virtual environment management is manual

### Poetry

**Pros:**
- Excellent dependency resolution
- Built-in virtualenv management
- Good lockfile format

**Cons:**
- Slow performance (Python-based)
- Dual purpose (build + package) adds complexity
- pyproject.toml can get confusing

## Conclusion

We chose **uv + just** because:

1. **Speed matters for iteration**: 5-second setup vs 30+ seconds compounds over time
2. **Simplicity**: `just --list` shows all available commands clearly
3. **Modern stack**: Using cutting-edge tools signals engineering culture
4. **DX first**: The "4-hour rule" in the assignment means developer velocity is critical

For a small team building an MVP, the productivity gain far outweighs the risk of using newer tools.

## Consequences

### Positive
- New developers can start in under 60 seconds
- CI/CD pipelines run faster
- Clear, self-documenting commands
- No more "works on my machine" issues

### Negative
- Team needs to learn uv syntax (minor)
- Some recruiters may not recognize uv (negligible)
- Need to document uv-specific features

## Implementation

See:
- `pyproject.toml` - dependency definitions
- `Justfile` - task automation commands
- `.env.example` - environment template

## Review Schedule
Review in 6 months to assess if tooling is meeting team needs, or if adoption issues emerge.
