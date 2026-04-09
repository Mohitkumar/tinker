---
sidebar_position: 3
title: tail
---

# tinkr tail

Stream live logs to your terminal. Polls the backend continuously and prints new entries as they arrive.

```
tinkr tail <service> [options]
```

## Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--query TEXT` | `-q` | `*` | Filter expression (e.g. `level:ERROR`) |
| `--lines INT` | `-n` | — | Show last N lines first, then stream live |
| `--poll FLOAT` | `-p` | `2.0` | Poll interval in seconds |
| `--resource TEXT` | `-r` | — | Resource type: `ecs`, `lambda`, `cloudrun`, `gke`, etc. |
| `--output FORMAT` | `-o` | `table` | Output format: `table`, `json`, `jsonlines` |

## Examples

```bash
# Stream all logs
tinkr tail payments-api

# Show last 20 lines, then stream live (like tail -n 20 -f)
tinkr tail payments-api -n 20

# Errors only
tinkr tail payments-api -q 'level:ERROR'

# Last 50 error lines then stream
tinkr tail payments-api -n 50 -q 'level:ERROR'

# Pipe to jq
tinkr tail payments-api --output jsonlines | jq .message
```

## Output

```
Tailing payments-api · last 20 lines  (Ctrl-C to stop)

--- live stream ---
14:01:03  ERROR     Payment charge failed: card_declined
14:01:04  ERROR     Stripe API timeout after 30s
14:01:09  INFO      Health check OK
14:01:14  ERROR     Payment charge failed: insufficient_funds
```

When `-n` is used, the historical lines print first (oldest at the top), followed by a `--- live stream ---` divider, then live entries as they arrive.

Press `Ctrl-C` to stop.

## Notes

- `tinkr tail` polls the backend — it is not a WebSocket push stream. Most observability backends don't expose a native push API.
- The `-n` lookback window is 30 minutes. For older history use [`tinkr logs --since`](logs).
- For high-volume services, use `-q` to reduce noise before piping to other tools.

## See also

- [Query language reference](query) — full syntax, field aliases, and per-backend examples
- [`tinkr logs`](logs) — fetch a fixed window of past logs (newest first)
- [`tinkr investigate`](investigate) — AI-powered investigation starting from recent errors
