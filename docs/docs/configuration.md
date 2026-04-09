---
sidebar_position: 8
title: Configuration Reference
---

# Configuration Reference

Tinkr uses two files, both in `~/.tinkr/`:

| File | Written by | Purpose |
|---|---|---|
| `~/.tinkr/config.toml` | `tinkr-server init` or manually | Structure — profiles, backends, services, notifiers, auth |
| `~/.tinkr/.env` | `tinkr-server init` or manually | Secrets — API keys, tokens, URLs. **Never commit this file.** |
| `~/.tinkr/config` | `tinkr init` | CLI connection — server URL and API token |

Values in `config.toml` can reference env vars as `"env:VAR_NAME"`. At load time Tinkr substitutes the value from `.env` or the process environment.

---

## config.toml — section by section

### `[server]` — CLI connection

Used by the **CLI** to know which server to talk to. Not needed on the server itself.

```toml
[server]
url   = "http://localhost:8000"     # Tinkr server URL
token = "env:TINKR_API_TOKEN"      # Raw API token (not the hash)
```

| Key | Description |
|---|---|
| `url` | Base URL of the Tinkr server |
| `token` | Raw API token the CLI sends as `Bearer <token>`. Store the value in `.env` and reference it here. |

---

### `[auth]` — API key authentication

Used by the **server** to verify incoming CLI and Slack bot requests. Store hashed keys here — never raw tokens.

```toml
[auth]
api_keys = [
  { hash = "<sha256-of-key>", subject = "alice", roles = ["oncall"] },
  { hash = "<sha256-of-key>", subject = "bob",   roles = ["viewer"] },
  { hash = "<sha256-of-key>", subject = "ci-bot", roles = ["viewer"] },
]
```

| Key | Description |
|---|---|
| `hash` | SHA-256 of the raw key. Generate: `python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" <raw-key>` |
| `subject` | Human-readable label for audit logs (email, name, or service name) |
| `roles` | List of roles: `viewer`, `oncall`, or `sre-lead` |

**Roles:**

| Role | Permissions |
|---|---|
| `viewer` | Read-only: logs, metrics, anomaly, trace, diff, slo, deploy, rca |
| `oncall` | Viewer + `fix`, `approve`, `watch`, `alert` |
| `sre-lead` | All permissions (same as oncall, different label) |

Generate a key pair:
```bash
# Raw key (give to the user)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Hash (put in config.toml)
python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" <raw-key>
```

---

### `[github]` — GitHub integration

Enables code investigation (`explain`, `fix`) and auto-PRs (`approve`). Optional — omit this section if you don't need it.

```toml
[github]
token        = "env:GITHUB_TOKEN"   # Fine-grained PAT with Contents+PR write
default_repo = "acme/monorepo"      # Used when a service has no repo configured
```

| Key | Description |
|---|---|
| `token` | Fine-grained PAT. Required scopes: Contents (read), Commits (read), Pull requests (write) |
| `default_repo` | Fallback repo for services that don't have a `repo` set in their profile |

---

### `[slack]` — Slack bot

Enables `/tinkr-*` slash commands and alert routing to Slack channels. Optional.

```toml
[slack]
bot_token      = "env:SLACK_BOT_TOKEN"
signing_secret = "env:SLACK_SIGNING_SECRET"
alerts_channel = "#incidents"          # Default channel for watch alerts
```

| Key | Description |
|---|---|
| `bot_token` | Bot OAuth token (`xoxb-...`) from your Slack app |
| `signing_secret` | Signing secret for verifying Slack webhook payloads |
| `alerts_channel` | Default Slack channel for watch alert notifications |

---

### `[profiles.<name>]` — Backend profiles

A profile bundles a backend with its services and notifiers. You can define as many profiles as you have environments. The active profile is what all CLI commands use.

**Profile resolution order:**
1. `--profile` flag on the command
2. `TINKR_PROFILE` environment variable
3. Profile with `active = true` in `config.toml`
4. Profile named `default`

