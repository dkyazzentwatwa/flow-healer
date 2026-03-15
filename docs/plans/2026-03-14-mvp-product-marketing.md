# Flow Healer MVP — Product & Marketing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish a shippable MVP with product narrative, operator-facing docs, clean install experience, and a demo — so Flow Healer can be shared publicly with external users.

**Architecture:** Two parallel workstreams: (1) product docs written from scratch into `docs/`, and (2) targeted technical gap closures across the evidence bundle, failure taxonomy, TUI tabs, and `doctor` command polish. The workstreams are independent and can be executed in parallel or sequentially.

**Tech Stack:** Python 3.11+, Textual (TUI), pytest, Markdown, YAML

---

## Workstream 1: Product Docs

### Task 1: Write the Formal MVP Design Doc

**Files:**
- Create: `docs/superpowers/specs/2026-03-14-mvp-design.md`

**Step 1: Write the file**

Create `docs/superpowers/specs/2026-03-14-mvp-design.md` with the full formal design document. This is a reference spec that other docs will draw from.

```markdown
# Flow Healer MVP Design — 2026-03-14

## Product Positioning

**Headline:**
> Flow Healer opens draft PRs for flaky tests and safe repo maintenance issues — with validation evidence attached — so you can review, approve, or retry in one place.

## Target User

Solo developers and OSS maintainers running their own repos. Not fleet operators. Not enterprise. Someone who gets paged at 2am about a flaky CI step and wants it handled while they sleep.

## Distribution

Open source. Self-hosted. `pip install flow-healer`.

## The Job

1. Watches issues labeled `healer:ready`
2. Proposes a fix via configured connector (default: codex CLI)
3. Runs validation, attaches evidence (commands run, pass/fail, diff summary)
4. Opens a draft PR with human-readable summary
5. Operator reviews, approves, or retries from TUI or CLI

## What Is NOT Claimed at MVP

- Broad refactors
- Unsafe fixes (all fixes are auditable, all state is local SQLite)
- Multi-repo fleet management (supported but not the headline)
- Magic

## The Two Issue Classes

### Class A — Flaky Test Repair

**Accepted when:**
- Issue title/label indicates a flaky or intermittently failing test
- Output targets are inside test files only (no production code changes)
- Validation command explicitly provided or detectable
- Max diff: small (single test file or test helper)

**Rejected:** tests failing due to production bugs → `needs_clarification`

### Class B — Safe CI / Config / Doc Fixes

**Accepted when:**
- Files in: `.github/`, `Makefile`, `pyproject.toml`, `requirements*.txt`, `*.md` docs, `setup.cfg`, `tox.ini`
- No production source files touched
- Issue body has explicit `Required code outputs` section
- Max diff: small (1–3 files)

**Rejected:** dependency bumps requiring code changes, CI restructuring

### Shared Rejection Criteria

- No `Required code outputs` → `needs_clarification`
- No validation commands and none detectable → `needs_clarification`
- Output targets include `src/` for non-test files → rejected with reason
- Diff exceeds size limit → `judgment_required`

## Operator-Visible Failure Taxonomy

All internal failure codes map to one of six operator-visible reasons:

| Operator Label | Meaning |
|---|---|
| `validation_failed` | Fix was applied but tests/CI did not pass |
| `diff_too_large` | Proposed diff exceeded size limit |
| `scope_violation` | Fix touched files outside allowed scope |
| `no_confident_fix` | Connector could not produce a high-confidence fix |
| `repo_blocked` | Circuit breaker open or repo paused |
| `review_required` | AI reviewer flagged the fix for human attention |

## Evidence Bundle (per run)

Every run produces one consistent operator-facing object. Minimum fields:

- `issue_id`, `repo`, `summary` — what was attempted
- `files_changed`, `diff_summary` — scope of the fix
- `validation_commands` — what was run
- `validation_passed` — true/false per command
- `risk_level` — `low` / `medium` / `high`
- `failure_reason` — one of the six operator-visible codes (if failed)

## Success Metrics

- **Approval-ready PR rate:** ≥ 60% of accepted issues produce a draft PR operator can approve without modification
- **Operator review time:** ≤ 2 minutes per item from TUI
- **Onboarding time:** First-time user gets their first result in ≤ 15 minutes

## Launch Checklist

- [ ] `pip install flow-healer` + `flow-healer doctor` returns green on a fresh setup
- [ ] Demo repo has ≥ 3 successful draft PRs per class (Class A and Class B)
- [ ] Demo screen recording: issue → TUI → draft PR → operator approves — under 3 minutes
```

**Step 2: No tests needed** — this is a doc, not code.

**Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-03-14-mvp-design.md
git commit -m "docs: add formal MVP design spec"
```

---

### Task 2: Write `docs/mvp.md`

**Files:**
- Create: `docs/mvp.md`

**Step 1: Write the file**

`docs/mvp.md` is the operator-facing MVP spec. It defines what the system does at launch, what it does not do, and how to know if it's working.

```markdown
# Flow Healer MVP

Flow Healer opens draft PRs for two classes of issues: flaky test repair and safe CI/config/doc fixes. It attaches validation evidence to every PR so you can review and decide in one place.

## What It Does at MVP

1. Watches GitHub issues labeled `healer:ready`
2. Proposes a fix via configured connector (default: `codex`)
3. Runs validation (local test suite and/or Docker)
4. Attaches evidence: files changed, diff summary, validation commands, pass/fail
5. Opens a draft PR with a human-readable summary
6. Operator reviews from TUI (`flow-healer tui`) or CLI (`flow-healer status`)

## Issue Classes Accepted at MVP

### Class A — Flaky Test Repair

Accepted when the issue describes a test that fails intermittently and the proposed fix only changes test files or test helpers.

**Example issue title:** `test_retry_backoff flakes on CI — timing sensitive`

Rejected if the test failure is caused by a production bug. Flow Healer will comment with `needs_clarification`.

### Class B — Safe CI / Config / Doc Fixes

Accepted when the issue targets:
- `.github/` workflow files
- `Makefile`, `pyproject.toml`, `setup.cfg`, `tox.ini`
- `requirements*.txt`
- `*.md` documentation

