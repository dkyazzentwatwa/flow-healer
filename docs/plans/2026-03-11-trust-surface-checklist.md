# Trust Surface Progress Checklist

## Coordination

- [x] Save the implementation plan to `docs/plans/2026-03-11-trust-surface-implementation.md`
- [x] Save a repo-tracked checkbox progress list
- [x] Dispatch worker agent for service trust contract
- [x] Dispatch worker agent for dashboard trust rendering
- [x] Integrate worker results into one coherent trust surface

## Task 1: Canonical Trust Payload

- [x] Add failing service tests for trust payload on `status_rows()`
- [x] Add failing service tests for trust payload on `doctor_rows()`
- [x] Implement trust summarizer helpers in `src/flow_healer/service.py`
- [x] Expose `trust` on status rows
- [x] Expose `trust` on doctor rows
- [x] Run `pytest tests/test_service.py -k trust -v`
- [x] Run `pytest tests/test_service.py -v`

## Task 2: Dashboard Trust Surface

- [x] Add failing dashboard tests for trust payload/rendering
- [x] Render repo trust state/score/summary in the dashboard
- [x] Render operator recommendation and explanation text
- [x] Keep existing scoreboard and telemetry cards working
- [x] Run `pytest tests/test_web_dashboard.py -k trust -v`
- [x] Run `pytest tests/test_web_dashboard.py -v`

## Task 3: Integration And Verification

- [x] Review the service and dashboard changes together
- [x] Update this checklist with completed items and any follow-ups
- [x] Run the full test suite with `pytest`
- [x] Request final code review

## Next Backlog After This Slice

- [ ] Add issue-level `why this ran` / `why this did not run` explanations
- [ ] Add contract linter action for issue forms
- [ ] Add contract remediation comment flow
- [ ] Add policy-driven throttle/quarantine actions
- [ ] Add phased validation and promotion states
