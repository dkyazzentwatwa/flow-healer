# Lane Guides

Lane guides are the canonical reference for editing anything under `e2e-smoke/` or `e2e-apps/`. Read the relevant guide before changing a sandbox, writing a lane-specific issue, or widening scope after validation fails.

Every guide in this directory uses the same contract:

- execution root
- readiness expectations
- allowed mutation scope
- validation commands
- evidence or fixture expectations
- common failure modes
- lane-specific guardrails

## Guides

- [browser-apps.md](browser-apps.md): browser-backed app targets such as `node-next`, `python-fastapi`, `ruby-rails-web`, `java-spring-web`, `prosper-chat`, and `nobi-owl-trader`
- [node-smoke.md](node-smoke.md): JS and Node smoke families
- [python-smoke.md](python-smoke.md): Python smoke families
- [ruby-smoke.md](ruby-smoke.md): Ruby smoke fixtures
- [java-gradle-smoke.md](java-gradle-smoke.md): Java Gradle smoke fixtures
- [go-smoke.md](go-smoke.md): Go smoke fixtures
- [rust-smoke.md](rust-smoke.md): Rust smoke fixtures
- [swift-smoke.md](swift-smoke.md): Swift smoke fixtures

## Shared Rules

- Keep issue `Required code outputs` scoped to the smallest valid lane root.
- Prefer lane-owned validation commands over repo-root shortcuts.
- Treat unrelated failures as baseline blockers, not invitations to mutate the whole repo.
- When browser evidence is involved, also follow [../evidence-contract.md](../evidence-contract.md).
- When an app target is involved, also follow [../dashboard.md](../dashboard.md), [../app-target-onboarding.md](../app-target-onboarding.md), and [../fixture-profile-guidance.md](../fixture-profile-guidance.md) as needed.
