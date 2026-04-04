# Tinker

Open-source AI-powered observability and incident response agent. Tinker runs in your cloud, monitors your infrastructure, cross-references incidents with your codebase, and suggests fixes — with human approval before any code changes.

Works with every major cloud provider and observability stack out of the box.

---

## How it works

```
┌──────────────────────────────────────────────────────────────────┐
│  Tinker Server  (deploy once in your cloud account)              │
│                                                                  │
│  POST /api/v1/analyze  ──► SSE streaming RCA                     │
│  GET  /mcp/sse         ──► Remote MCP for Claude Code / editors  │
│  POST /slack/events    ──► Slack bot                             │
│  GET  /health                                                    │
│                                                                  │
│  Active backend (one env var):                                   │
│  cloudwatch | gcp | azure | grafana | datadog | elastic          │
│                                                                  │
│  Credentials → cloud-native identity. Zero long-lived keys.      │
└───────────────────────┬──────────────────────────────────────────┘
                        │  API key
          ┌─────────────┼──────────────────┐
          ▼             ▼                  ▼
       CLI           Claude Code        Slack Bot
      (thin)         remote MCP         (webhook)
                     over SSE
```

1. **Tinker Server** runs in your cloud with a read-only IAM role / Managed Identity — no credentials in code or containers
2. **CLI and Slack bot** are thin clients authenticated to the server via a short API key
3. **Claude Code** connects via the `/mcp/sse` endpoint as a remote MCP server
4. Set `TINKER_BACKEND` to point at your observability stack — the rest is automatic

---

## Supported backends

| Backend | Logs | Metrics | Traces | Auth (no long-lived keys) |
|---|---|---|---|---|
| `cloudwatch` | CloudWatch Logs Insights | CloudWatch Metrics | X-Ray | ECS Task Role / Lambda Execution Role |
| `gcp` | Cloud Logging | Cloud Monitoring | Cloud Trace | Workload Identity (Cloud Run SA) |
| `azure` | Log Analytics / KQL | Azure Monitor Metrics | Application Insights | Managed Identity |
| `grafana` | Loki / LogQL | Prometheus / PromQL | Tempo | API key or basic auth |
| `datadog` | Logs API v2 | Metrics API v1 | APM Traces | API key + App key |
| `elastic` | Elasticsearch / OpenSearch | Aggregations | APM | API key |