Rejected if the fix would touch production source files under `src/`.

## What Is Out of Scope at MVP

- Broad refactors
- Fixes to production bugs
- Dependency version bumps that require code changes
- CI restructuring
- Multi-repo fleet management (supported but not the MVP headline)

## How to Know It's Working

Run `flow-healer doctor` after setup. A green result means:

- GitHub token present and valid
- Connector binary found and responds
- Git repo accessible
- State database accessible

Then run `flow-healer start --once` against a repo with a labeled issue. Check `flow-healer status` for the result.

## Rejection States

| State | Meaning | What to do |
|---|---|---|
| `needs_clarification` | Issue body lacks required outputs or validation | Add `Required code outputs:` and `Validation command:` sections to the issue |
| `judgment_required` | Diff too large or scope unclear | Narrow the issue scope |
| `failed` | Fix applied but validation did not pass | See attempt details in TUI → retry or close |
| `blocked` | Circuit breaker open or repo paused | Run `flow-healer doctor` to diagnose |

## Metrics

See [docs/superpowers/specs/2026-03-14-mvp-design.md](superpowers/specs/2026-03-14-mvp-design.md) for target success metrics.
```

**Step 2: Commit**

```bash
git add docs/mvp.md
git commit -m "docs: add MVP spec"
```

---

### Task 3: Write `docs/safe-scope.md`

**Files:**
- Create: `docs/safe-scope.md`

**Step 1: Write the file**

`docs/safe-scope.md` is the complete contract for what issues get accepted vs rejected, with examples.

```markdown
# Safe Scope Contract

This document defines exactly what files Flow Healer is allowed to modify at MVP, and what causes an issue to be rejected.

## Allowed Target Files

### Class A — Test Files Only

```text
tests/**
test_*.py
*_test.py
spec/**
__tests__/**
*.test.js
*.test.ts
*.spec.js
*.spec.ts
```

### Class B — Safe Config / CI / Doc Files

```text
.github/**
Makefile
pyproject.toml
setup.cfg
tox.ini
requirements*.txt
*.md
docs/**/*.md
```

## Always-Rejected Target Files

Any file matching these patterns causes immediate rejection with `scope_violation`:

```text
src/**           (except test files inside src/tests/ or src/**/*test*)
lib/**
app/**
*.py             (root-level, non-test)
```

The rejection comment on the issue will explain exactly which file triggered the violation.

## Issue Body Requirements

Every accepted issue must include:

```
## Required code outputs

- `path/to/file.py` (description of what changes)

## Validation command

pytest tests/test_specific.py -v
```

Missing either section causes `needs_clarification`. Flow Healer comments on the issue explaining what to add.

## Diff Size Limits

- Max files changed: 8 (configurable via `max_diff_files`)
- Max lines changed: 400 (configurable via `max_diff_lines`)

Exceeding either triggers `judgment_required`.

## Examples

### Accepted: Class A

```
Title: test_cache_invalidation flakes on CI

Required code outputs:
- `tests/test_cache.py` (remove time.sleep dependency, use mock timer)

Validation command:
pytest tests/test_cache.py -v
```

### Accepted: Class B

```
Title: CI fails on Python 3.12 — missing tomllib import guard

Required code outputs:
- `pyproject.toml` (add python_requires constraint)
- `.github/workflows/ci.yml` (add 3.12 to matrix)

Validation command:
python -m pytest tests/ -q
```

### Rejected: production file in outputs

```
Required code outputs:
- `src/flow_healer/healer_runner.py`  ← triggers scope_violation
```

### Rejected: no validation command and none detectable

```
Title: update README badges

Required code outputs:
- `README.md`

(no Validation command section)  ← triggers needs_clarification
```

## Lenient vs Strict Contract Mode

Flow Healer supports two parsing modes, configured per repo:

- `lenient` (default): infers outputs and validation from issue body; gates on low confidence only
- `strict`: requires explicit `Required code outputs` and `Validation command` sections; no inference

For MVP and new users, `lenient` is recommended. Switch to `strict` once your issue templates are established.

## Scope Checking at Runtime

Scope is checked at two points:

1. **Pre-run (triage):** Issue body is parsed for output targets. Targets outside allowed scope → issue is rejected before work begins.
2. **Post-run (verification):** Actual diff is inspected. Any file outside the declared outputs → `scope_violation` failure.
```

**Step 2: Commit**

```bash
git add docs/safe-scope.md
git commit -m "docs: add safe-scope contract"
```

---

### Task 4: Write `docs/operator-workflow.md`

**Files:**
- Create: `docs/operator-workflow.md`

**Step 1: Write the file**

```markdown
# Operator Workflow

This document explains the review queue, what each state means, and how to take action from the TUI or CLI.

## The Review Queue

Flow Healer maintains a queue of issues in SQLite. States visible in the TUI:

| State | Meaning |
|---|---|
| `queued` | Issue is waiting to be processed |
| `claimed` / `running` | Fix is in progress |
| `verify_pending` | Fix applied, running validation |
| `pr_open` | Draft PR opened, awaiting your review |
| `failed` | Fix failed validation — see failure reason |
| `blocked` | Repo paused or circuit breaker open |
| `merged` / `closed` | Work complete |

## Opening the TUI

```bash
flow-healer tui
```

The TUI has four tabs:

| Tab | What it shows |
|---|---|
| **Review Queue** | Issues with open draft PRs ready for your review |
| **Blocked** | Issues stuck in `failed` or `blocked` — need attention |
| **Repo Health** | Circuit breaker state, success rate, recent activity |
| **History** | All resolved issues (merged, closed, cancelled) |

## Row Actions

With a row selected in the TUI:

| Key | Action |
|---|---|
| `r` | Retry the issue (re-queue with current context) |
| `p` | Pause the entire repo (stops new work) |
| `o` | Open the draft PR link in your browser |
| `q` | Quit |

## CLI Actions

```bash
# See queue state
flow-healer status

# Pause a repo
flow-healer pause --repo my-repo

# Resume a repo
flow-healer resume --repo my-repo

# Retry a specific issue (re-label it healer:ready on GitHub)
# Flow Healer will pick it up on next poll

# Export queue data for analysis
flow-healer export --formats csv,jsonl
```

