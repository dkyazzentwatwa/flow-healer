# Ecosystem Support Tier Implementation Plan

## Overview

Implement a tiered ecosystem support model for Flow Healer that differentiates between:
- **VERIFIED**: Full autonomous PR capability with strong detection, validation, and retry handling
- **GUARDED**: Patching + smoke/build validation, autonomous PR only when validation confidence is high
- **ASSISTED**: Patch-capable but requires human-supplied validation commands

## Files to Create

### 1. `src/flow_healer/ecosystem.py` (NEW - Core Domain Model)

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import FrozenSet

class EcosystemSupportTier(Enum):
    VERIFIED = "verified"      # Full autonomy ready
    GUARDED = "guarded"        # Conditional autonomy
    ASSISTED = "assisted"      # Human validation required

class ValidationDepth(Enum):
    PARSE_ONLY = "parse_only"
    SMOKE = "smoke"
    BUILD_LINT = "build_lint"
    FULL_TEST = "full_test"
    AUTONOMOUS_READY = "autonomous_ready"

@dataclass(frozen=True)
class EcosystemProfile:
    ecosystem_id: str           # e.g., "python-pytest", "node-npm-jest"
    language: str               # e.g., "python", "node"
    framework: str               # e.g., "pytest", "jest"
    tier: EcosystemSupportTier
    validation_depths: tuple[ValidationDepth, ...]
    markers: FrozenSet[str]     # Files that indicate this ecosystem
    root_detectors: tuple[str, ...]  # Priority order for root detection
    test_commands: tuple[str, ...]    # Valid test commands
    autonomous_pr_ready: bool
    docker_image: str
    docker_install_cmd: str

# Ecosystem profiles registry
class EcosystemRegistry:
    _profiles: dict[str, EcosystemProfile]
    
    @classmethod
    def detect(cls, repo_path: Path) -> tuple[str, EcosystemProfile, float]:
        """Detect ecosystem from repo, returns (id, profile, confidence)"""
    
    @classmethod
    def get(cls, ecosystem_id: str) -> EcosystemProfile | None:
        """Get profile by ID"""
    
    @classmethod
    def recommended_mode(cls, ecosystem_id: str, validation_commands: tuple[str, ...]) -> EcosystemSupportTier:
        """Determine recommended mode based on ecosystem and validation"""
```

**Ecosystem Profiles to Define:**

| Ecosystem ID | Language | Framework | Tier | Validation Depths |
|-------------|----------|-----------|------|------------------|
| python-pytest | python | pytest | VERIFIED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST, AUTONOMOUS_READY |
| python-poetry-pytest | python | pytest | VERIFIED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST, AUTONOMOUS_READY |
| node-npm-jest | node | jest | VERIFIED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST, AUTONOMOUS_READY |
| node-pnpm-vitest | node | vitest | VERIFIED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST, AUTONOMOUS_READY |
| go-modules | go | go | GUARDED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST |
| rust-cargo | rust | cargo | GUARDED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST |
| java-gradle | java | gradle | GUARDED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST |
| java-maven | java | maven | GUARDED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST |
| dotnet-sln | dotnet | dotnet | GUARDED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST |
| ruby-bundler-rspec | ruby | rspec | GUARDED | PARSE_ONLY, SMOKE, BUILD_LINT, FULL_TEST |
| swift-spm | swift | spm | ASSISTED | PARSE_ONLY |
| php-composer | php | phpunit | ASSISTED | PARSE_ONLY |

### 2. `src/flow_healer/validation/adapters.py` (NEW)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

class ValidationErrorKind(Enum):
    MISSING_TOOLCHAIN = "missing_toolchain"
    MISSING_DEPENDENCIES = "missing_dependencies"
    INVALID_EXECUTION_ROOT = "invalid_execution_root"
    UNSUPPORTED_PROJECT_SHAPE = "unsupported_project_shape"
    INFRA_RUNTIME_ISSUE = "infra_runtime_issue"
    REPO_CONTRACT_INSUFFICIENT = "repo_contract_insufficient"
    TEST_TIMEOUT = "test_timeout"
    TEST_FAILURE = "test_failure"

@dataclass
class ValidationResult:
    success: bool
    output: str
    error_kind: ValidationErrorKind | None = None
    error_message: str = ""
    duration_seconds: float = 0.0

class ValidationAdapter(ABC):
    @abstractmethod
    def validate(
        self,
        workspace: Path,
        execution_root: str,
        depth: ValidationDepth,
        command: str | None = None,
    ) -> ValidationResult:
        pass
    
    @abstractmethod
    def can_handle(self, ecosystem_id: str) -> bool:
        pass

# Concrete adapters
class PythonPytestAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        cmd = command or "pytest -q"
        # Run with timeout, capture output, classify errors
        ...

class NodeNpmJestAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        cmd = command or "npm test -- --passWithNoTests"
        ...

class GoTestAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        # Requires explicit validation command for guarded mode
        ...

class RustCargoAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        # Requires explicit validation command for guarded mode
        ...

class JavaGradleAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        # Detect gradlew wrapper
        ...

class JavaMavenAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        ...

class RubyRspecAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        ...

class SwiftTestAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        # Assisted mode - limited automation
        ...

class DotNetTestAdapter(ValidationAdapter):
    def validate(self, workspace, execution_root, depth, command=None) -> ValidationResult:
        ...

# Adapter registry
class ValidationAdapterRegistry:
    _adapters: list[ValidationAdapter]
    
    @classmethod
    def get_adapter(cls, ecosystem_id: str) -> ValidationAdapter | None:
        for adapter in cls._adapters:
            if adapter.can_handle(ecosystem_id):
                return adapter
        return None
```

