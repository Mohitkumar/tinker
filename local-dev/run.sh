#!/usr/bin/env bash
# Start / stop the local development infrastructure.
# The Tinker server is NOT included — run it from your IDE or terminal.
#
# Usage:
#   ./run.sh          # start infra
#   ./run.sh down     # tear down
#   ./run.sh logs     # tail container logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "${1:-}" == "down" ]]; then
  docker compose down --remove-orphans
  exit 0
fi

if [[ "${1:-}" == "logs" ]]; then
  docker compose logs -f
  exit 0
fi

echo "Starting local dev infrastructure..."
docker compose up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 3

echo -n "payments-api "
for i in $(seq 1 20); do
  if curl -sf http://localhost:7001/health > /dev/null 2>&1; then
    echo "✓ healthy"
    break
  fi
  echo -n "."
  sleep 2
  if [[ $i == 20 ]]; then echo " timed out"; fi
done

echo ""
echo "──────────────────────────────────────────────────────────"
echo "  payments-api  → http://localhost:7001  (dummy service)"
echo "  Loki          → http://localhost:3100  (log storage)"
echo "  Prometheus    → http://localhost:9090  (metrics)"
echo "  Grafana UI    → http://localhost:3000  (dashboards)"
echo ""
echo "  Next steps:"
echo "  1. Start Tinker in your IDE  (see repo root .env.example)"
echo "     TINKER_BACKEND=grafana uv run tinker-server"
echo ""
echo "  2. Generate traffic:"
echo "     ./generate_traffic.sh              # steady mixed"
echo "     ./generate_traffic.sh incident     # simulate incident"
echo ""
echo "  3. Analyze:"
echo "     tinker analyze payments-api --since 5m -v"
echo "──────────────────────────────────────────────────────────"