**Common keys for all profiles:**

| Key | Description |
|---|---|
| `backend` | One of: `cloudwatch`, `gcp`, `azure`, `grafana`, `datadog`, `elastic`, `otel` |
| `active` | `true` to make this the default profile |

---

### `[profiles.<name>.services.<service>]` — Per-service configuration

Attach metadata to a service within a profile — primarily the GitHub repo and resource type for code context and deploy correlation.

```toml
[profiles.aws-prod.services.payments-api]
repo          = "acme/payments"    # GitHub repo for code investigation and PRs
resource_type = "ecs"              # ecs | lambda | cloud_run | gke | container_app | k8s
```

| Key | Description |
|---|---|
| `repo` | `owner/repo` on GitHub. Falls back to `[github].default_repo` if omitted |
| `resource_type` | Cloud resource type — used to scope metric queries to the right namespace |

---

### `[profiles.<name>.notifiers.<name>]` — Alert notifiers

Notifiers define where watch alerts are sent. A profile can have multiple notifiers.

**Slack notifier:**
```toml
[profiles.aws-prod.notifiers.team-slack]
type      = "slack"
bot_token = "env:SLACK_BOT_TOKEN"
channel   = "#prod-incidents"
```

**Webhook notifier** (PagerDuty, Opsgenie, custom):
```toml
[profiles.aws-prod.notifiers.pagerduty]
type                 = "webhook"
url                  = "env:PAGERDUTY_WEBHOOK_URL"
header_Authorization = "env:PAGERDUTY_API_KEY"   # Any header: header_<Name> = <value>
```

**Discord notifier:**
```toml
[profiles.aws-prod.notifiers.discord-ops]
type = "webhook"
url  = "env:DISCORD_OPS_WEBHOOK_URL"
```

| Key | Description |
|---|---|
| `type` | `slack` or `webhook` |
| `channel` | Slack channel (slack type only) |
| `url` | Webhook URL (webhook type only) |
| `header_<Name>` | Any HTTP header to add to webhook requests, e.g. `header_Authorization` |

---

## Full config.toml — all backends

A complete reference showing every backend and feature in one file. In practice you'll only use the sections relevant to your stack.

