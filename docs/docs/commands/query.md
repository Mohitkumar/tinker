---
sidebar_position: 11
title: Query language
---

# Tinkr query language

The `--query` / `-q` option on `tinkr logs` and `tinkr tail` accepts a unified query language that Tinkr translates into each backend's native syntax. You never need to learn LogQL, KQL, or Elasticsearch DSL — write one query, run it anywhere.

---

## Wildcard (match all)

```
*
```

The default when `--query` is omitted. Returns every log line in the time window.

---

## Text search

### Bare word

```
timeout
```

Matches any log line containing the word `timeout` (case-insensitive on most backends).

### Exact phrase

```
"database connection refused"
```

Quotes enforce phrase matching — the words must appear adjacent and in order.

### Multiple words (implicit AND)

```
stripe timeout
```

Two bare words side-by-side are combined with implicit AND — both must appear in the log line.

---

## Field filters

### Single value

```
level:ERROR
service:payments-api
trace_id:abc123def456
```

Matches logs where the specified field equals the value.

### Multiple values (OR within a field)

```
level:(ERROR OR WARN)
service:(payments-api OR auth-service)
```

Parentheses with `OR` inside a field filter match any of the listed values.

---

## Boolean operators

### AND

```
level:ERROR AND service:payments-api
```

Both conditions must be true. `AND` is case-insensitive. It is also **implicit** — two expressions side-by-side are AND'd automatically:

```
level:ERROR service:payments-api
```

### OR

```
level:ERROR OR level:CRITICAL
```

Either condition matches. Use parentheses to group with other operators:

```
(level:ERROR OR level:CRITICAL) AND service:payments-api
```

### NOT

```
NOT "health check"
NOT level:DEBUG
```

Excludes log lines that match the expression.

---

## Grouping

Use parentheses to override default precedence (`NOT` > `AND` > `OR`):

```
(level:ERROR OR level:CRITICAL) AND NOT service:load-balancer
```

---

## Field aliases

These short names are equivalent to their canonical counterparts:

| Alias | Canonical field |
|---|---|
| `lvl` | `level` |
| `severity` | `level` |
| `svc` | `service` |
| `app` | `service` |
| `msg` | `message` |
| `trace` | `trace_id` |
| `span` | `span_id` |

```bash
# These are equivalent
tinkr logs payments-api -q 'severity:ERROR'
tinkr logs payments-api -q 'level:ERROR'
```

---

## Practical examples

### Find all errors in a service

```bash
tinkr logs payments-api -q 'level:ERROR'
```

### Errors and warnings together

```bash
tinkr logs payments-api -q 'level:(ERROR OR WARN)'
```

### Specific exception

```bash
tinkr logs payments-api -q '"NullPointerException"'
```

### Phrase search in the message field

```bash
tinkr logs payments-api -q 'message:"stripe timeout"'
```

### Errors from two services combined

```bash
tinkr logs payments-api -q 'level:ERROR AND service:(payments-api OR order-service)'
```

### Errors, excluding noisy health checks

```bash
tinkr logs payments-api -q 'level:ERROR AND NOT "health check"'
```

### High-severity events excluding infra noise

```bash
tinkr logs payments-api -q '(level:ERROR OR level:CRITICAL) AND NOT service:load-balancer'
```

### Find a specific trace across services

```bash
tinkr logs payments-api -q 'trace_id:abc123def456'
# or using the alias:
tinkr logs payments-api -q 'trace:abc123def456'
```

### Stream errors live (tail)

```bash
tinkr tail payments-api -q 'level:ERROR'
```

### Stream errors and warnings, pipe to jq

```bash
tinkr tail payments-api -q 'level:(ERROR OR WARN)' --output jsonlines | jq .message
```

### Last 100 critical events in the past 6 hours

```bash
tinkr logs payments-api --since 6h -n 100 -q 'level:CRITICAL'
```

---

## Passing raw backend queries

If your query starts with a backend-specific sentinel character, Tinkr passes it through unchanged without translating:

| Backend | Pass-through trigger | Example |
|---|---|---|
| Grafana (Loki) | Starts with `{` | `{service="payments-api"} \|= "timeout"` |
| Datadog | Starts with `@` or `service:` | `@http.status_code:500` |
| CloudWatch | Contains `\|` | `fields @message \| filter level = 'ERROR'` |
| GCP | Starts with `resource.`, `labels.`, `severity=`, etc. | `severity=ERROR resource.labels.service_name="payments-api"` |

Raw queries bypass translation and are sent directly to the backend — useful when you need a feature that the unified language doesn't expose.

---

## Backend translation reference

The table below shows how each unified expression maps to each backend's native syntax.

| Tinkr query | Loki (LogQL) | CloudWatch Insights | GCP Cloud Logging | Azure (KQL) | Datadog | Elastic / OTel |
|---|---|---|---|---|---|---|
| `level:ERROR` | `\| logfmt \| level="ERROR"` | `filter level = 'ERROR'` | `severity="ERROR"` | `where Level == "ERROR"` | `status:error` | `{"term":{"level":"ERROR"}}` |
| `"timeout"` | `\|= "timeout"` | `filter @message like /timeout/` | `SEARCH("timeout")` | `where Message contains "timeout"` | `"timeout"` | `{"match":{"message":"timeout"}}` |
| `NOT level:DEBUG` | `\| logfmt \| level != "DEBUG"` | `filter level != 'DEBUG'` | `severity!="DEBUG"` | `where Level != "DEBUG"` | `-status:debug` | `{"must_not":[{"term":{"level":"DEBUG"}}]}` |

---

## See also

- [`tinkr logs`](logs) — fetch a fixed window of past logs
- [`tinkr tail`](tail) — stream logs live
