# Agentic Coding

Flow Healer enables AI-powered automated code repair through its agentic coding capabilities. This document covers how Flow Healer uses AI agents to understand issues, generate fixes, and validate solutions.

## How Agentic Coding Works

Flow Healer transforms GitHub issues into structured task specifications that AI agents can understand and execute:

1. **Issue Parsing**: The system parses issue titles, descriptions, and validation commands into a `HealerTaskSpec`
2. **Agent Execution**: An AI connector (Codex, Claude, or Haiku) generates a fix based on the task specification
3. **Validation**: The fix is applied to an isolated worktree and validated against the specified tests/commands
4. **Evidence Collection**: Successful fixes include evidence (test output, logs) in the draft PR

## Supported Agents

### OpenAI Codex

Codex is Flow Healer's primary agentic backend:

```yaml
service:
  connector_backend: app_server  # or exec
  connector_model: gpt-5.1-codex-mini
```

Features:
- Native multi-agent support (`healer_codex_native_multi_agent_enabled`)
- Subagent orchestration for complex tasks
- App-server mode for persistent sessions
- Exec mode for stateless invocations

### Claude (Haiku, Sonnet, Opus)

Anthropic's Claude models can power Flow Healer:

```yaml
service:
  connector_backend: claude_cli
  connector_model: claude-sonnet-4-20250514
```

### Other Backends

Flow Healer supports multiple connector backends:
- `gemini_cli` — Google's Gemini
- `cline` — Cline CLI
- `kilo_cli` — Kilo CLI

See [connectors.md](connectors.md) for full backend documentation.

## Native Multi-Agent Recovery

When a fix fails validation, Flow Healer can invoke Codex's native multi-agent system to recover:

```yaml
repos:
  - repo_slug: owner/repo
    healer_codex_native_multi_agent_enabled: true
    healer_codex_native_multi_agent_max_subagents: 3
```

This spawns subagents to:
- Analyze the failure context
- Propose alternative approaches
- Execute recovery strategies

## Task Specification

Every agent receives a structured task spec containing:

- **Task kind**: The category of work (test_fix, config_update, etc.)
- **Execution root**: The directory or file to modify
- **Required outputs**: Files that must be changed
- **Input-only context**: Reference files that shouldn't be modified
- **Validation commands**: How to verify the fix
- **Runtime profile**: Language, framework, and environment details

See [issue-contracts.md](issue-contracts.md) for the full specification.

## Best Practices

1. **Clear issue contracts**: Well-defined `Required code outputs` and `Validation command` improve agent success
2. **Use lane guides**: Follow [lane-guides/README.md](lane-guides/README.md) for language-specific expectations
3. **Monitor recovery patterns**: Check [agent-remediation-playbook.md](agent-remediation-playbook.md) for repeated failure handling

## Extending Agent Capabilities

To add new agent features:

1. Define new task kinds in `healer_task_spec.py`
2. Add validation logic in `healer_runner.py`
3. Update lane guides for new language/framework support
4. Add tests in the matching `tests/test_healer_*.py` module

## Related Documentation

- [connectors.md](connectors.md) — All supported AI backends
- [haiku.md](haiku.md) — Claude Haiku configuration
- [automated-coding-with-claude-haiku.md](automated-coding-with-claude-haiku.md) — Deep dive on Haiku
- [agent-remediation-playbook.md](agent-remediation-playbook.md) — Repeated failure handling
