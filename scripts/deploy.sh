#!/usr/bin/env bash
# Invoked by the server poller, from the tested commit.
set -euo pipefail
umask 077
sha=${1:?Expected tested commit SHA}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
cd /home1/ncloud/iumon
exec 9>/home1/ncloud/.iumon-deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
  echo 'Tracked server files have local changes; reconcile them first.' >&2; exit 1;
}
git fetch origin main
if [[ "$sha" != "$(git rev-parse refs/remotes/origin/main)" ]]; then
  echo 'Skipping superseded commit; only the latest tested main is deployed.'
  exit 0
fi
git cat-file -e "$sha^{commit}"
previous=$(git rev-parse HEAD)
if [[ -f /home1/ncloud/iumon-deployed-sha && "$(cat /home1/ncloud/iumon-deployed-sha)" == "$sha" && "$previous" == "$sha" ]]; then
  exit 0
fi
# Operator records the existing Compose file's absolute path once.
IFS= read -r COMPOSE_FILE < .deploy-compose-path
[[ "$COMPOSE_FILE" == /home1/ncloud/iumon/* && -f "$COMPOSE_FILE" ]] || {
  echo 'Invalid .deploy-compose-path' >&2; exit 1;
}
export COMPOSE_FILE
# Pin the existing project name so app keeps the tunnel's Docker network/DNS.
compose=(sudo -n docker compose -p iumon --profile demo -f "$COMPOSE_FILE")
"${compose[@]}" config --quiet
container=$("${compose[@]}" ps -q app)
[[ -n "$container" ]] || { echo 'Expected an existing app deployment.' >&2; exit 1; }
[[ "$(sudo -n docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" == iumon ]]
[[ "$(sudo -n docker inspect --format '{{if .Config.Healthcheck}}{{json .Config.Healthcheck.Test}}{{end}}' "$container")" == *CMD* ]] || {
  echo 'App must have a healthcheck before automatic deployment.' >&2; exit 1;
}
old_image=$(sudo -n docker inspect --format '{{.Image}}' "$container")
rollback_tag="iumon-app:rollback-$(date +%s)-$$"
sudo -n docker image tag "$old_image" "$rollback_tag"
override=$(mktemp /home1/ncloud/iumon-rollback.XXXXXX.json)
printf '{"services":{"app":{"image":"%s"}}}\n' "$rollback_tag" > "$override"
switched=0
replacing=0
finish() {
  result=$?
  trap - EXIT
  if (( result != 0 && switched )); then
    echo 'Deployment failed; restoring previous checkout.' >&2
    git checkout --detach "$previous" || true
    if (( replacing )); then
      if "${compose[@]}" -f "$override" up -d --no-deps --no-build --wait --wait-timeout 120 app; then
        echo "Previous image restored: $rollback_tag" >&2
      else
        echo "ROLLBACK FAILED. Retained image: $rollback_tag" >&2
      fi
    fi
  fi
  rm -f -- "$override"
  exit "$result"
}
trap finish EXIT
git checkout --detach "$sha"
switched=1
"${compose[@]}" config --quiet
"${compose[@]}" build app
replacing=1
"${compose[@]}" up -d --no-deps --no-build --wait --wait-timeout 120 app
curl --fail --silent --show-error --max-time 30 http://127.0.0.1:8765/api/status >/dev/null
printf '%s\n' "$sha" > /home1/ncloud/iumon-deployed-sha
echo "Deployed $sha; previous image retained as $rollback_tag"