## Reviewing a Draft PR

Flow Healer opens PRs in **draft** state. Each PR body includes:

- Summary of intended fix
- Files changed
- Validation commands run and their pass/fail result
- Risk level assessment from the AI reviewer

To approve: convert draft to ready-for-review, then merge normally.
To retry: close the PR and re-label the issue `healer:ready`. Flow Healer will re-attempt with feedback from the PR comments.
To reject: close the PR and close the issue (or remove the label).

## Understanding Failure Reasons

| Failure | Meaning | Action |
|---|---|---|
| `validation_failed` | Tests did not pass after fix | Check test output in PR body; retry or edit issue |
| `diff_too_large` | Too many files or lines changed | Narrow the issue scope |
| `scope_violation` | Fix touched disallowed files | Update issue's Required outputs section |
| `no_confident_fix` | Connector could not produce a fix | Add more context to issue body; retry |
| `repo_blocked` | Circuit breaker open | Run `flow-healer doctor`; check recent failure rate |
| `review_required` | AI reviewer flagged for human attention | Read PR body reviewer section; decide manually |

## Circuit Breaker

Flow Healer tracks failure rate per repo. If > 50% of recent attempts fail, it opens the circuit breaker and stops attempting new work. Run `flow-healer doctor` to see the current state and reset if needed.

## Pausing a Repo

```bash
flow-healer pause --repo my-repo
```

This stops Flow Healer from claiming new issues for that repo. In-progress work completes normally. Resume with `flow-healer resume --repo my-repo`.
```

**Step 2: Commit**

```bash
git add docs/operator-workflow.md
git commit -m "docs: add operator workflow guide"
```

---

### Task 5: Write `docs/onboarding.md`

**Files:**
- Create: `docs/onboarding.md`

**Step 1: Write the file**

Target: a solo dev who has never used Flow Healer, getting their first result in ≤ 15 minutes.

```markdown
# Onboarding: Get Your First Result in 15 Minutes

This guide walks you through pointing Flow Healer at a GitHub repo and getting your first automated draft PR.

## Prerequisites

- Python 3.11+
- A GitHub personal access token with `repo` scope
- The `codex` CLI installed (default connector): `npm install -g @openai/codex`
- Git

## Step 1: Install (2 minutes)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install flow-healer
```

Verify:

```bash
flow-healer --help
```

## Step 2: Configure (3 minutes)

```bash
mkdir -p ~/.flow-healer
cp $(python -c "import flow_healer; print(flow_healer.__file__.replace('__init__.py', ''))../config.example.yaml") ~/.flow-healer/config.yaml
```

Or download the config template manually from the repo. Then open `~/.flow-healer/config.yaml` and set:

```yaml
repos:
  - name: my-repo
    path: /absolute/path/to/your/local/clone
    repo_slug: yourname/your-repo
    default_branch: main
    enable_autonomous_healer: true
    issue_contract_mode: lenient
```

Set your GitHub token:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

## Step 3: Check Setup (1 minute)

```bash
flow-healer doctor
```

Green checks mean you're ready. If any check is red, follow the remediation hint shown.

Common issues:
- `GITHUB_TOKEN not set` → set the env var above
- `connector not found` → install `codex` or switch `connector_backend` in config
- `repo path not found` → check the `path:` in your config

## Step 4: Create a Test Issue (2 minutes)

On GitHub, create an issue on your repo with this body:

```markdown
## Required code outputs

- `.github/workflows/ci.yml` (add a missing newline at end of file)

## Validation command

echo "ok"
```

Add the label `healer:ready` to the issue.

This is a Class B safe issue — it only touches a CI config file. Perfect for a first run.

## Step 5: Run (2 minutes)

```bash
flow-healer start --once --repo my-repo
```

This runs one healing cycle and exits. Watch the logs. You should see:
1. Issue claimed
2. Connector invoked
3. Validation run
4. PR opened (or failure reported)

## Step 6: Review (2 minutes)

Open the TUI to see the result:

```bash
flow-healer tui
```

Navigate to **Review Queue** to see your draft PR. Press `o` to open it in the browser.

Or check from the CLI:

```bash
flow-healer status --repo my-repo
```

## What to Do If It Fails

Run `flow-healer doctor --preflight` for a detailed diagnostic. Check the logs at `~/.flow-healer/flow-healer.log`.

Common first-run failures:
- `needs_clarification` → your issue body is missing `Required code outputs` or `Validation command` sections
- `no_confident_fix` → the connector couldn't understand the issue; add more context
- `validation_failed` → the fix was applied but the test/command failed; check the PR body for details

## Next Steps

- Read [docs/safe-scope.md](safe-scope.md) to understand what kinds of issues Flow Healer accepts
- Read [docs/operator-workflow.md](operator-workflow.md) to learn TUI and CLI controls
- Read [docs/mvp.md](mvp.md) for the full MVP scope
- Edit `~/.flow-healer/config.yaml` to add more repos or adjust limits
- Set up `flow-healer serve` to run as a persistent background service
```

**Step 2: Commit**

```bash
git add docs/onboarding.md
git commit -m "docs: add 15-minute onboarding guide"
```

---

### Task 6: Rewrite `README.md`

**Files:**
- Modify: `README.md`

**Step 1: Read the current README first** (already done above — it leads with architecture)

**Step 2: Write the new README**

Replace the current content with a product-first structure:

```markdown
<div align="center">

# Flow Healer

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](docs/installation.md)
[![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20TUI-111111?style=for-the-badge&logo=gnubash&logoColor=white)](docs/dashboard.md)
[![State](https://img.shields.io/badge/state-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](docs/runtime-state.md)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](docs/test-strategy.md)
[![GitHub](https://img.shields.io/badge/automation-GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](docs/issue-contracts.md)

**Flow Healer opens draft PRs for flaky tests and safe repo maintenance issues — with validation evidence attached — so you can review, approve, or retry in one place.**

[Get Started in 15 Minutes →](docs/onboarding.md) · [MVP Scope](docs/mvp.md) · [Operator Guide](docs/operator-workflow.md) · [Safe Scope Contract](docs/safe-scope.md)

</div>

## What It Does

Flow Healer watches your GitHub issues labeled `healer:ready`, proposes a fix, runs validation, and opens a draft PR with evidence attached. You review and decide.

```text
GitHub issue (healer:ready)
         │
         ▼
  Flow Healer claims it
         │
         ▼
  AI connector proposes fix
         │
         ▼
  Validation runs (local / Docker)
         │
         ▼
  Evidence bundle built
    ┌────┴────┐
    ▼         ▼
