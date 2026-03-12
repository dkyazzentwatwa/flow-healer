#!/usr/bin/env python3

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: fixture_driver.py <prepare|auth-state> <fixture> [output_path] [entry_url]", file=sys.stderr)
        return 1

    action = sys.argv[1]
    fixture = sys.argv[2]

    if action == "prepare":
        print(f"prepared fixture {fixture}")
        return 0

    if action == "auth-state":
        if len(sys.argv) < 4:
            print("auth-state requires an output path", file=sys.stderr)
            return 1
        output_path = Path(sys.argv[3])
        entry_url = sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:3201"
        parsed_url = urlsplit(entry_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.scheme and parsed_url.netloc else "http://127.0.0.1:3201"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "cookies": [
                {
                    "name": "healer_session",
                    "value": fixture,
                    "domain": "127.0.0.1",
                    "path": "/",
                    "httpOnly": False,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ],
            "origins": [
                {
                    "origin": origin,
                    "localStorage": [
                        {"name": "fixture_profile", "value": fixture},
                    ],
                }
            ],
        }
        output_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"wrote auth state for {fixture}")
        return 0

    print(f"unsupported action: {action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
