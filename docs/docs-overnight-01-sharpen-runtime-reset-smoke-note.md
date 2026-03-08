Changed [docs/docs-overnight-01-sharpen-runtime-reset-smoke-note.md](/Users/cypher-server/Documents/code/flow-healer/docs/docs-overnight-01-sharpen-runtime-reset-smoke-note.md) to make the reset smoke note sharper: it now calls out stale-status replay, explicitly names the `no_workspace_change` failure pattern, and adds a short operator check for confirming a real in-workspace edit.

Validation ran: `sed -n '1,260p' docs/docs-overnight-01-sharpen-runtime-reset-smoke-note.md` and `git diff -- docs/docs-overnight-01-sharpen-runtime-reset-smoke-note.md`.