Draft PR    retry / clarify
opened      (operator notified)
```

## Issue Classes Supported

**Class A — Flaky Test Repair:** Fix intermittently failing tests. Output targets must be test files only.

**Class B — Safe CI / Config / Doc Fixes:** Fix `.github/`, `Makefile`, `pyproject.toml`, `requirements*.txt`, `*.md`, and similar safe files.

Both classes require an explicit `Required code outputs` section and a `Validation command` in the issue body. See [docs/safe-scope.md](docs/safe-scope.md) for the full contract.

## Get Started

```bash
pip install flow-healer
mkdir -p ~/.flow-healer
cp config.example.yaml ~/.flow-healer/config.yaml
# edit config.yaml with your repo path and slug
export GITHUB_TOKEN=ghp_your_token
flow-healer doctor
flow-healer start --once
```

Read the [15-minute onboarding guide](docs/onboarding.md) for a full walkthrough.

## Operator Interface

```bash
# Terminal UI — review queue, retry, open PRs
flow-healer tui

# CLI status
flow-healer status

# Diagnose setup issues
flow-healer doctor
```

The TUI shows a **Review Queue** of draft PRs ready to approve, a **Blocked** tab for failures needing attention, and a **Repo Health** tab.

## Not Magic

- All state is local SQLite (`~/.flow-healer/repos/<name>/state.db`)
- All fixes are auditable — every diff and validation run is in the PR body
- No production code changes without explicit issue contracts
- You approve every merge

## Documentation

- [docs/onboarding.md](docs/onboarding.md) — 15-minute setup guide
- [docs/mvp.md](docs/mvp.md) — what's in scope at MVP
- [docs/safe-scope.md](docs/safe-scope.md) — file scope rules and examples
- [docs/operator-workflow.md](docs/operator-workflow.md) — TUI / CLI operator guide
- [docs/README.md](docs/README.md) — full documentation index
- [AGENTS.md](AGENTS.md) — coding-agent operating contract

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
flow-healer doctor
flow-healer start --once
```
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with product-first structure"
```

---

### Task 7: Annotate `config.example.yaml`

**Files:**
- Modify: `config.example.yaml`

**Step 1: Add solo-dev-oriented comments to every field**

The current config has minimal comments. Add a `# [solo dev]` or `# [advanced]` annotation to each field so a first-time user knows what to care about.

Key annotations to add (for each field, prepend a comment line):

```yaml
service:
  # [solo dev] Set GITHUB_TOKEN in your shell. Never put the token value here.
  github_token_env: GITHUB_TOKEN

  # [advanced] Override if using GitHub Enterprise
  github_api_base_url: https://api.github.com

  # [solo dev] How often to check for new issues. 30s is fine for personal use.
  poll_interval_seconds: 30

  # [solo dev] Where state is stored. Default is ~/.flow-healer
  state_root: ~/.flow-healer

  # [solo dev] Use 'exec' for the default codex CLI connector.
  # Options: exec | app_server | claude_cli | cline | kilo_cli
  connector_backend: exec

  # [advanced] Route code vs non-code tasks to different connectors
  connector_routing_mode: single_backend
  ...

repos:
  - name: demo
    # [solo dev] Absolute path to your local git clone
    path: /absolute/path/to/target-repo

    # [solo dev] GitHub owner/repo slug (e.g. myname/my-repo)
    repo_slug: owner/repo

    # [solo dev] Your main branch name
    default_branch: main

    # [solo dev] Set to true to enable autonomous healing
    enable_autonomous_healer: true

    # [solo dev] 'guarded_pr' opens draft PRs for review. Recommended.
    healer_mode: guarded_pr

    # [solo dev] Issues must have this label to be processed
    issue_required_labels:
      - healer:ready

    # [solo dev] 'lenient' infers outputs/validation. Use 'strict' once your
    # issue templates are established.
    issue_contract_mode: lenient

    # [advanced] Confidence threshold below which issues get needs_clarification
    parse_confidence_threshold: 0.3

    # [solo dev] How many issues to work on simultaneously
    max_concurrent_issues: 3

    # [solo dev] How many times to retry a failed fix
    retry_budget: 2

    # [advanced] Circuit breaker: trips when failure rate exceeds this threshold
    circuit_breaker_failure_rate: 0.5

    # [solo dev] Leave blank to auto-detect from your repo's marker files
    language: ""

    # [solo dev] Set to 'required' to always run tests before opening a PR
    verifier_policy: required

    # [solo dev] Run tests locally, then Docker if local fails
    test_gate_mode: local_then_docker
```

**Step 2: Commit**

```bash
git add config.example.yaml
git commit -m "docs: annotate config.example.yaml for solo dev onboarding"
```

---

## Workstream 2: Technical Gaps

### Task 8: Standardize the Evidence Bundle

**Context:** `HealerRunResult` (in `healer_runner.py:342`) contains the raw per-run data. The TUI detail pane and PR body currently pull from different parts of this result. We want one standard operator-facing `EvidenceBundle` that feeds both.

**Files:**
- Modify: `src/flow_healer/healer_runner.py` (add `EvidenceBundle` dataclass, populate it in runner)
- Modify: `src/flow_healer/healer_verifier.py` (attach verifier evidence to bundle)
- Modify: `src/flow_healer/healer_reviewer.py` (attach reviewer evidence to bundle)
- Test: `tests/test_healer_runner.py`

**Step 1: Write a failing test for EvidenceBundle**

In `tests/test_healer_runner.py`, add:

