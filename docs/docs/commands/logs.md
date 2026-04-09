---
sidebar_position: 2
title: logs
---

# tinkr logs

Fetch recent log lines from a service.

```
tinkr logs <service> [options]
```

## Arguments

| Argument | Description |
|---|---|
| `service` | Service name as configured in the active profile |

## Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--since TEXT` | `-s` | `30m` | How far back to look — e.g. `30m`, `1h`, `24h` |
| `--query TEXT` | `-q` | `*` | Filter expression (e.g. `level:ERROR`, `"NullPointerException"`) |
| `--limit INT` | `-n` | `50` | Maximum number of log lines to return |
| `--resource TEXT` | `-r` | — | Resource type: `ecs`, `lambda`, `cloudrun`, `gke`, etc. |
| `--output FORMAT` | `-o` | `table` | Output format: `table`, `json`, `jsonlines` |

## Examples

```bash
# Last 30 minutes of logs (newest first)
tinkr logs payments-api

# Last hour, errors only
tinkr logs payments-api --since 1h -q 'level:ERROR'

# Search for a specific exception
tinkr logs payments-api --since 2h -q '"NullPointerException"'

# Return up to 200 lines
tinkr logs payments-api --since 6h -n 200

# Machine-readable output
tinkr logs payments-api --since 1h --output jsonlines | jq .message
```

## Output

Results are displayed **oldest first, newest at the bottom** — so the most recent entries are always visible without scrolling up.

```
2026-04-09 14:01:14  ERROR   Payment charge failed: insufficient_funds
2026-04-09 14:01:04  ERROR   Stripe API timeout after 30s (attempt 3/3)
2026-04-09 14:01:03  WARN    Retry queue depth 847 — exceeds soft limit of 100
```

## Query syntax

The `--query` / `-q` value uses Tinkr's unified query language, which is translated to each backend's native syntax at query time. See the [full query language reference](query) for all operators and field aliases.

### Quick reference

| Expression | Matches |
|---|---|
| `*` | All logs (default) |
| `level:ERROR` | Error-level logs |
| `level:(ERROR OR WARN)` | Errors or warnings |
| `"NullPointerException"` | Exact phrase anywhere in the message |
| `timeout` | Bare word — substring match |
| `message:"stripe timeout"` | Phrase in the `message` field |
| `service:payments-api AND level:ERROR` | Errors from a specific service |
| `NOT "health check"` | Exclude health-check noise |
| `level:ERROR AND NOT service:load-balancer` | Errors, excluding one service |

### Backend translation

| Backend | Native syntax |
|---|---|
| Grafana (Loki) | LogQL |
| CloudWatch | Logs Insights |
| GCP | Cloud Logging filter |
| Azure | KQL |
| Datadog | Log query syntax |
| Elastic / OTel | Elasticsearch DSL |

## See also

- [Query language reference](query) — full syntax, field aliases, and per-backend examples
- [`tinkr tail`](tail) — stream logs live
- [`tinkr investigate`](investigate) — start an AI-powered investigation from log context
