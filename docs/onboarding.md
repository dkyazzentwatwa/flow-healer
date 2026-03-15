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
```

Copy `config.example.yaml` (at the root of the Flow Healer repo) to `~/.flow-healer/config.yaml`. If you installed via pip without cloning the repo, download it from the [GitHub repo root](https://github.com/flow-healer/flow-healer/blob/main/config.example.yaml). Then open it and set:

```yaml
repos:
  - name: my-repo
    path: /absolute/path/to/your/local/clone
    repo_slug: yourname/your-repo
    default_branch: main
    enable_autonomous_healer: true
    issue_contract_mode: lenient  # "lenient" infers outputs/validation — see docs/safe-scope.md
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
