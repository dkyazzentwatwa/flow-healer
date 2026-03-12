# Java, Go, and Rust Full Toolchain Smoke Follow-Up

## Why This Is Still Open

The repository now has first-class local validation strategies and reference targets for:

- `go`
- `rust`
- `java_gradle`

The remaining work is no longer toolchain availability. The remaining gap is durable automation and repeatable proof capture for these lanes across time (local reruns, canary cadence, and CI strategy).

## Current Local Status (`2026-03-12`)

- Installed toolchains verified:
  - `go version go1.26.1 darwin/arm64`
  - `rustc 1.94.0` / `cargo` available
  - `openjdk version "25.0.2"` and `javac` available via wrapper checks
- Native smoke/test commands executed successfully:
  - `cd e2e-smoke/go && go test ./...`
  - `cd e2e-smoke/rust && cargo test`
  - `cd e2e-smoke/java-gradle && ./gradlew test --no-daemon`
  - `cd e2e-apps/java-spring-web && ./gradlew test --no-daemon`
- Java app live smoke executed successfully:
  - `cd e2e-apps/java-spring-web && ./gradlew bootRun`
  - `GET /healthz` => `200 {"status":"ok"}`
  - `GET /dashboard` (anonymous) => `302 Location: /login`
  - `POST /login` => `Set-Cookie: healer_session=seeded-admin@example.com`
  - `GET /dashboard` (with cookie) => `200` and renders `seeded-admin@example.com`

## End Goal

Prove that Flow Healer's new Go, Rust, and Java reference lanes work end-to-end on a machine with the required toolchains available, without hidden manual setup.

## Definition Of Done

- The local machine or CI runner has working `go`, `cargo`, `java`, and `javac` in `PATH`.
- Each new reference target passes its published validation command from a clean checkout.
- Preflight reports for the Go, Rust, and Java roots show `ready` instead of environment-blocked.
- Java app boot/readiness is live-smoked, not just unit-tested.
- The evidence from those native runs is captured in a short verification note or canary artifact summary.

## Remaining Tasks

### 1. Persist this proof in routine operations

- Add these exact commands to the weekly mastery checklist.
- Capture one attached status snapshot per week showing Go/Rust/Java roots still `ready`.
- Keep one short Java boot smoke transcript per review window.

### 2. Decide and land persistent automation scope

- Decide whether native Go/Rust/Java smoke belongs in:
  - a local operator checklist only
  - a dedicated CI job
  - periodic canary runs on a prepared machine
- If CI is chosen, add a job with explicit toolchain provisioning.

### 3. Keep canary freshness visible for app-backed Java lane

- Ensure runtime profile canary freshness remains within the 7-day target.
- Alert when Java profile freshness drifts even if code lanes stay green.

## Suggested Verification Bundle

- Terminal output for:
  - `go test ./...`
  - `cargo test`
  - both Java `./gradlew test --no-daemon` commands
- One live Java app smoke transcript covering health, login, and dashboard session behavior
- Updated roadmap/weekly note entries referencing this proof run and the next rerun date
