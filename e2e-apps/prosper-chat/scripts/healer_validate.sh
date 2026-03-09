#!/bin/sh

set -eu

profile="${1:-web}"

if [ "$profile" != "web" ]; then
  echo "unsupported validation profile: $profile" >&2
  exit 1
fi

npm test
