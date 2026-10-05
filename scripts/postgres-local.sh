#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Isolated disposable cluster. Matches .env.example; custom DB settings use Docker or your own DB.
for binary in initdb pg_ctl createdb psql; do
  command -v "$binary" >/dev/null || { echo "Missing $binary. Install PostgreSQL and add its bin directory to PATH."; exit 1; }
done
mkdir -p .local
cluster="$PWD/.local/postgres"
case "${1:-start}" in
  start)
    if [[ ! -f "$cluster/PG_VERSION" ]]; then
      password_file=$(mktemp)
      trap 'rm -f "$password_file"' EXIT
      printf '%s\n' maxx_local > "$password_file"
      initdb -D "$cluster" -U maxx --pwfile="$password_file" --auth=scram-sha-256 >/dev/null
    fi
    if ! pg_ctl -D "$cluster" status >/dev/null 2>&1; then
      pg_ctl -D "$cluster" -l "$PWD/.local/postgres.log" -o "-h 127.0.0.1 -p 55432 -k $PWD/.local" -w start
    fi
    export PGPASSWORD=maxx_local
    if ! psql -h 127.0.0.1 -p 55432 -U maxx -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'maxx'" | grep -q '^1$'; then
      createdb -h 127.0.0.1 -p 55432 -U maxx maxx
    fi
    echo "Postgres ready on 127.0.0.1:55432 (database/user: maxx)."
    ;;
  stop) pg_ctl -D "$cluster" -m fast -w stop ;;
  *) echo "Usage: $0 start|stop"; exit 1 ;;
esac