```toml
# ── CLI connection ────────────────────────────────────────────────────────────
[server]
url   = "https://tinkr.acme.internal"
token = "env:TINKR_API_TOKEN"


# ── Server authentication ─────────────────────────────────────────────────────
[auth]
api_keys = [
  { hash = "<sha256>", subject = "alice@acme.com", roles = ["oncall"]  },
  { hash = "<sha256>", subject = "bob@acme.com",   roles = ["viewer"]  },
  { hash = "<sha256>", subject = "ci-bot",         roles = ["viewer"]  },
  { hash = "<sha256>", subject = "slack-bot",      roles = ["sre-lead"] },
]


# ── GitHub ────────────────────────────────────────────────────────────────────
[github]
token        = "env:GITHUB_TOKEN"
default_repo = "acme/monorepo"


# ── Slack bot ─────────────────────────────────────────────────────────────────
[slack]
bot_token      = "env:SLACK_BOT_TOKEN"
signing_secret = "env:SLACK_SIGNING_SECRET"
alerts_channel = "#incidents"


# ── Profile: Grafana (local dev / self-hosted) ────────────────────────────────
[profiles.default]
backend        = "grafana"
loki_url       = "env:GRAFANA_LOKI_URL"
prometheus_url = "env:GRAFANA_PROMETHEUS_URL"
tempo_url      = "env:GRAFANA_TEMPO_URL"

[profiles.default.services.payments-api]
repo          = "acme/payments"
resource_type = "k8s"

[profiles.default.notifiers.slack-dev]
type      = "slack"
bot_token = "env:SLACK_BOT_TOKEN"
channel   = "#dev-alerts"


# ── Profile: AWS CloudWatch ───────────────────────────────────────────────────
[profiles.aws-prod]
backend          = "cloudwatch"
region           = "us-east-1"
log_group_prefix = "/ecs/"          # Scope log queries to ECS log groups
active           = true             # Default profile

[profiles.aws-prod.services.payments-api]
repo          = "acme/payments"
resource_type = "ecs"

[profiles.aws-prod.services.auth-service]
repo          = "acme/auth"
resource_type = "ecs"

[profiles.aws-prod.services.batch-worker]
repo          = "acme/batch"
resource_type = "lambda"

[profiles.aws-prod.notifiers.pagerduty]
type                 = "webhook"
url                  = "env:PAGERDUTY_WEBHOOK_URL"
header_Authorization = "env:PAGERDUTY_API_KEY"

[profiles.aws-prod.notifiers.slack-oncall]
type      = "slack"
bot_token = "env:SLACK_BOT_TOKEN"
channel   = "#prod-incidents"

# Second AWS region — separate profile
[profiles.aws-eu]
backend          = "cloudwatch"
region           = "eu-west-1"
log_group_prefix = "/ecs/"

[profiles.aws-eu.services.payments-api]
repo          = "acme/payments"
resource_type = "ecs"


# ── Profile: GCP ─────────────────────────────────────────────────────────────
[profiles.gcp-prod]
backend    = "gcp"
project_id = "acme-prod-123456"

[profiles.gcp-prod.services.checkout-service]
repo          = "acme/checkout"
resource_type = "cloud_run"

[profiles.gcp-prod.notifiers.discord-sre]
type = "webhook"
url  = "env:DISCORD_SRE_WEBHOOK_URL"

# GCP staging — same project structure, different project ID
[profiles.gcp-staging]
backend    = "gcp"
project_id = "acme-staging-789012"

[profiles.gcp-staging.services.checkout-service]
repo          = "acme/checkout"
resource_type = "cloud_run"


# ── Profile: Azure ────────────────────────────────────────────────────────────
[profiles.azure-prod]
backend         = "azure"
workspace_id    = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # Log Analytics workspace
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
resource_group  = "prod-rg"

[profiles.azure-prod.services.api-gateway]
repo          = "acme/api-gateway"
resource_type = "container_app"

[profiles.azure-prod.notifiers.opsgenie]
type                 = "webhook"
url                  = "env:OPSGENIE_WEBHOOK_URL"
header_Authorization = "env:OPSGENIE_API_KEY"


# ── Profile: Datadog ──────────────────────────────────────────────────────────
[profiles.datadog-prod]
backend = "datadog"
site    = "datadoghq.com"       # EU: datadoghq.eu

[profiles.datadog-prod.services.payments-api]
repo          = "acme/payments"
resource_type = "ecs"

[profiles.datadog-prod.notifiers.pagerduty]
type                 = "webhook"
url                  = "env:PAGERDUTY_WEBHOOK_URL"
header_Authorization = "env:PAGERDUTY_API_KEY"


# ── Profile: Elasticsearch ────────────────────────────────────────────────────
[profiles.elastic-prod]
backend       = "elastic"
url           = "env:ELASTIC_URL"
index_pattern = "logs-*,filebeat-*"     # Comma-separated index patterns

[profiles.elastic-prod.services.search-service]
repo          = "acme/search"
resource_type = "k8s"

[profiles.elastic-prod.notifiers.slack-search-team]
type      = "slack"
bot_token = "env:SLACK_BOT_TOKEN"
channel   = "#search-oncall"


# ── Profile: OpenTelemetry ────────────────────────────────────────────────────
[profiles.otel-prod]
backend        = "otel"
opensearch_url = "env:OTEL_OPENSEARCH_URL"
prometheus_url = "env:OTEL_PROMETHEUS_URL"

[profiles.otel-prod.services.inventory-service]
repo          = "acme/inventory"
resource_type = "k8s"
```

