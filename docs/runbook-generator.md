# Runbook Generator

LangGraph-powered agent that automatically generates Redis SRE runbooks with built-in research and evaluation.

## Usage

### Basic Generation
```bash
uv run python -m redis_sre_agent.cli.main runbook generate \
  "Redis memory fragmentation crisis" \
  "Memory fragmentation ratio reached 4.2 causing performance issues"
```

### With Requirements
```bash
uv run python -m redis_sre_agent.cli.main runbook generate \
  "Redis Cluster slot migration stuck" \
  "Slot migration stuck at 52% with MOVED errors" \
  --severity critical \
  --requirements "Include CLUSTER diagnostic commands" \
  --requirements "Add manual recovery procedures"
```

### Evaluate Existing Runbooks
```bash
uv run python -m redis_sre_agent.cli.main runbook evaluate
```

## Options

- `--severity {critical,warning,info}` - Runbook severity
- `--requirements <text>` - Specific requirements (use multiple times)
- `--max-iterations <num>` - Refinement iterations (default: 2)
- `--auto-save` - Save to `source_documents/runbooks/`

## Quality Assurance

Each runbook is automatically evaluated on:
- **Technical Accuracy** - Redis commands correctness
- **Completeness** - Coverage of necessary aspects
- **Actionability** - Clear executable steps
- **Production Readiness** - Real incident response utility

**Expected Performance**: 4.0+/5.0 score, 2-3 minutes generation time

## Integration

1. **Generate** runbooks for poor-performing scenarios
2. **Ingest** via `pipeline ingest-sources`
3. **Verify** improvement with evaluation tests

## Architecture

- **Research Phase**: Tavily search + knowledge base lookup
- **Generation Phase**: LLM with structured template
- **Evaluation Phase**: Expert LLM judge assessment
- **Refinement**: Automatic improvement for scores <3.5

Located in `redis_sre_agent/agent/runbook_generator.py`
