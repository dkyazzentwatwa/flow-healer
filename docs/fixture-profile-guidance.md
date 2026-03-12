# Fixture Profile Guidance

Fixture profiles are the deterministic contract for app-backed repro flows.

## Naming

- Use short, role-oriented names such as `anonymous`, `seeded-admin`, `seeded-basic-user`, or `seeded-expired-session`.
- One fixture profile should describe both the data shape and the auth/session posture.
- Do not introduce a separate auth-profile field for the same scenario.

## What A Good Fixture Profile Does

- resets the app to a known baseline
- seeds only the data required for the repro
- avoids time-sensitive randomness when a fixed timestamp or identifier will do
- can be rerun before both failure capture and resolution capture

## Fixture Driver Behavior

Flow Healer can call the app's fixture driver twice per app-backed run:

1. `prepare <fixture_profile>` before booting the app
2. `auth-state <fixture_profile> <output_path> <entry_url>` after the app is ready

The auth-state step should create a Playwright-compatible `storageState` file so browser capture can reuse sessions without brittle UI login flows.

## Recommended Profiles

- `anonymous`: unauthenticated baseline with public data only
- `seeded-admin`: deterministic admin account plus any required seeded records
- `seeded-basic-user`: non-admin account for access-control and visibility checks
- `seeded-expired-session`: deterministic session-expiry or re-auth scenario

## Anti-Patterns

- profiles that depend on wall-clock timing or random IDs
- profiles that mutate shared external services
- profiles that require manual login before every run
- profiles that write temporary auth state inside the git worktree

## Storage State Notes

- write generated auth state outside the worktree when possible
- include only the cookies or local storage entries required for the scenario
- keep the stored origin aligned with the runtime profile host and port, not the full path from `entry_url`