### 3. `src/flow_healer/policy.py` (NEW - Autonomy Policy)

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class AutonomyMode(Enum):
    VERIFIED_AUTONOMOUS = "verified_autonomous"
    GUARDED = "guarded"
    ASSISTED = "assisted"

# Downgrade reason codes
DOWNGRADE_UNSUPPORTED_ECOSYSTEM = "unsupported_ecosystem"
DOWNGRADE_AMBIGUOUS_EXECUTION_ROOT = "ambiguous_execution_root"
DOWNGRADE_MISSING_TEST_COMMAND = "missing_test_command"
DOWNGRADE_MISSING_TOOLCHAIN = "missing_toolchain"
DOWNGRADE_LOW_CONFIDENCE_DETECTION = "low_confidence_detection"
DOWNGRADE_VALIDATION_UNAVAILABLE = "validation_unavailable"
DOWNGRADE_REPO_CONTRACT_INSUFFICIENT = "repo_contract_insufficient"

@dataclass
class AutonomyDecision:
    mode: AutonomyMode
    reasons: tuple[str, ...]
    recommended_action: str
    validation_depth_achieved: ValidationDepth | None = None

def compute_autonomy(
    ecosystem_profile: EcosystemProfile,
    validation_result: ValidationResult | None,
    execution_root_confidence: float,
    has_explicit_validation_command: bool,
    repo_config_overrides: dict | None = None,
) -> AutonomyDecision:
    """
    Determine autonomy level based on:
    - Ecosystem tier
    - Validation depth achieved
    - Execution root confidence
    - Explicit validation command presence
    - Repo config overrides
    """
    
    # VERIFIED + full validation passes = normal autonomous PR
    if (ecosystem_profile.tier == EcosystemSupportTier.VERIFIED and 
        validation_result and validation_result.success):
        return AutonomyDecision(
            mode=AutonomyMode.VERIFIED_AUTONOMOUS,
            reasons=(),
            recommended_action="open_pr",
            validation_depth_achieved=ValidationDepth.AUTONOMOUS_READY,
        )
    
    # GUARDED + smoke/build passes but full validation unavailable = guarded/draft
    if ecosystem_profile.tier == EcosystemSupportTier.GUARDED:
        reasons = []
        if not has_explicit_validation_command:
            reasons.append(DOWNGRADE_MISSING_TEST_COMMAND)
        if validation_result and not validation_result.success:
            reasons.append(validation_result.error_kind.value)
        
        return AutonomyDecision(
            mode=AutonomyMode.GUARDED,
            reasons=tuple(reasons),
            recommended_action="create_draft_pr" if not has_explicit_validation_command else "require_human_review",
        )
    
    # ASSISTED = patch generation allowed, stronger human validation required
    return AutonomyDecision(
        mode=AutonomyMode.ASSISTED,
        reasons=(DOWNGRADE_UNSUPPORTED_ECOSYSTEM,),
        recommended_action="require_human_validation",
    )
```

## Files to Modify

### 4. `src/flow_healer/language_detector.py`

- Add `detect_ecosystem()` function that returns ecosystem_id and confidence
- Refactor existing `detect_language()` to use ecosystem registry internally
- Preserve backward compatibility

### 5. `src/flow_healer/language_strategies.py`

- Keep for backward compatibility
- Add `get_strategy_for_ecosystem(ecosystem_id: str) -> LanguageStrategy`
- Bridge ecosystem profile → LanguageStrategy

### 6. `src/flow_healer/healer_task_spec.py`

Add fields to HealerTaskSpec:
```python
@dataclass
class HealerTaskSpec:
    # ... existing fields ...
    ecosystem_id: str = ""
    ecosystem_tier: str = ""  # "verified", "guarded", "assisted"
    recommended_mode: str = ""  # "verified", "guarded", "assisted"
    root_detection_confidence: float = 0.0
    detected_tools: tuple[str, ...] = ()  # npm, pytest, cargo, etc.