---

## Full .env reference

```bash title="~/.tinkr/.env"
# ── LLM ───────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
# OPENROUTER_API_KEY=sk-or-...
# OPENAI_API_KEY=sk-...
# GROQ_API_KEY=gsk_...

# ── CLI ───────────────────────────────────────────────────────────────────────
TINKR_SERVER_URL=https://tinkr.acme.internal
TINKR_API_TOKEN=<raw-token>

# ── Server auth ───────────────────────────────────────────────────────────────
TINKR_API_KEYS='[{"hash":"<sha256>","subject":"alice","roles":["oncall"]}]'

# ── Backend: Grafana ──────────────────────────────────────────────────────────
GRAFANA_LOKI_URL=http://loki:3100
GRAFANA_PROMETHEUS_URL=http://prometheus:9090
GRAFANA_TEMPO_URL=http://tempo:3200
# Grafana Cloud:
# GRAFANA_API_KEY=glc_...

# ── Backend: CloudWatch ───────────────────────────────────────────────────────
AWS_REGION=us-east-1
# No access keys in production — use IAM role on EC2/ECS

# ── Backend: GCP ──────────────────────────────────────────────────────────────
GCP_PROJECT_ID=acme-prod-123456
# No service account key in production — use Workload Identity

# ── Backend: Azure ────────────────────────────────────────────────────────────
AZURE_LOG_ANALYTICS_WORKSPACE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_RESOURCE_GROUP=prod-rg
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx   # Managed Identity client ID
# AZURE_TENANT_ID=...     # Only for local dev with Service Principal
# AZURE_CLIENT_SECRET=... # Avoid in prod — use Managed Identity

# ── Backend: Datadog ──────────────────────────────────────────────────────────
DD_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DD_APP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DD_SITE=datadoghq.com

# ── Backend: Elasticsearch ────────────────────────────────────────────────────
ELASTIC_URL=https://elastic.acme.internal:9200
ELASTIC_API_KEY=VnVhQ2ZHY0JDZGJrZXctATxxxxxxxxxxxxxxxx==

# ── Backend: OTel / OpenSearch ────────────────────────────────────────────────
OTEL_OPENSEARCH_URL=http://opensearch:9200
OTEL_PROMETHEUS_URL=http://prometheus:9090

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN=github_pat_xxxxxxxxxxxxxxxx

# ── Slack ─────────────────────────────────────────────────────────────────────
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
SLACK_SIGNING_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Notifiers ─────────────────────────────────────────────────────────────────
PAGERDUTY_WEBHOOK_URL=https://events.pagerduty.com/integration/XXXX/enqueue
PAGERDUTY_API_KEY=Token token=XXXX
OPSGENIE_WEBHOOK_URL=https://api.opsgenie.com/v2/alerts
OPSGENIE_API_KEY=GenieKey XXXX
DISCORD_SRE_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/xxxx
DISCORD_OPS_WEBHOOK_URL=https://discord.com/api/webhooks/0987654321/xxxx

# ── Agent behaviour ───────────────────────────────────────────────────────────
TINKR_DEFAULT_MODEL=anthropic/claude-sonnet-4-6
TINKR_DEEP_RCA_MODEL=anthropic/claude-opus-4-6
TINKR_LOG_LEVEL=INFO
```

---

## Environment variable precedence

Tinkr reads configuration in this order (later wins):

1. Process environment (injected by cloud secrets manager at container start)
2. `~/.tinkr/.env`
3. `config.toml` `env:` references (resolved from #1 and #2)

---

## Setup wizards

The interactive wizards generate both files from prompts:

```bash
# Set up the server (run on the machine with cloud access)
tinkr-server init

# Connect the CLI to a running server (run on developer machines)
tinkr init
```

`tinkr-server init` walks through: LLM provider → Slack → GitHub → server API key → backend profile.
