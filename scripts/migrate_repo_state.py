#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from flow_healer.repo_state_migration import migrate_repo_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate Flow Healer repo state into the canonical repo identity.")
    parser.add_argument("--source-db", required=True, help="Path to the legacy source state.db")
    parser.add_argument("--target-db", required=True, help="Path to the canonical target state.db")
    parser.add_argument("--source-repo-name", default="flow-healer")
    parser.add_argument("--target-repo-name", default="flow-healer-self")
    parser.add_argument("--no-backup", action="store_true", help="Skip pre-migration DB backups")
    return parser.parse_args()


def _backup_path(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return db_path.parent.parent / "backups" / f"{db_path.parent.name}.state.{stamp}.bak"


def _backup_db(db_path: Path) -> str:
    if not db_path.exists():
        return ""
    backup_path = _backup_path(db_path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup_path)
    return str(backup_path)


def main() -> int:
    args = parse_args()
    source_db = Path(args.source_db).expanduser().resolve()
    target_db = Path(args.target_db).expanduser().resolve()

    payload: dict[str, object] = {
        "source_db": str(source_db),
        "target_db": str(target_db),
        "source_backup": "",
        "target_backup": "",
    }
    if not args.no_backup:
        payload["source_backup"] = _backup_db(source_db)
        payload["target_backup"] = _backup_db(target_db)

    payload["migration"] = migrate_repo_state(
        source_db=source_db,
        target_db=target_db,
        source_repo_name=args.source_repo_name,
        target_repo_name=args.target_repo_name,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