```

Update `compile_task_spec()` to:
- Infer ecosystem_id from issue body, validation commands, paths
- Determine recommended_mode based on ecosystem + available validation
- Set root_detection_confidence

### 7. `src/flow_healer/healer_runner.py`

- Import ecosystem module
- Pass ecosystem profile to validation adapters
- Use autonomy policy to determine PR behavior:
  - VERIFIED_AUTONOMOUS: open PR normally
  - GUARDED: create draft PR or require review
  - ASSISTED: flag for human validation

### 8. `src/flow_healer/service.py`

Update `status_rows()` and `doctor_rows()` to include:

```python
{
    "ecosystem": {
        "id": "python-pytest",
        "tier": "verified",
        "language": "python",
        "framework": "pytest",
        "root_detection_confidence": 0.95,
        "selected_execution_root": "e2e-smoke/python",
        "detected_tools": ["pytest", "pip"],
        "supported_validation_depths": ["parse_only", "smoke", "build_lint", "full_test", "autonomous_ready"],
        "autonomous_pr_ready": True,
        "recommended_mode": "verified",
        "downgrade_reasons": [],
    },
    # ... existing fields ...
}
```

### 9. `src/flow_healer/config.py`

Add new config options to RelaySettings:
```python
@dataclass
class RelaySettings:
    # ... existing fields ...
    healer_ecosystem: str = ""  # Override detected ecosystem
    healer_validation_depth_cap: str = ""  # "full_test", "build_lint", "smoke"
    healer_autonomous_pr_threshold: float = 0.8
    healer_draft_pr_for_guarded: bool = True
```

### 10. `README.md`

Replace "Supported Languages" section:

```markdown
## Verified Ecosystem Support

Flow Healer provides tiered autonomous PR automation based on ecosystem maturity:

### Tier A: Verified
- **Python (pytest, poetry)**: Full autonomous PR with targeted test inference
- **Node.js (npm/pnpm + jest/vitest)**: Full autonomous PR with targeted test inference

### Tier B: Guarded
- **Go modules**: Patch-capable, requires explicit validation command
- **Rust (cargo)**: Patch-capable, requires explicit validation command
- **Java (Gradle/Maven)**: Patch-capable, requires explicit validation command
- **Ruby (bundler + rspec)**: Patch-capable, requires explicit validation command
- **.NET**: Patch-capable, requires explicit validation command

### Tier C: Assisted
- **Swift (SPM)**: Patch-capable, human validation required
- **PHP (composer)**: Patch-capable, human validation required

### Ecosystem Detection

Flow Healer automatically detects:
- Package manager and lockfiles (package.json, go.mod, Cargo.toml, etc.)
- Test framework from config (pytest.ini, jest.config.js, etc.)
- Build tools (npm, gradle, maven, cargo, etc.)
- Monorepo markers (pnpm-workspace.yaml, nx.json, turbo.json)

### Adding New Ecosystems

Ecosystems are defined in `ecosystem.py` as `EcosystemProfile` entries.
Validation adapters live in `validation/adapters.py`.
```

## Test Files to Create/Modify

### 11. `tests/test_ecosystem.py` (NEW)
- Test ecosystem detection from various repo structures
- Test tier determination logic
- Test confidence scoring

### 12. `tests/test_validation_adapters.py` (NEW)
- Test each adapter's command parsing
- Test error classification
- Test timeout handling

### 13. `tests/test_policy.py` (NEW)
- Test autonomy decisions for each tier
- Test downgrade reasons
- Test repo config overrides

### 14. Update existing tests
- `test_language_detector.py` - add ecosystem tests
- `test_service.py` - add ecosystem fields to status output tests

## Implementation Order

| Order | Component | Priority | Description |
|-------|-----------|----------|-------------|
| 1 | `ecosystem.py` | CRITICAL | Domain model - tiers, profiles, registry |
| 2 | `language_detector.py` | CRITICAL | Detect ecosystem from repo |
| 3 | `healer_task_spec.py` | CRITICAL | Add ecosystem to task spec |
| 4 | `validation/adapters.py` | HIGH | Implement validation adapters |
| 5 | `policy.py` | HIGH | Autonomy decision logic |
| 6 | `service.py` | HIGH | Update status/doctor outputs |
| 7 | `config.py` | MEDIUM | Add ecosystem config options |
| 8 | `README.md` | MEDIUM | Update documentation |
| 9 | Tests | MEDIUM | Unit tests for new components |

## Key Design Decisions

1. **Backward Compatibility**: Keep `language_strategies.py` and `language_detector.py` interfaces unchanged
2. **Conservative Autonomy**: Default to guarded/assisted, require explicit opt-in for full autonomy
3. **Explicit Downgrades**: Always surface why autonomy was downgraded in status output
4. **Configurable**: Allow repo-level overrides for ecosystem mode, validation depth cap
5. **Extensible**: New ecosystems can be added by defining profiles + validation adapters
