import re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class HealerTaskSpec:
    execution_root: str
    output_targets: tuple[str, ...]

def _normalize_known_sandbox_root(path: str) -> str:
    normalized = str(path or "").strip().strip("'\"").lstrip("./").rstrip("/")
    if not normalized:
        return ""
    parts = Path(normalized).parts
    if len(parts) >= 2 and parts[0] in {"e2e-smoke", "e2e-apps"}:
        return Path(parts[0], parts[1]).as_posix()
    if normalized.startswith("e2e-smoke/") or normalized.startswith("e2e-apps/"):
        return normalized
    return ""

def _sandbox_roots_from_targets(output_targets: tuple[str, ...]) -> tuple[str, ...]:
    roots = {
        _normalize_known_sandbox_root(target)
        for target in output_targets
    }
    return tuple(sorted([r for r in roots if r]))

def _execution_root_conflicts_with_targets(task_spec: HealerTaskSpec) -> bool:
    if not task_spec.execution_root:
        return False
    target_roots = _sandbox_roots_from_targets(task_spec.output_targets)
    if not target_roots:
        return False
    normalized_execution_root = _normalize_known_sandbox_root(task_spec.execution_root)
    if normalized_execution_root:
        return normalized_execution_root not in target_roots
    return str(task_spec.execution_root) not in target_roots

# Simulate issue 1014
ts = HealerTaskSpec(
    execution_root="e2e-apps/node-next",
    output_targets=("e2e-apps/node-next/app/tictactoe-t4/page.js",)
)

print(f"Target roots: {_sandbox_roots_from_targets(ts.output_targets)}")
print(f"Normalized exec root: {_normalize_known_sandbox_root(ts.execution_root)}")
print(f"Conflict: {_execution_root_conflicts_with_targets(ts)}")