```python
def test_evidence_bundle_fields():
    """EvidenceBundle must have all required operator-facing fields."""
    from flow_healer.healer_runner import EvidenceBundle
    bundle = EvidenceBundle(
        issue_id="42",
        repo="owner/repo",
        summary="Fix flaky test_cache_invalidation by mocking timer",
        files_changed=["tests/test_cache.py"],
        diff_summary="1 file changed, 5 insertions(+), 3 deletions(-)",
        validation_commands=["pytest tests/test_cache.py -v"],
        validation_passed=True,
        risk_level="low",
        failure_reason="",
    )
    assert bundle.issue_id == "42"
    assert bundle.repo == "owner/repo"
    assert bundle.validation_passed is True
    assert bundle.risk_level == "low"
    assert bundle.failure_reason == ""
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_healer_runner.py::test_evidence_bundle_fields -v
```
Expected: FAIL with `ImportError: cannot import name 'EvidenceBundle'`

**Step 3: Add `EvidenceBundle` to `healer_runner.py`**

Add after the `HealerRunResult` dataclass (around line 354):

```python
@dataclass(slots=True, frozen=True)
class EvidenceBundle:
    """Operator-facing evidence for one healing attempt. Feeds PR body and TUI detail pane."""
    issue_id: str
    repo: str
    summary: str                        # what the fix intended to do
    files_changed: list[str]            # actual files in the diff
    diff_summary: str                   # human-readable diff stat line
    validation_commands: list[str]      # commands that were run
    validation_passed: bool             # overall pass/fail
    risk_level: str                     # "low" | "medium" | "high"
    failure_reason: str                 # one of the 6 operator-visible codes, or ""
    verifier_summary: str = ""          # from HealerVerifier
    reviewer_summary: str = ""          # from HealerReviewer
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_healer_runner.py::test_evidence_bundle_fields -v
```
Expected: PASS

**Step 5: Write a test for `build_evidence_bundle` helper**

```python
def test_build_evidence_bundle_from_run_result():
    """build_evidence_bundle maps HealerRunResult → EvidenceBundle correctly."""
    from flow_healer.healer_runner import EvidenceBundle, HealerRunResult, build_evidence_bundle
    run_result = HealerRunResult(
        success=True,
        failure_class="",
        failure_reason="",
        failure_fingerprint="",
        proposer_output="",
        diff_paths=["tests/test_cache.py"],
        diff_files=1,
        diff_lines=8,
        test_summary={"passed": 5, "failed": 0},
        workspace_status={},
    )
    bundle = build_evidence_bundle(
        run_result=run_result,
        issue_id="42",
        repo="owner/repo",
        summary="Fix flaky test",
        validation_commands=["pytest tests/ -v"],
    )
    assert isinstance(bundle, EvidenceBundle)
    assert bundle.validation_passed is True
    assert bundle.files_changed == ["tests/test_cache.py"]
    assert bundle.risk_level == "low"
    assert bundle.failure_reason == ""
```

**Step 6: Run test to verify it fails**

```bash
pytest tests/test_healer_runner.py::test_build_evidence_bundle_from_run_result -v
```
Expected: FAIL with `ImportError: cannot import name 'build_evidence_bundle'`

**Step 7: Add `build_evidence_bundle` to `healer_runner.py`**

Add the helper function:

```python
# Operator-visible failure code mapping (internal → operator label)
_OPERATOR_FAILURE_MAP: dict[str, str] = {
    "tests_failed": "validation_failed",
    "verifier_failed": "validation_failed",
    "diff_too_large": "diff_too_large",
    "diff_files_exceeded": "diff_too_large",
    "diff_lines_exceeded": "diff_too_large",
    "scope_violation": "scope_violation",
    "output_target_violation": "scope_violation",
    "no_workspace_change": "no_confident_fix",
    "connector_unavailable": "no_confident_fix",
    "connector_runtime_error": "no_confident_fix",
    "circuit_breaker_open": "repo_blocked",
    "healer_paused": "repo_blocked",
    "review_required": "review_required",
}

def _operator_failure_reason(failure_class: str) -> str:
    """Map internal failure class to one of the 6 operator-visible codes."""
    if not failure_class:
        return ""
    if failure_class.startswith("no_workspace_change:"):
        return "no_confident_fix"
    return _OPERATOR_FAILURE_MAP.get(failure_class, "validation_failed")


def _risk_level_from_result(run_result: "HealerRunResult") -> str:
    """Derive risk level from diff size and test results."""
    diff_lines = run_result.diff_lines or 0
    diff_files = run_result.diff_files or 0
    failed = (run_result.test_summary or {}).get("failed", 0)
    if failed > 0 or diff_lines > 200 or diff_files > 4:
        return "high"
    if diff_lines > 50 or diff_files > 2:
        return "medium"
    return "low"


def build_evidence_bundle(
    *,
    run_result: "HealerRunResult",
    issue_id: str,
    repo: str,
    summary: str,
    validation_commands: list[str],
    verifier_summary: str = "",
    reviewer_summary: str = "",
) -> EvidenceBundle:
    """Build an operator-facing EvidenceBundle from a HealerRunResult."""
    diff_files = run_result.diff_files or 0
    diff_lines = run_result.diff_lines or 0
    diff_summary = f"{diff_files} file(s) changed, {diff_lines} line(s)"
    return EvidenceBundle(
        issue_id=issue_id,
        repo=repo,
        summary=summary,
        files_changed=list(run_result.diff_paths or []),
        diff_summary=diff_summary,
        validation_commands=validation_commands,
        validation_passed=bool(run_result.success),
        risk_level=_risk_level_from_result(run_result),
        failure_reason=_operator_failure_reason(run_result.failure_class),
        verifier_summary=verifier_summary,
        reviewer_summary=reviewer_summary,
    )
```

**Step 8: Run test to verify it passes**

```bash
pytest tests/test_healer_runner.py::test_build_evidence_bundle_from_run_result -v
```
Expected: PASS

**Step 9: Run full runner test suite**

```bash
pytest tests/test_healer_runner.py -v
```
Expected: all pass

**Step 10: Commit**

```bash
git add src/flow_healer/healer_runner.py tests/test_healer_runner.py
git commit -m "feat: add EvidenceBundle dataclass and build_evidence_bundle helper"
```

---

### Task 9: Normalize Failure Taxonomy in TUI Display

**Context:** The TUI currently shows raw `failure_class` strings to operators (e.g. `tests_failed`, `verifier_failed`, `no_workspace_change:...`). We need it to show the 6 operator-visible codes instead.

