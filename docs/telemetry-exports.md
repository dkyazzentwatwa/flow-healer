# Telemetry Exports

This doc defines the operator-facing telemetry export contract for Flow Healer.

## Export Surfaces

Flow Healer supports two first-class export formats:

- CSV: spreadsheet-friendly snapshots for Numbers, Sheets, or ad hoc analysis
- JSONL: append-friendly structured records for replay, custom dashboards, and downstream tooling

The CLI entrypoint is:

```bash
flow-healer export --repo <repo-name>
```

By default this writes both formats under the service state root in a timestamped export directory.

## Export Families

Each export run writes the following datasets:

- `issues`
- `attempts`
- `events`
- `runtime_status`
- `control_commands`
- `summary_metrics`

CSV files live under `csv/` and JSONL files live under `jsonl/` in the chosen export directory.

## Source Of Truth

Exports are derived from existing runtime state and service summaries:

- SQLite issue and attempt history
- `healer_events`
- runtime status snapshots
- operator command history
- current cross-repo service status rows

Do not build a second telemetry persistence layer just for exports.

## Format Expectations

CSV:

- should stay stable and spreadsheet-friendly
- may JSON-encode nested values into cells when flattening is not meaningful
- should preserve top-level identifying fields such as repo and IDs

JSONL:

- should preserve nested payloads
- should be one JSON object per line
- should remain safe for append-style and stream processing workflows

## Intended Use

Use CSV when the operator wants local analysis in Numbers or similar tools.

Use JSONL when the operator wants:

- structured archival
- replay/debugging
- custom ingestion pipelines
- transformations into other views or dashboards
