#!/usr/bin/env bash
# Deploy the service and prove it came up. Run from anywhere in the repo.
#
# The service's Root Directory is set to /aura-chat, so `railway up` is run from
# the REPO ROOT with no path and no --path-as-root. Passing either would make
# Railway look for aura-chat/aura-chat and fail with "could not determine how to
# build the app" -- see DEPLOY.md.
set -euo pipefail

BASE="${AURA_BASE:-https://aura-chat-production-0711.up.railway.app}"
cd "$(git rev-parse --show-toplevel)"

echo "deploying from $(pwd) (service root directory = /aura-chat)"
railway up --service aura-chat --detach

for _ in $(seq 1 30); do
  sleep 10
  status=$(railway deployment list --service aura-chat 2>/dev/null | sed -n '2p')
  echo "  $status"
  case "$status" in *SUCCESS*) break;; *FAILED*|*CRASHED*) echo "deploy failed"; exit 1;; esac
done

echo "--- is the new build actually serving? ---"
curl -fsS -D- -o /dev/null -m 15 "$BASE/health" | grep -qi x-request-id \
  && echo "  ok: this build answers with X-Request-Id" \
  || { echo "  WARNING: no X-Request-Id -- an older image is still serving"; exit 1; }

echo "--- /doctor ---"
if [ -n "${TOK:-}" ]; then
  curl -fsS -m 30 -H "Authorization: Bearer $TOK" "$BASE/doctor"
  echo
else
  echo "  set TOK to a realtor token to run the real readiness check"
fi