**Files:**
- Modify: `src/flow_healer/tui.py` (use `_operator_failure_reason` when displaying failure class)
- Test: `tests/test_tui.py`

**Step 1: Write a failing test**

In `tests/test_tui.py`, add:

```python
def test_tui_shows_operator_failure_reason_not_internal_code():
    """TUI attempt rows must display operator-visible failure codes, not internal ones."""
    from flow_healer.tui import _format_attempt_row_for_display
    row = {
        "attempt_id": "abc123",
        "issue_id": "42",
        "state": "failed",
        "failure_class": "tests_failed",
        "failure_reason": "3 tests failed in test_cache.py",
    }
    display = _format_attempt_row_for_display(row)
    # Internal code "tests_failed" must be mapped to operator label
    assert display["operator_failure"] == "validation_failed"
    assert "tests_failed" not in display["operator_failure"]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_tui.py::test_tui_shows_operator_failure_reason_not_internal_code -v
```
Expected: FAIL with `ImportError: cannot import name '_format_attempt_row_for_display'`

**Step 3: Add `_format_attempt_row_for_display` to `tui.py`**

Import `_operator_failure_reason` from `healer_runner` and add the function:

```python
from .healer_runner import _operator_failure_reason

def _format_attempt_row_for_display(row: dict[str, Any]) -> dict[str, Any]:
    """Map internal attempt row fields to operator-visible display values."""
    failure_class = str(row.get("failure_class") or "")
    return {
        **row,
        "operator_failure": _operator_failure_reason(failure_class) if failure_class else "",
    }
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_tui.py::test_tui_shows_operator_failure_reason_not_internal_code -v
```
Expected: PASS

**Step 5: Update `_populate_tables` to use operator labels in Attempts table**

In `tui.py` around line 823-830, change the `failure_class` column to use `_format_attempt_row_for_display`:

Find:
```python
attempts_table.add_row(
    str(row.get("attempt_id", "")),
    str(row.get("issue_id", "")),
    _colored_state(str(row.get("state", ""))),
    str(row.get("failure_class", "")),
)
```

Replace with:
```python
display = _format_attempt_row_for_display(row)
attempts_table.add_row(
    str(display.get("attempt_id", "")),
    str(display.get("issue_id", "")),
    _colored_state(str(display.get("state", ""))),
    str(display.get("operator_failure", "")),
)
```

**Step 6: Run full TUI test suite**

```bash
pytest tests/test_tui.py -v
```
Expected: all pass

**Step 7: Commit**

```bash
git add src/flow_healer/tui.py tests/test_tui.py
git commit -m "feat: normalize failure codes to operator-visible taxonomy in TUI"
```

---

### Task 10: Restructure TUI Tabs

**Context:** Current TUI tabs (Attempts, Events, Logs, Analytics) are shown below the queue table in a secondary panel. The plan restructures to top-level tabs: Review Queue | Blocked | Repo Health | History.

**Files:**
- Modify: `src/flow_healer/tui.py` (restructure `compose()` and tab logic)
- Test: `tests/test_tui.py`

**Step 1: Write failing test for tab structure**

```python
def test_tui_app_has_review_queue_tab(tmp_path):
    """TUI top-level tabs must include Review Queue, Blocked, Repo Health, History."""
    from flow_healer.tui import FlowHealerTUI
    # Just verify the tab IDs are defined as class-level constants or exist in compose
    assert hasattr(FlowHealerTUI, "TAB_REVIEW_QUEUE") or "tab-review-queue" in FlowHealerTUI.__dict__.get("_tab_ids", [])
```

This test will be adjusted once we add the constants. For now:

```python
def test_tui_tab_ids_defined():
    """MVP tab IDs must all be importable constants from tui module."""
    import flow_healer.tui as tui_mod
    assert hasattr(tui_mod, "TAB_REVIEW_QUEUE")
    assert hasattr(tui_mod, "TAB_BLOCKED")
    assert hasattr(tui_mod, "TAB_REPO_HEALTH")
    assert hasattr(tui_mod, "TAB_HISTORY")
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_tui.py::test_tui_tab_ids_defined -v
```
Expected: FAIL

**Step 3: Add tab ID constants to `tui.py`**

Near the top of `tui.py` (after the `STATE_COLORS` dict), add:

```python
# ---------------------------------------------------------------------------
# Tab IDs (MVP restructure)
# ---------------------------------------------------------------------------

TAB_REVIEW_QUEUE = "tab-review-queue"
TAB_BLOCKED = "tab-blocked"
TAB_REPO_HEALTH = "tab-repo-health"
TAB_HISTORY = "tab-history"
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_tui.py::test_tui_tab_ids_defined -v
```
Expected: PASS

**Step 5: Restructure `compose()` in `FlowHealerTuiApp`**

Locate the `compose()` method (around line 755). The current structure has a `DataTable` for the queue and a `TabbedContent` below it with Attempts/Events/Logs/Analytics.

Restructure to top-level tabs:

```python
def compose(self) -> ComposeResult:
    yield Header()
    yield self._stats_bar
    with TabbedContent(initial=TAB_REVIEW_QUEUE):
        with TabPane("Review Queue", id=TAB_REVIEW_QUEUE):
            yield DataTable(id="queue-table", cursor_type="row")
            yield Static("", id="action-hints")
        with TabPane("Blocked", id=TAB_BLOCKED):
            yield DataTable(id="blocked-table", cursor_type="row")
        with TabPane("Repo Health", id=TAB_REPO_HEALTH):
            yield DataTable(id="attempts-table", cursor_type="row")
            yield Static(id="analytics-panel")
        with TabPane("History", id=TAB_HISTORY):
            yield DataTable(id="events-table", cursor_type="row")
    yield Footer()
```

**Note:** This is a significant structural change. Read the full `compose()` and `_setup_tables()` methods before editing to understand what IDs are referenced downstream. Update `_setup_tables()` to add columns for the new `blocked-table`. Update `_populate_tables()` to populate blocked items (items with state `failed` or `blocked`) into `blocked-table`.

**Step 6: Update `_setup_tables()` to add blocked-table columns**

