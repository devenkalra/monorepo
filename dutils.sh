#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${DUTILS_COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.production.yml}"

usage() {
  cat <<'EOF'
dutils.sh - production docker compose utility

Usage:
  ./dutils.sh <command> [args...]

Commands:
  redeploy <service...>       Build (no-cache) + up --force-recreate --no-deps
  build <service...>          Build service(s) (cached)
  rebuild <service...>        Build service(s) with --no-cache
  up [service...]             Start service(s) in detached mode
  down                        Stop and remove containers/networks
  restart <service...>        Restart service(s)
  logs <service> [--tail N]   Show logs (defaults: --tail 200 -f)
  ps [service...]             Show compose service status
  pull [service...]           Pull image(s)
  exec <service> <cmd...>     Execute a command in a running container
  config                      Show resolved compose config
  help                        Show this help

Environment:
  DUTILS_COMPOSE_FILE         Override compose file (default: docker-compose.production.yml)

Examples:
  ./dutils.sh redeploy frontend
  ./dutils.sh logs backend --tail 100
  ./dutils.sh exec backend python manage.py migrate
EOF
}

compose() {
  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "Compose file not found: ${COMPOSE_FILE}" >&2
    exit 1
  fi

  echo "> docker compose -f ${COMPOSE_FILE} $*"
  docker compose -f "${COMPOSE_FILE}" "$@"
}

cmd="${1:-help}"
shift || true

case "${cmd}" in
  redeploy)
    [[ "$#" -ge 1 ]] || { echo "redeploy requires at least one service name" >&2; exit 1; }
    for service in "$@"; do
      compose build --no-cache "${service}"
      compose up -d --force-recreate --no-deps "${service}"
    done
    ;;

  build)
    [[ "$#" -ge 1 ]] || { echo "build requires at least one service name" >&2; exit 1; }
    compose build "$@"
    ;;

  rebuild)
    [[ "$#" -ge 1 ]] || { echo "rebuild requires at least one service name" >&2; exit 1; }
    compose build --no-cache "$@"
    ;;

  up)
    compose up -d "$@"
    ;;

  down)
    compose down
    ;;

  restart)
    [[ "$#" -ge 1 ]] || { echo "restart requires at least one service name" >&2; exit 1; }
    compose restart "$@"
    ;;

  logs)
    [[ "$#" -ge 1 ]] || { echo "logs requires a service name" >&2; exit 1; }
    if [[ " $* " == *" --tail "* ]]; then
      compose logs -f "$@"
    else
      compose logs -f --tail 200 "$@"
    fi
    ;;

  ps)
    compose ps "$@"
    ;;

  pull)
    compose pull "$@"
    ;;

  exec)
    [[ "$#" -ge 2 ]] || { echo "exec requires: exec <service> <command...>" >&2; exit 1; }
    compose exec -T "$@"
    ;;

  config)
    compose config
    ;;

  help|-h|--help)
    usage
    ;;

  *)
    echo "Unknown command: ${cmd}" >&2
    usage
    exit 1
    ;;
esac
