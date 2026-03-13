# Java Gradle Smoke Lanes

This guide covers the Gradle-based Java smoke fixtures under `e2e-smoke/java-gradle`.

## Execution Root

- Use `e2e-smoke/java-gradle` or the narrower path declared by the issue.
- Keep mutations inside the Gradle fixture rather than broadening to other Java directories.

## Readiness Expectations

- The lane expects Gradle-based validation, not Maven.
- Local Java and Gradle readiness must be present because this lane does not use Docker fallback in the current model.

## Allowed Mutation Scope

- Restrict edits to fixture-local Java sources, Gradle config, and tests required by the issue.
- Avoid runtime-profile or app-server edits from a smoke-fixture issue.

## Validation Commands

- Prefer `cd e2e-smoke/java-gradle && ./gradlew test --no-daemon`.

## Evidence And Fixture Expectations

- Java Gradle smoke is a code/test fixture lane.
- Browser evidence belongs to `java-spring-web` under [browser-apps.md](browser-apps.md).

## Common Failure Modes

- A Maven-oriented issue contract gets applied to a Gradle fixture.
- Java toolchain drift on the host.
- Validation succeeds locally but the issue contract points at files outside the declared Gradle root.

## Lane-Specific Guardrails

- Do not add Maven-specific assumptions to this lane.
- Keep Gradle invocation explicit and local to the fixture.