All backends accept the same **unified query syntax** — you never need to learn backend-specific query languages. See [Unified query language](#unified-query-language) below.

---

## Quick start

### The fast path — `tinker init`

One command walks you through everything: cloud selection, IAM setup, LLM provider, Slack, GitHub, and optionally deploys the server.

```bash
pip install tinker-agent   # or: uv add tinker-agent
tinker init
```

```
? Which cloud provider are you using?
  ❯ AWS
    GCP (Google Cloud)
    Azure
    Self-hosted (Grafana + Prometheus)
    Datadog
    Elastic / OpenSearch

? Where will the Tinker server run?
  ❯ AWS ECS Fargate (recommended)
    Docker Compose (local/VM)

? Which LLM provider do you want to use?
  ❯ Anthropic (Claude) — direct
    OpenRouter — access 100+ models
    OpenAI (GPT-4o etc.)
    Groq — fast open-source models

  Anthropic API key: ****

? Enable Slack bot integration? (y/N)
? Enable GitHub integration? (y/N)

✓ Config written to .env
✓ Deploy config written to tinker.toml

Your Tinker API key (save this):
  aBcDeFgHiJkL...

? Deploy the Tinker server now? (Y/n)
```

That's it. `tinker init` handles IAM role creation, generates and hashes your API key, writes `.env`, and optionally runs `tinker deploy`.

---

### Manual setup

If you prefer to configure things yourself:

```bash
git clone https://github.com/your-org/tinker.git
cd tinker
uv sync
cp .env.example .env        # edit with your values
uv run tinker-server        # start the server
```

For a full local development environment with a realistic dummy service, see [Local development](#local-development) below.

---

## CLI reference

```bash
# ── Setup ────────────────────────────────────────────────────────
tinker init                                  # interactive setup wizard
tinker deploy                                # deploy server to configured cloud
tinker doctor                                # verify all services are reachable
tinker version

# ── Analysis ─────────────────────────────────────────────────────
tinker analyze payments-api                  # RCA for the last hour
tinker analyze payments-api --since 2h -v   # stream agent reasoning
tinker analyze payments-api --deep          # extended thinking (Claude Opus)

# ── Fix workflow ──────────────────────────────────────────────────
tinker fix INC-abc123                        # show proposed fix
tinker fix INC-abc123 --approve             # validate + apply + open PR

# ── Raw observability (no AI) ─────────────────────────────────────
tinker tail payments-api                             # stream live logs
tinker tail payments-api -q "level:ERROR"            # stream filtered live logs
tinker tail payments-api -q 'level:(ERROR OR WARN) AND "timeout"'
tinker logs payments-api                             # fetch recent logs
tinker logs payments-api -q "level:ERROR" --since 30m -n 100
tinker metrics payments-api Errors --since 2h
tinker monitor --services payments-api,auth-service

# ── Help ──────────────────────────────────────────────────────────
tinker help
```

---

## Live log streaming — `tinker tail`

`tinker tail` streams new log entries as they arrive, using the backend's native streaming where available and falling back to polling elsewhere.

```bash
tinker tail payments-api                              # all logs
tinker tail payments-api -q "level:ERROR"             # errors only
tinker tail payments-api -q 'level:(ERROR OR WARN) AND "database"'
tinker tail auth-service --poll 5                     # poll every 5s
```

| Backend | Mechanism | Latency |
|---|---|---|
| `grafana` / Loki | Native websocket (`/loki/api/v1/tail`) | Real-time |
| `cloudwatch` | Poll `query_logs` every N seconds | ≈ poll interval |
| `gcp` | Poll `query_logs` every N seconds | ≈ poll interval |
| `azure` | Poll `query_logs` every N seconds | ≈ poll interval |
| `datadog` | Poll `query_logs` every N seconds | ≈ poll interval |
| `elastic` | Poll `query_logs` every N seconds | ≈ poll interval |

The Loki websocket tail automatically falls back to polling if `websockets` is not installed or the connection fails.

All [unified query syntax](#unified-query-language) works the same way — `level:ERROR`, `"timeout"`, `NOT "health check"`, etc.

---

## Supported LLM providers

Tinker uses [LiteLLM](https://github.com/BerriAI/litellm) — swap providers by changing one env var, no code changes needed.

| Provider | `TINKER_DEFAULT_MODEL` example | Key variable |
|---|---|---|
| Anthropic (direct) | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| OpenRouter | `openrouter/anthropic/claude-opus-4-6` | `OPENROUTER_API_KEY` |
| OpenRouter | `openrouter/openai/gpt-4o` | `OPENROUTER_API_KEY` |
| OpenRouter | `openrouter/meta-llama/llama-3.1-70b-instruct` | `OPENROUTER_API_KEY` |
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |
| Groq | `groq/llama-3.1-70b-versatile` | `GROQ_API_KEY` |
| Ollama (local) | `ollama/llama3` | — |

`tinker init` lets you pick the provider interactively and sets all of this up.

---

## Slack bot

Invite `@tinker` to any channel:

```
/tinker-analyze payments-api since=2h
/tinker-fix INC-abc123
/tinker-approve INC-abc123          (requires oncall role)
/tinker-status
/tinker-help
```

The bot posts proactive alerts when the monitoring loop detects anomalies.
Alerts include inline buttons: **Get Fix** / **Approve** / **Dismiss**.

---

## Claude Code (remote MCP)

Once deployed, add Tinker as a remote MCP server in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "tinker": {
      "transport": "sse",
      "url": "https://tinker.your-company.internal/mcp/sse",
      "headers": {
        "Authorization": "Bearer ${TINKER_API_TOKEN}"
      }
    }
  }
}
```

Claude can then call `query_logs`, `get_metrics`, `detect_anomalies`, `search_code`, and `suggest_fix` directly from your editor — against your live production observability backend.

---

## Deployment

### Automated — `tinker deploy`

After running `tinker init`, deploy with one command:

```bash
tinker deploy
```

This reads `tinker.toml` and handles the full flow for your cloud:

| Cloud | What `tinker deploy` does |
|---|---|
| **AWS ECS** | Creates ECR repo → builds + pushes image → registers ECS task definition → creates/updates ECS service |
| **GCP Cloud Run** | Cloud Build or local Docker → Artifact Registry → `gcloud run services replace` |
| **Azure Container Apps** | `az acr build` → `az containerapp create` |
| **Self-hosted** | `docker compose up --build -d` |

### Manual deployment

<details>
<summary>AWS ECS Fargate</summary>

```bash
# 1. Create the read-only IAM role
aws iam create-role --role-name tinker-readonly \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam put-role-policy --role-name tinker-readonly \
  --policy-name TinkerReadOnly \
  --policy-document file://deploy/aws/iam-policy.json

# 2. Store secrets in Secrets Manager
aws secretsmanager create-secret --name tinker/anthropic-api-key --secret-string "sk-ant-..."

# 3. Build, push, deploy
aws ecr create-repository --repository-name tinker
docker build -f deploy/Dockerfile -t <ecr-url>/tinker:latest .
docker push <ecr-url>/tinker:latest
aws ecs register-task-definition --cli-input-json file://deploy/aws/task-definition.json
```

See [deploy/aws/task-definition.json](deploy/aws/task-definition.json) — the task role and Secrets Manager wiring are already configured.
</details>

<details>
<summary>GCP Cloud Run</summary>

```bash
# 1. Create service account
gcloud iam service-accounts create tinker-readonly
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:tinker-readonly@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.viewer"
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:tinker-readonly@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.viewer"

# 2. Store secrets
echo -n "sk-ant-..." | gcloud secrets create tinker-anthropic-api-key --data-file=-

# 3. Deploy
gcloud run services replace deploy/gcp/cloudrun.yaml
```

See [deploy/gcp/cloudrun.yaml](deploy/gcp/cloudrun.yaml).
</details>

<details>
<summary>Azure Container Apps</summary>

```bash
# 1. Deploy (managed identity created automatically)
az containerapp create --yaml deploy/azure/container-app.yaml

# 2. Assign roles to the managed identity
az role assignment create --assignee <principal-id> \
  --role "Monitoring Reader" --scope /subscriptions/SUBSCRIPTION_ID
az role assignment create --assignee <principal-id> \
  --role "Log Analytics Reader" --scope /subscriptions/SUBSCRIPTION_ID
```

See [deploy/azure/container-app.yaml](deploy/azure/container-app.yaml).
</details>

---

## Configuration

`tinker init` writes all of this for you. For manual configuration:

### Core (all deployments)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key — or use `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` |
| `TINKER_BACKEND` | Active backend: `cloudwatch` `gcp` `azure` `grafana` `datadog` `elastic` |
| `TINKER_DEFAULT_MODEL` | LiteLLM model string, e.g. `anthropic/claude-sonnet-4-6` |
| `TINKER_DEEP_RCA_MODEL` | Model for `--deep` analysis, e.g. `anthropic/claude-opus-4-6` |
| `TINKER_API_KEYS` | JSON array of hashed client keys (generated by `tinker init`) |
| `TINKER_SERVER_PORT` | Default `8000` |

### Per-backend

| Backend | Variables |
|---|---|
| `cloudwatch` | `AWS_REGION` — credentials from IAM role (no keys needed) |
| `gcp` | `GCP_PROJECT_ID` — credentials from Workload Identity (no keys needed) |
| `azure` | `AZURE_LOG_ANALYTICS_WORKSPACE_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` |
| `grafana` | `GRAFANA_LOKI_URL`, `GRAFANA_PROMETHEUS_URL`, `GRAFANA_TEMPO_URL` |
| `datadog` | `DATADOG_API_KEY`, `DATADOG_APP_KEY`, `DATADOG_SITE` |
| `elastic` | `ELASTICSEARCH_URL`, `ELASTICSEARCH_API_KEY` |

See [.env.example](.env.example) for the complete reference with comments.

### Managing client API keys

`tinker init` generates and hashes a key automatically. To add more:

```bash
# Generate
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Hash (store hash on server, give raw key to client)
python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" <raw-key>

# Add to server env
TINKER_API_KEYS='[{"hash":"<sha256>","subject":"alice","roles":["sre"]}]'
```

---

## Security

| Concern | How Tinker handles it |
|---|---|
| Cloud credentials | Never stored — server uses IAM role / Workload Identity / Managed Identity |
| Client auth | API keys (SHA-256 hashed at rest) or short-lived JWTs via your IdP |
| Destructive operations | `apply_fix` and `create_pr` require explicit `/approve` — blocked by default in Claude Code |
| RBAC | Slack commands gated by user group → role mapping |
| Prompt injection | Log content sanitized with regex before inclusion in any LLM prompt |
| Fix safety | Proposed diffs scanned with Semgrep before being shown to the user |
| Audit trail | Every agent tool call logged with actor, session ID, timestamp, and approval chain |
| Secrets in logs | Credentials stripped from all log data before LLM submission |

---

## Verify your setup

```bash
tinker doctor
```

```
╭─────────────────────────────────────────────────────────╮
│  Tinker Doctor                                          │
╰─────────────────────────────────────────────────────────╯

Check    Status   Detail
──────   ──────   ──────────────────────────────────────────
LLM      ✓ OK     anthropic/claude-sonnet-4-6 → OK
Backend  ✓ OK     cloudwatch
Slack    ✓ OK     auth_test passed
GitHub   ✓ OK     authenticated

All checks passed.
```

---

## Unified query language

Tinker uses a single query syntax across all backends. You write it once; Tinker translates it to CloudWatch Logs Insights, LogQL, GCP filter, KQL, Datadog search, or Elasticsearch DSL automatically.

### Syntax

| Pattern | Meaning |
|---|---|
| `level:ERROR` | Field match |
| `level:(ERROR OR WARN)` | Multi-value field match |
| `"connection timeout"` | Exact phrase |
| `timeout` | Substring match |
| `level:ERROR AND "timeout"` | Logical AND (explicit) |
| `level:ERROR "timeout"` | Logical AND (implicit) |
| `level:ERROR OR level:WARN` | Logical OR |
| `NOT "health check"` | Negation |
| `(level:ERROR OR level:WARN) AND service:payments-api` | Grouped expressions |

### Field aliases

`severity` → `level`, `svc` / `app` → `service`, `msg` → `message`, `trace` → `trace_id`

### Resource targeting

Use `resource:TYPE` to tell Tinker which infrastructure resource to query. Without it, each backend uses its default (Lambda for CloudWatch, Cloud Run for GCP, AppTraces for Azure, etc.).

| Resource type | CloudWatch log group | GCP resource.type | Azure KQL table | Loki label | ES index |
|---|---|---|---|---|---|
| `resource:lambda` | `/aws/lambda/{svc}` | `cloud_function` | `FunctionAppLogs` | `resource="lambda"` | `lambda-*` |
| `resource:ecs` | `/ecs/{svc}` | `cloud_run_revision` | `ContainerLog` | `resource="container"` | `ecs-*` |
| `resource:eks` | `/aws/containerinsights/{svc}/application` | `k8s_container` | `ContainerLog` | `resource="container"` | `kubernetes-*` |
| `resource:ec2` | `/aws/ec2/{svc}` | `gce_instance` | `Syslog` | `resource="host"` | `syslog-*` |
| `resource:rds` | `/aws/rds/instance/{svc}/postgresql` | `cloudsql_database` | `AzureDiagnostics` | `resource="db"` | `rds-*` |
| `resource:apigw` | `API-Gateway-Execution-Logs_{svc}/prod` | — | `ApiManagementGatewayLogs` | `resource="apigw"` | `apigw-*` |
| `resource:cloudrun` | `/ecs/{svc}` | `cloud_run_revision` | `ContainerLog` | `resource="container"` | `ecs-*` |
| `resource:gke` | `/aws/containerinsights/{svc}/application` | `k8s_container` | `ContainerLog` | `resource="container"` | `kubernetes-*` |
| `resource:aks` | `/ecs/{svc}` | `k8s_container` | `ContainerLog` | `resource="container"` | `kubernetes-*` |
| `resource:vm` | `/aws/ec2/{svc}` | `gce_instance` | `Syslog` | `resource="host"` | `syslog-*` |
| `resource:appservice` | — | — | `AppServiceConsoleLogs` | `resource="container"` | `appservice-*` |
| (none) | auto-discover via `describe_log_groups` | `cloud_run_revision` | `AppTraces` | — | `logs-*` |

Cross-cloud aliases (`resource:lambda` on GCP, `resource:ecs` on Azure, etc.) map to the closest equivalent — you never need to rewrite queries when switching backends.

### Examples

```bash
# Same query works on every backend — for both tail and logs
tinker tail payments-api  -q 'level:ERROR AND "timeout"'
tinker tail auth-service  -q 'level:(ERROR OR WARN) AND "database"'
tinker logs payments-api  -q 'level:ERROR AND "timeout"' --since 1h
tinker logs orders-api    -q 'NOT "health check" AND level:ERROR'

# Target a specific infrastructure resource type
tinker logs payments-api  -q 'resource:lambda AND level:ERROR'
tinker logs orders-api    -q 'resource:ecs AND "OOMKilled"'
tinker logs user-api      -q 'resource:rds AND level:ERROR AND "deadlock"'
tinker logs ingress       -q 'resource:apigw AND level:ERROR'
```

### How it maps

| Tinker query | CloudWatch | LogQL | GCP filter | KQL | Datadog |
|---|---|---|---|---|---|
| `level:ERROR` | `level = 'ERROR'` | `{level="ERROR"}` | `severity="ERROR"` | `SeverityLevel == "Error"` | `status:error` |
| `"timeout"` | `@message like /timeout/` | `\|= \`timeout\`` | `textPayload:"timeout"` | `Message contains "timeout"` | `"timeout"` |
| `level:(ERROR OR WARN)` | `level in ['ERROR','WARN']` | `level=~\`ERROR\|WARN\`` | `(severity="ERROR" OR severity="WARNING")` | `SeverityLevel in ("Error","Warning")` | `status:(error OR warn)` |
| `resource:ecs` | log group `/ecs/{svc}` | `{resource="container"}` | `resource.type="cloud_run_revision"` | table `ContainerLog` | (stripped) |

Raw backend-native queries (LogQL `{...}`, Insights `| filter ...`, KQL `| where ...`) are still accepted and passed through unchanged.

---

## Local development

The [`local-dev/`](local-dev/) directory contains everything you need to develop Tinker against a real observability stack without a cloud account.

### What's in the stack

| Service | Port | Purpose |
|---|---|---|
| `payments-api` | 7000 | Dummy microservice — emits structured logs at all levels + Prometheus metrics |
| `loki` | 3100 | Log storage |
| `prometheus` | 9090 | Metrics (scrapes payments-api + host Tinker server) |
| `grafana` | 3000 | Visual dashboards |

The Tinker server is **not** in this compose — you run it from your IDE so you get hot reload, breakpoints, and logs in your terminal.

### Setup

**1. Start the infrastructure:**

```bash
cd local-dev
./run.sh
```

**2. Start the Tinker server in your IDE / terminal:**

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and these backend vars:
#   TINKER_BACKEND=grafana
#   GRAFANA_LOKI_URL=http://localhost:3100
#   GRAFANA_PROMETHEUS_URL=http://localhost:9090
#   GRAFANA_TEMPO_URL=http://localhost:3200

uv run tinker-server
# Server → http://localhost:8000
```

**3. Generate traffic against the dummy service:**

```bash
cd local-dev

# Steady mixed traffic until Ctrl-C (60% ok, 15% error, 10% warn, 10% slow, 5% debug)
./generate_traffic.sh

# Simulate an incident: error spike followed by a circuit breaker opening
./generate_traffic.sh incident

# Fire 100 rapid requests then exit
./generate_traffic.sh burst

# Quiet mode — only ok + debug, no errors
./generate_traffic.sh quiet
```

**4. Analyze with Tinker:**

```bash
tinker tail payments-api                             # live stream
tinker tail payments-api -q 'level:ERROR'            # filtered live stream
tinker analyze payments-api --since 5m -v
tinker logs payments-api -q 'level:ERROR AND "timeout"'
```

### Dummy service endpoints

| Endpoint | Emits |
|---|---|
| `GET /pay` | Random weighted scenario |
| `GET /pay/ok` | INFO — successful payment |
| `GET /pay/error` | ERROR — payment failed (random error message) |
| `GET /pay/slow` | WARN — slow database query |
| `GET /pay/warn` | WARN — retry scenario |
| `GET /pay/critical` | CRITICAL — circuit breaker open |
| `GET /pay/debug` | DEBUG — cache hit |
| `GET /metrics` | Prometheus metrics |
| `GET /health` | Health check |

### Tear down

```bash
cd local-dev && ./run.sh down
```

---

## Development

```bash
uv sync
uv run pytest                    # all tests
uv run pytest -k backend         # backend unit tests only
uv run pytest tests/test_query/  # unified query language tests
uv run ruff check src/           # lint
uv run mypy src/                 # type check
```

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the phased roadmap.

---

## License

MIT
