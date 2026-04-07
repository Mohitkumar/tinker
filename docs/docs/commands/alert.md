---
sidebar_position: 12
title: alert
---

# tinker alert

Manage threshold-based alert rules. An alert rule fires a notification when a metric crosses a defined threshold, regardless of whether a watch is running.

```
tinker alert <subcommand> [options]
```

## Subcommands

| Subcommand | Description |
|---|---|
| `create <service> <metric> <operator> <threshold>` | Create an alert rule |
| `list` | List all alert rules |
| `delete <alert-id>` | Delete an alert rule |
| `mute <alert-id>` | Mute an alert rule for a duration |

---

## `tinker alert create`

```bash
tinker alert create <service> <metric> <operator> <threshold> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `service` | Service name |
| `metric` | Metric name (e.g. `error_count`, `latency_p99`) |
| `operator` | Comparison operator: `gt`, `lt`, `gte`, `lte` |
| `threshold` | Numeric threshold value |

### Options

| Flag | Default | Description |
|---|---|---|
| `--severity TEXT` | `medium` | `low`, `medium`, `high`, `critical` |
| `--notifier TEXT` | `default` | Notifier from your profile config |
| `--destination TEXT` | — | Override the notifier channel/URL |

### Examples

```bash
# Fire when error count exceeds 50
tinker alert create payments-api error_count gt 50

# High severity p99 latency alert → PagerDuty
tinker alert create payments-api latency_p99 gt 1000 --severity high --notifier pagerduty

# Alert when request rate drops below minimum
tinker alert create payments-api request_rate lt 100 --severity critical

# Route to specific Slack channel
tinker alert create auth-service error_count gt 20 --notifier slack-ops --destination "#auth-oncall"
```

### Output

```
Alert rule created
  ID:        alert-a3f2b1c4
  Service:   payments-api
  Condition: error_count > 50
  Severity:  medium
  Notifier:  default
```

---

## `tinker alert list`

```bash
tinker alert list
```

### Output

```
ALERT ID          SERVICE         METRIC          CONDITION   SEVERITY  NOTIFIER   STATUS
alert-a3f2b1c4   payments-api    error_count     > 50        medium    default    active
alert-b5c6d7e8   payments-api    latency_p99     > 1000      high      pagerduty  active
alert-9f8e7d6c   auth-service    error_count     > 20        medium    slack-ops  muted (until 16:00)
```

---

## `tinker alert delete`

Permanently removes an alert rule.

```bash
tinker alert delete alert-a3f2b1c4
```

---

## `tinker alert mute`

Silence an alert rule for a period without deleting it. Useful during planned maintenance.

```bash
tinker alert mute alert-a3f2b1c4 [options]
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--for TEXT` | `30m` | Mute duration: `30m`, `2h`, `1d` |

### Examples

```bash
# Mute for 30 minutes (default)
tinker alert mute alert-a3f2b1c4

# Mute for 2 hours during maintenance window
tinker alert mute alert-a3f2b1c4 --for 2h

# Mute for a full day
tinker alert mute alert-a3f2b1c4 --for 1d
```

---

## Alert rules vs watches

| | `tinker alert` | `tinker watch` |
|---|---|---|
| Trigger | Specific metric threshold | Any anomaly change |
| Granularity | Per metric, per threshold | Per service, all metrics |
| Use case | "Notify me if error_count > 50" | "Notify me of anything unusual" |
| Muting | Per rule | Per watch (stop) |

Use both together: watches catch unexpected anomalies, alert rules enforce hard SLO thresholds.

## See also

- [`tinker watch`](watch) — continuous background monitoring
- [`tinker slo`](slo) — compute error budget and burn rate
- [Slack Integration](../integrations/slack) — Slack notifier configuration
- [Webhooks](../integrations/webhooks) — webhook notifier configuration
