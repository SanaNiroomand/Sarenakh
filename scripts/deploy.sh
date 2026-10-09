#!/usr/bin/env bash
# Ship the committed tree (never .env or local data) to the server and rebuild.
#   Usage: scripts/deploy.sh user@host [remote_dir]
# First time only: copy your .env to <remote_dir>/.env on the server (see README).
set -euo pipefail

TARGET=${1:?usage: scripts/deploy.sh user@host [remote_dir]}
DIR=${2:-sarenakh}

cd "$(git rev-parse --show-toplevel)"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "warning: uncommitted changes are NOT deployed (only HEAD is shipped)" >&2
fi

echo ">> uploading $(git rev-parse --short HEAD) to $TARGET:$DIR"
git archive --format=tar HEAD | ssh "$TARGET" "
  set -e
  mkdir -p '$DIR'
  cd '$DIR'
  # remove previously shipped files, keep secrets and runtime data
  find . -mindepth 1 -maxdepth 1 ! -name .env ! -name data -exec rm -rf {} +
  tar -x
"

echo ">> building and restarting"
ssh "$TARGET" "cd '$DIR' && docker compose up -d --build --remove-orphans && docker image prune -f >/dev/null && docker compose ps"

echo ">> health"
ssh "$TARGET" "sleep 5; curl -fsS http://127.0.0.1:8000/health; echo"