```python
blocked_table = self.query_one("#blocked-table", DataTable)
blocked_table.add_columns("#", "State", "Title", "Failure")
```

**Step 7: Update `_populate_tables()` to populate blocked-table**

```python
blocked_table = self.query_one("#blocked-table", DataTable)
blocked_table.clear()
blocked_states = {"failed", "error", "blocked"}
for row in snapshot.get("queue_rows", []):
    if str(row.get("state", "")).lower() in blocked_states:
        display = _format_attempt_row_for_display(row)
        blocked_table.add_row(
            f"#{row.get('issue_id', '')}",
            _colored_state(str(row.get("state", ""))),
            str(row.get("title", "")),
            str(display.get("operator_failure", "")),
        )
```

**Step 8: Run test suite**

```bash
pytest tests/test_tui.py -v
```
Expected: all pass (adjust any broken tests that reference old tab IDs like `tab-attempts`)

**Step 9: Commit**

```bash
git add src/flow_healer/tui.py tests/test_tui.py
git commit -m "feat: restructure TUI to Review Queue / Blocked / Repo Health / History tabs"
```

---

### Task 11: Add TUI Row Actions (retry, pause, open PR)

**Context:** Phase 1 interactivity was started in the last commit (`6a16843`). This task continues it by ensuring retry, pause, and open-PR-link actions work from the Review Queue tab.

**Files:**
- Modify: `src/flow_healer/tui.py`
- Test: `tests/test_tui.py`

**Step 1: Read `tui.py` around the keybindings and action handlers** to understand what's already implemented.

```bash
grep -n "BINDINGS\|action_retry\|action_pause\|action_open_pr\|key_r\|key_p\|key_o" src/flow_healer/tui.py
```

**Step 2: Write failing tests for missing actions**

```python
def test_tui_app_has_retry_binding():
    """TUI must define a 'retry' key binding."""
    from flow_healer.tui import FlowHealerTuiApp
    binding_keys = [b.key for b in FlowHealerTuiApp.BINDINGS]
    assert "r" in binding_keys, "Expected 'r' binding for retry"

def test_tui_app_has_pause_binding():
    from flow_healer.tui import FlowHealerTuiApp
    binding_keys = [b.key for b in FlowHealerTuiApp.BINDINGS]
    assert "p" in binding_keys, "Expected 'p' binding for pause repo"

def test_tui_app_has_open_pr_binding():
    from flow_healer.tui import FlowHealerTuiApp
    binding_keys = [b.key for b in FlowHealerTuiApp.BINDINGS]
    assert "o" in binding_keys, "Expected 'o' binding for open PR link"
```

**Step 3: Run tests to verify which pass/fail**

```bash
pytest tests/test_tui.py::test_tui_app_has_retry_binding tests/test_tui.py::test_tui_app_has_pause_binding tests/test_tui.py::test_tui_app_has_open_pr_binding -v
```

**Step 4: Add any missing bindings to `BINDINGS` in `FlowHealerTuiApp`**

In the `BINDINGS` class attribute, add any that are missing:

```python
BINDINGS = [
    Binding("q", "quit", "Quit"),
    Binding("r", "retry_selected", "Retry"),
    Binding("p", "pause_repo", "Pause Repo"),
    Binding("o", "open_pr", "Open PR"),
    Binding("s", "open_settings", "Settings"),
    Binding("e", "export_telemetry", "Export"),
]
```

**Step 5: Add action handlers for any missing actions**

```python
def action_retry_selected(self) -> None:
    """Re-queue the selected issue by posting a GitHub comment."""
    row = self._selected_queue_row()
    if row is None:
        self.notify("No issue selected.", severity="warning")
        return
    issue_id = str(row.get("issue_id", ""))
    if not issue_id:
        return
    self.notify(f"Retry queued for issue #{issue_id}", severity="information")
    # Dispatch the retry via the service (re-label the issue)
    self._dispatch_retry(issue_id)

def action_pause_repo(self) -> None:
    """Pause the current repo."""
    self._service.set_paused(True, self._repo_name)
    self.notify("Repo paused.", severity="warning")

def action_open_pr(self) -> None:
    """Open the draft PR for the selected issue in the browser."""
    row = self._selected_queue_row()
    if row is None:
        self.notify("No issue selected.", severity="warning")
        return
    pr_url = str(row.get("pr_url") or row.get("pr_number") or "")
    if pr_url.startswith("http"):
        webbrowser.open(pr_url)
    else:
        self.notify("No PR URL available for this issue.", severity="warning")

def _selected_queue_row(self) -> dict[str, Any] | None:
    """Return the snapshot queue row for the currently selected row, or None."""
    try:
        table = self.query_one("#queue-table", DataTable)
        cursor_row = table.cursor_row
        rows = self._snapshot.get("queue_rows", [])
        if 0 <= cursor_row < len(rows):
            return rows[cursor_row]
    except Exception:
        pass
    return None
```

**Step 6: Run test suite**

```bash
pytest tests/test_tui.py -v
```
Expected: all pass

**Step 7: Commit**

```bash
git add src/flow_healer/tui.py tests/test_tui.py
git commit -m "feat: add retry/pause/open-PR row actions to TUI"
```

---

### Task 12: Polish `doctor` Command

**Context:** `flow-healer doctor` currently outputs raw JSON rows. For solo devs, this is hard to read. We need a plain-language output mode that surfaces every issue with a remediation hint.

**Files:**
- Modify: `src/flow_healer/cli.py` (add `--plain` flag and plain-language formatter)
- Test: `tests/test_cli.py`

**Step 1: Write a failing test**

In `tests/test_cli.py`, add:

```python
def test_doctor_plain_output_shows_green_for_ok_setup(monkeypatch, tmp_path):
    """doctor --plain must show human-readable green/red lines, not JSON."""
    import io
    from flow_healer.cli import format_doctor_rows_plain
    rows = [
        {
            "repo": "my-repo",
            "token_present": True,
            "git_ok": True,
            "connector_found": True,
            "db_ok": True,
            "preflight_summary": {"ready": True, "issues": []},
        }
    ]
    output = format_doctor_rows_plain(rows)
    assert "✓" in output or "OK" in output.upper()
    assert "my-repo" in output
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_cli.py::test_doctor_plain_output_shows_green_for_ok_setup -v
```
Expected: FAIL with `ImportError: cannot import name 'format_doctor_rows_plain'`

