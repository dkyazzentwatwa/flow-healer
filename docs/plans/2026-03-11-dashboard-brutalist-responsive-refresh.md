# Brutalist Responsive Dashboard Refresh

## Summary
- Rebuild the dashboard shell in `src/flow_healer/dashboard_cockpit.py` as a mobile-first, software-brutalist interface.
- Use a top-tab mobile experience with `Queue`, `Detail`, and `Health`.
- Use a two-column desktop workspace with utility panels instead of the current fixed three-column cockpit.
- Fix light mode by routing core text, borders, backgrounds, and state colors through explicit semantic theme tokens rather than dark-biased utility classes.

## Implementation Changes
### Shell and layout
- Replace the current fixed three-column cockpit with a responsive shell.
- On mobile, use a sticky tab strip with `Queue`, `Detail`, and `Health`.
- On tablet and desktop, keep the queue on the left and issue detail on the right.
- Move saved views, repo filter, and system health into collapsible utility panels instead of always-visible fixed columns.
- Preserve issue-queue-first ordering and keyboard flow.

### Collapsible interaction model
- Add Alpine state for collapsible sections across the dashboard.
- Make the header stats cluster, saved views, filters, system health, detail subsections, and actions block independently collapsible.
- Default non-primary sections to collapsed on mobile.
- Keep queue and detail open by default on desktop while leaving utility panels collapsible.
- Keep keyboard shortcuts working, but ensure they behave predictably when mobile tabs are active.

### Visual redesign
- Shift from the current glassy look to software brutalism with harder borders, flatter surfaces, stronger shadows, and bolder type hierarchy.
- Reduce translucent layering and tighten the accent system so the interface reads as a focused ops tool.
- Make selected states, status chips, and action controls much clearer.
- Simplify the header action area so it behaves like an intentional control strip rather than floating pills.

### Theme and contrast fix
- Introduce semantic theme variables for page background, panel background, muted surfaces, primary text, secondary text, borders, active states, and status tones.
- Update markup so light and dark mode both consume those semantic tokens.
- Ensure light mode body copy, metadata, inactive controls, and queue cards remain readable without washed-out contrast.

## Public Interfaces / State Changes
- No HTTP endpoint changes.
- No payload shape changes for `/api/queue`, `/api/issue-detail`, or `/api/overview`.
- Expand the Alpine component state in the rendered page to include:
  - active mobile tab id
  - per-section collapse state
  - responsive helpers for mobile versus desktop defaults
- Keep `openIssueDetail`, `refresh`, `toggleTheme`, queue filtering, and keyboard shortcuts, while rewiring the template to support the new shell.

## Test Plan
- Update `tests/test_web_dashboard.py` to verify:
  - mobile tab shell labels and state wiring
  - collapsible controls for saved views, filters, health, and detail actions
  - semantic theme hooks for readable light and dark mode rendering
  - command palette and keyboard shortcuts still present
  - old three-column assumptions removed or updated
- Manually verify with browser screenshots for:
  - desktop dark mode
  - desktop light mode
  - phone-width dark mode
  - phone-width light mode
- Confirm queue selection, detail switching, collapse controls, and theme toggle all remain functional.

## Assumptions
- The redesign stays server-rendered inside the current inline HTML and Alpine approach.
- Brutalism here means sharper and bolder, not chaotic; operational readability stays first.
- System health remains secondary content and should stay de-emphasized unless explicitly opened.
- Screenshot-based visual verification is part of acceptance because responsiveness and contrast are core to the task.
