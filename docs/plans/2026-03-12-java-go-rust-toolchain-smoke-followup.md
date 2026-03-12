# Java, Go, and Rust Full Toolchain Smoke Follow-Up

## Why This Is Still Open

The repository now has first-class local validation strategies and reference targets for:

- `go`
- `rust`
- `java_gradle`

The remaining gap is not wiring inside Flow Healer. It is environment availability for the native toolchains needed to run true end-to-end smoke validation from a clean checkout.

## Current Blockers

- `go` is not installed in the current workspace environment.
- `cargo` / Rust toolchain is not installed in the current workspace environment.
- A Java runtime and `javac` are not installed in the current workspace environment.
- Because of the missing toolchains, we could not run:
  - `cd e2e-smoke/go && go test ./...`
  - `cd e2e-smoke/rust && cargo test`
  - `cd e2e-smoke/java-gradle && ./gradlew test --no-daemon`
  - `cd e2e-apps/java-spring-web && ./gradlew test --no-daemon`
  - `cd e2e-apps/java-spring-web && ./gradlew bootRun`

## End Goal

Prove that Flow Healer's new Go, Rust, and Java reference lanes work end-to-end on a machine with the required toolchains available, without hidden manual setup.

## Definition Of Done

- The local machine or CI runner has working `go`, `cargo`, `java`, and `javac` in `PATH`.
- Each new reference target passes its published validation command from a clean checkout.
- Preflight reports for the Go, Rust, and Java roots show `ready` instead of environment-blocked.
- Java app boot/readiness is live-smoked, not just unit-tested.
- The evidence from those native runs is captured in a short verification note or canary artifact summary.

## Remaining Tasks

### 1. Provision toolchains

- Install Go and verify `go version`.
- Install Rust and verify `cargo --version`.
- Install JDK 17+ and verify `java -version` plus `javac -version`.
- Decide whether this should be documented as local-only setup, CI setup, or both.

### 2. Run native smoke commands

- Run `cd e2e-smoke/go && go test ./...`
- Run `cd e2e-smoke/rust && cargo test`
- Run `cd e2e-smoke/java-gradle && ./gradlew test --no-daemon`
- Run `cd e2e-apps/java-spring-web && ./gradlew test --no-daemon`

### 3. Live-smoke Java app boot

- Run `cd e2e-apps/java-spring-web && ./gradlew bootRun`
- Confirm `http://127.0.0.1:3201/healthz` responds.
- Confirm `/login` sets `healer_session`.
- Confirm `/dashboard` redirects when anonymous and renders the seeded user with a valid session cookie.

### 4. Re-run Flow Healer readiness checks

- Re-run focused preflight coverage after toolchain install.
- Confirm Go, Rust, and Java roots no longer fail for missing environment dependencies.
- Capture one short before/after note showing the preflight transition to `ready`.

### 5. Decide on persistent automation

- Decide whether native Go/Rust/Java smoke belongs in:
  - a local operator checklist only
  - a dedicated CI job
  - periodic canary runs on a prepared machine
- If CI is chosen, add a job with explicit toolchain provisioning.

## Suggested Verification Bundle

- Terminal output for `go test ./...`
- Terminal output for `cargo test`
- Terminal output for both Java `./gradlew test --no-daemon` commands
- One live Java app smoke transcript covering health, login, and dashboard session behavior
- Updated note in the harness roadmap or a follow-up completion doc once the toolchains are available