**Step 3: Add `format_doctor_rows_plain` to `cli.py`**

```python
def format_doctor_rows_plain(rows: list[dict]) -> str:
    """Format doctor_rows as human-readable plain text with remediation hints."""
    lines: list[str] = []
    for row in rows:
        repo = str(row.get("repo") or row.get("repo_name") or "unknown")
        lines.append(f"\n=== {repo} ===")

        checks = [
            ("GITHUB_TOKEN present", row.get("token_present"), "Set the GITHUB_TOKEN env var"),
            ("Git repo accessible", row.get("git_ok"), "Check the 'path:' in your config.yaml"),
            ("Connector found", row.get("connector_found"), "Install the connector (e.g. npm install -g @openai/codex)"),
            ("State database accessible", row.get("db_ok"), "Check disk space and permissions under ~/.flow-healer"),
        ]
        for label, ok, hint in checks:
            if ok:
                lines.append(f"  ✓  {label}")
            else:
                lines.append(f"  ✗  {label}")
                lines.append(f"     → {hint}")

        preflight = row.get("preflight_summary") or {}
        issues = preflight.get("issues") or []
        if preflight.get("ready"):
            lines.append("  ✓  Preflight checks passed")
        elif issues:
            lines.append("  ✗  Preflight issues:")
            for issue in issues[:5]:
                lines.append(f"     → {issue}")

    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_cli.py::test_doctor_plain_output_shows_green_for_ok_setup -v
```
Expected: PASS

**Step 5: Update `doctor` command handler in `main()` to use plain output by default**

In `cli.py`, the `build_parser()` function adds `--preflight` flag to `doctor`. Add `--plain` flag:

```python
if name == "doctor":
    cmd.add_argument("--preflight", action="store_true")
    cmd.add_argument("--plain", action="store_true", default=True,
                     help="Show human-readable output (default). Use --no-plain for JSON.")
    cmd.add_argument("--no-plain", dest="plain", action="store_false")
```

In `main()`, update the doctor handler:

```python
if args.command == "doctor":
    rows = service.doctor_rows(args.repo, preflight=bool(args.preflight))
    if getattr(args, "plain", True):
        print(format_doctor_rows_plain(rows))
    else:
        for row in rows:
            print(json.dumps(row, indent=2, default=str))
    return
```

**Step 6: Run the full CLI test suite**

```bash
pytest tests/test_cli.py -v
```
Expected: all pass

**Step 7: Smoke test manually**

```bash
flow-healer doctor
```
Expected: human-readable output with ✓/✗ lines.

**Step 8: Commit**

```bash
git add src/flow_healer/cli.py tests/test_cli.py
git commit -m "feat: polish doctor command with human-readable plain output"
```

---

### Task 13: Demo Repo Setup (P1)

**Context:** A public demo repo is needed for the launch checklist. This task documents the setup steps. No code to write here — it's configuration and issue seeding.

**Files:**
- Create: `docs/demo-repo-setup.md`

**Step 1: Write the setup doc**

```markdown
# Demo Repo Setup

## Overview

The demo repo is a public GitHub repo configured as a Flow Healer target. It contains seeded issues that demonstrate both Class A (flaky test) and Class B (safe config/CI) healing.

## Setup Steps

1. Create a public GitHub repo: `flow-healer-demo` under your account
2. Clone locally: `git clone git@github.com:yourname/flow-healer-demo.git`
3. Create a minimal Python project structure:
   - `pyproject.toml` with basic metadata
   - `tests/test_sample.py` with a trivially flaky test
   - `.github/workflows/ci.yml` with a basic CI workflow
4. Create labels on the GitHub repo:
   - `healer:ready` (green)
   - `healer:pr-approved` (blue)
5. Configure Flow Healer to target the demo repo in `config.yaml`
6. Seed 5-10 issues (mix of Class A and B):
   - 3x Class A: flaky test issues (test files only)
   - 3x Class B: safe config/CI fixes
   - 2x intentional rejects (production files, no validation command)
7. Add `healer:ready` label to the first two issues
8. Run `flow-healer start --once --repo demo` and verify PRs are opened

## Seeded Issue Templates

### Class A — Example

```
Title: test_sample_timing is flaky on CI

## Required code outputs

- `tests/test_sample.py` (replace time.sleep with mock timer)

## Validation command

pytest tests/test_sample.py -v
```

### Class B — Example

```
Title: CI workflow missing python-version matrix for 3.12

## Required code outputs

- `.github/workflows/ci.yml` (add 3.12 to matrix)

## Validation command

echo "CI config updated"
```
```

**Step 2: Commit**

```bash
git add docs/demo-repo-setup.md
git commit -m "docs: add demo repo setup guide"
```

---

## Verification After Each Week

After completing Week 1 tasks (Tasks 1–7 + 8–9):

```bash
pytest tests/test_healer_runner.py -v   # Evidence bundle
pytest tests/test_tui.py -v             # Failure taxonomy normalization
```

After completing Week 2 tasks (Tasks 10–11):

```bash
pytest tests/test_tui.py -v
pytest tests/test_cli.py -v
```

After completing Week 3 tasks (Tasks 12 + doc updates):

```bash
flow-healer doctor
flow-healer start --once
```

Full smoke test sequence:

```bash
flow-healer doctor --repo <demo-repo>
flow-healer start --repo <demo-repo> --once
flow-healer tui --repo <demo-repo> --once
flow-healer export --repo <demo-repo>
```

---

## Week-by-Week Summary

| Week | Tasks |
|------|-------|
| 1 | Tasks 1–4 (design doc, mvp.md, safe-scope.md, operator-workflow.md) + Tasks 8–9 (evidence bundle, failure taxonomy) |
| 2 | Tasks 5–6 (onboarding.md, README rewrite) + Tasks 10–11 (TUI restructure, row actions) |
| 3 | Task 7 (annotate config) + Task 12 (doctor polish) |
| 4 | Task 13 (demo repo) + end-to-end runs + demo recording |
