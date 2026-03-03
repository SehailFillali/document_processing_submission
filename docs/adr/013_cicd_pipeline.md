# ADR 013: CI/CD Pipeline with GitHub Actions

## Status
**Accepted** - 2026-03-02

## Context
We need to automate our build, test, and deployment processes. The assignment expects production-ready infrastructure. We need to document the CI/CD strategy.

## Purpose
This decision impacts:
- **Delivery Speed**: How fast we can ship
- **Quality**: How we prevent regressions
- **Reliability**: How we ensure consistent builds
- **Developer Experience**: How automated our workflow is

## Alternatives Considered

| Alternative | Pros | Cons | Best For |
|-------------|------|------|----------|
| **GitHub Actions (Chosen)** | Free tier, tight GitHub integration | Less customizable | GitHub repos |
| GitLab CI | Full CI/CD in GitLab | Vendor lock-in | GitLab repos |
| Jenkins | Highly customizable | Complex setup | Enterprise |
| CircleCI | Good parallelism | Expensive at scale | Fast builds |
| AWS CodePipeline | Native AWS integration | AWS only | AWS shops |
| Terraform Cloud | IaC focused | Not general CI/CD | Terraform |

## Detailed Pros and Cons

### GitHub Actions (Chosen)

**Pros:**
- **Free tier** - 2000 min/month free
- **Native GitHub** - Tight integration with repo
- **Marketplace** - Many pre-built actions
- **Easy setup** - YAML-based workflow
- **Matrix builds** - Test multiple versions
- **Caching** - Built-in caching for dependencies

**Cons:**
- **Limited customization** - Less flexible than Jenkins
- **Cold starts** - First run can be slow
- **Concurrency limits** - Can be restrictive
- **Debugging** - Harder to debug failures

### Jenkins

**Pros:**
- **Highly customizable** - Almost unlimited flexibility
- **Self-hosted** - Full control
- **Mature** - Battle-tested

**Cons:**
- **Complex setup** - Requires server maintenance
- **Outdated UI** - Looks dated
- **Plugin issues** - Plugin dependency hell

### GitLab CI

**Pros:**
- **All-in-one** - CI/CD built into GitLab
- **Good UI** - Modern interface
- **Auto DevOps** - Auto-deploy capability

**Cons:**
- **Vendor lock-in** - Must use GitLab
- **Complex** - Feature-rich but complex

## Conclusion

We chose **GitHub Actions** because:

1. **Assignment submission** - GitHub repo expected
2. **Free tier** - Sufficient for MVP
3. **Tight integration** - Native GitHub experience
4. **Simplicity** - Easy to understand and modify
5. **Fast setup** - No server to maintain

## Pipeline Design

### Workflows

1. **CI (ci.yml)** - Runs on every push
   - Lint (ruff, mypy)
   - Type check
   - Unit tests with coverage
   
2. **Deploy (deploy.yml)** - Runs on main branch
   - Build Docker image
   - Push to registry (optional for assignment)
   
3. **Evaluate (evaluate.yml)** - Manual trigger
   - Run evaluation script
   - Report metrics

### Jobs

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/uv-action@v1
      - run: just lint
  
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/uv-action@v1
      - run: just test
```

## Consequences

### Positive
- Automated quality gates
- Consistent builds every time
- Fast feedback loop
- Easy to add more stages
- Great for assignment submission

### Negative
- Limited to GitHub ecosystem
- Can hit rate limits on heavy usage
- Debugging CI issues can be tricky

## Implementation

See:
- `.github/workflows/ci.yml` - CI workflow
- `.github/workflows/deploy.yml` - Deploy workflow
- `.github/workflows/evaluate.yml` - Evaluation workflow
- `Justfile` - Local automation commands

## Review Schedule
Review after assignment submission to assess if pipeline meets deployment needs.