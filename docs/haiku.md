# Haiku

Flow Healer uses Claude Haiku as one of its AI connector backends for automated code generation and repair.

## Overview

Claude Haiku is Anthropic's efficient large language model optimized for speed and cost-effectiveness. It's particularly well-suited for focused, deterministic repair tasks like fixing test failures, updating dependencies, and handling configuration changes.

## Configuration

To use Haiku as your connector, configure your `config.yaml`:

```yaml
service:
  connector_backend: claude_cli  # or other Haiku-supported backends
  connector_model: claude-haiku-4-5-20251001
```

## Use Cases

Haiku-powered healing handles:
- Test failure repairs
- Dependency upgrade fixes
- Configuration mismatches
- Breaking API changes
- Documentation updates

## When to Use Haiku

Haiku is ideal when:
- Speed is important (fast inference)
- Cost efficiency matters
- Tasks are focused and deterministic
- Large context is needed (200k window)

## Related Documentation

- [automated-coding-with-claude-haiku.md](automated-coding-with-claude-haiku.md) — Detailed guide on Claude Haiku integration
- [connectors.md](connectors.md) — All supported AI backends
- [agentic-coding.md](agentic-coding.md) — General agentic coding capabilities
