# App Target Onboarding

Use this checklist when adding a new browser-backed reference app or runtime profile.

## Required App Shape

- Put the app under `e2e-apps/<target-name>/`.
- Add one deterministic health endpoint such as `GET /healthz`.
- Add one stable login/session path and one stable post-login route such as `/dashboard`.
- Keep the target small enough that a focused issue can touch 1-3 files without crossing unrelated subsystems.

## Required Runtime Profile

Add an entry under `healer_app_runtime_profiles` with:

- `name`
- `start_command`
- `working_directory`
- `ready_url`
- `browser`
- `headless`
- `fixture_driver_command` when the app needs seeded data or pre-authenticated sessions

Example:

```yaml
healer_app_runtime_profiles:
  - name: ruby-rails-web
    start_command: ruby server.rb
    working_directory: e2e-apps/ruby-rails-web
    ready_url: http://127.0.0.1:3101/healthz
    browser: chromium
    headless: true
    fixture_driver_command:
      - ruby
      - scripts/fixture_driver.rb
```

## Fixture Driver Contract

If the app uses fixtures or richer auth/session flows, ship one repo-owned driver command that supports:

- `prepare <fixture_profile>`
- `auth-state <fixture_profile> <output_path> <entry_url>`

`prepare` should reset or seed deterministic repro data.

`auth-state` should write a Playwright-compatible `storageState` JSON file at `output_path`.
Normalize `entry_url` down to its scheme + host + port before writing `origins[].origin`.

## Required Tests

- One sandbox existence entry in `tests/test_e2e_apps_sandboxes.py`
- One issue-parser case proving the app path resolves to the right execution root and language
- One runner test if the app depends on fixture-driver behavior that differs from existing targets

## Issue Contract Example

```md
app_target: ruby-rails-web
entry_url: http://127.0.0.1:3101/login
fixture_profile: seeded-admin
runtime_profile: ruby-rails-web

repro_steps:
- goto /login
- fill input[name=email]=admin@example.com
- fill input[name=password]=demo-password
- click button[type=submit]
- expect_text Dashboard
```

## Canary Readiness

Before calling an app target "reference ready", verify:

- the runtime boots from a clean checkout
- the health endpoint responds consistently
- failure and resolution screenshots are captured
- console and network logs are present
- the artifact pack can be published without manual cleanup
