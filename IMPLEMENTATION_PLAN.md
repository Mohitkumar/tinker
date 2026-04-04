# Tinker — Implementation Plan

## Status legend
- ✅ Complete
- 🔄 Partial / in progress
- [ ] Not started

---

## Phase 0: Project Skeleton ✅

**Goal:** Runnable project with config loading, logging, and a smoke-test CLI command.

- [x] Directory structure and `pyproject.toml`
- [x] `ObservabilityBackend` ABC and data models (`LogEntry`, `MetricPoint`, `Anomaly`)
- [x] `config.py` with pydantic-settings (all env vars, fails fast on missing required)
- [x] All 6 backend stubs (`cloudwatch`, `gcp`, `azure`, `grafana`, `datadog`, `elastic`)
- [x] Agent orchestrator, tool definitions, guardrails
- [x] CLI skeleton (Typer + Rich)
- [x] Slack bot skeleton (Bolt)
- [x] MCP server base class + provider servers + GitHub server
- [x] FastAPI server skeleton with auth, SSE routes, MCP-over-SSE endpoint
- [x] ~~Raw cloud manifests (ECS/Cloud Run/Container Apps)~~ → replaced by Helm chart + Terraform modules (see Phase 0.1)
- [x] `CLAUDE.md`, `README.md`, `.gitignore`, `.env.example`
- [x] Test stubs for backends, agent, MCP servers

**Deliverable:** `tinker version` works; all imports succeed.

---

## Phase 0.1: Infra Scaffolding ✅

Deployment tooling that the platform team uses — separate from the CLI.

- [x] `deploy/Dockerfile` — production image
- [x] `deploy/docker-compose.yml` — server + Loki + Prometheus + Grafana
- [x] `deploy/helm/tinker/` — production Helm chart (EKS / GKE / AKS)
  - [x] `Chart.yaml`, `values.yaml`
  - [x] `templates/deployment.yaml` — secrets from Kubernetes Secret, not baked in
  - [x] `templates/service.yaml`, `templates/ingress.yaml`
  - [x] `templates/serviceaccount.yaml` — IRSA / Workload Identity / Azure WI annotations
  - [x] `templates/hpa.yaml` — optional autoscaling
- [x] `deploy/terraform/aws/` — ECS Fargate module (cluster, task def, IAM role, ECR, log group)
- [x] `deploy/terraform/gcp/` — Cloud Run module (service account, roles, Secret Manager, Cloud Run)
- [x] `deploy/terraform/azure/` — Container Apps module (Key Vault, managed identity, role assignments)
- [x] `tinker init` deploy mode generates `tinker-values.yaml` (Helm) or `tinker.tfvars` (Terraform) — no cloud commands run from the CLI

---

## Phase 1: Backends — Real Queries ✅

**Goal:** Each backend returns real data from its provider.

### 1.1 CloudWatch ✅
- [x] `query_logs` — Logs Insights, polls until complete
- [x] `get_metrics` — `GetMetricData` with period/stat
- [x] `detect_anomalies` — error count threshold
- [x] Log group auto-discovery via `describe_log_groups` when no `resource:TYPE` present
- [x] Multi-log-group queries (`logGroupNames=[...]`)
- [ ] X-Ray trace search via `BatchGetTraces`
- [ ] Unit tests with `moto[logs,cloudwatch]`

### 1.2 Grafana Stack ✅
- [x] `query_logs` — Loki LogQL, label selector, unified query translation
- [x] `get_metrics` — Prometheus range query via `/api/v1/query_range`
- [x] `detect_anomalies` — Loki error count + Prometheus 5xx rate
- [x] `tail_logs` — native Loki websocket (`/loki/api/v1/tail`), fallback to poll
- [ ] Tempo search API
- [x] Unit tests with `respx`

### 1.3 GCP ✅
- [x] `query_logs` — Cloud Logging filter, unified query translation
- [x] `get_metrics` — Cloud Monitoring timeseries
- [x] `detect_anomalies`
- [ ] Cloud Trace integration
- [ ] Unit tests with VCR cassettes

### 1.4 Azure ✅
- [x] `query_logs` — KQL query via Log Analytics workspace
- [x] `get_metrics` — Azure Monitor Metrics
- [x] `detect_anomalies`
- [ ] App Insights dependency trace lookup
- [ ] Unit tests with `pytest-mock`

### 1.5 Datadog ✅
- [x] `query_logs` — Logs Search API v2
- [x] `get_metrics` — Metrics API v1
- [x] `detect_anomalies`
- [ ] APM Traces API v2
- [ ] Unit tests with `respx`

### 1.6 Elasticsearch / OpenSearch ✅
- [x] `query_logs` — DSL bool query, OTel field mapping, resource-aware index routing
- [x] `get_metrics` — date_histogram aggregation
- [ ] Unit tests with VCR cassettes

**Deliverable:** `tinker logs <service> --since 30m` returns real log entries from all backends.

---

## Phase 1.5: Unified Query Language ✅

**Goal:** One query syntax works across all backends. Never write CloudWatch Insights or LogQL manually.

- [x] `src/tinker/query/ast.py` — `TextFilter`, `FieldFilter`, `AndExpr`, `OrExpr`, `NotExpr` + field aliases
- [x] `src/tinker/query/parser.py` — recursive-descent parser (Lucene-lite syntax)
- [x] `src/tinker/query/resource.py` — resource type routing tables for all backends + `extract_resource()`
- [x] Translators:
  - [x] `translators/cloudwatch.py` — Logs Insights filter + `resolve_log_groups()`
  - [x] `translators/gcp.py` — GCP filter string + resource.type routing
  - [x] `translators/azure.py` — KQL expression + per-table field maps + KQL table routing
  - [x] `translators/loki.py` — LogQL stream selector + line filters + resource label routing
  - [x] `translators/elastic.py` — ES DSL dict + `resolve_index()` per resource type
  - [x] `translators/datadog.py` — Datadog search syntax
- [x] `resource:TYPE` field — routes to correct log group / resource.type / KQL table / Loki label / ES index
- [x] Cross-cloud aliases — `resource:lambda` on GCP maps to `cloud_function`, `resource:ecs` on Azure maps to `ContainerLog`, etc.
- [x] Raw native query passthrough — LogQL `{...}`, Insights `| filter`, KQL `| where` accepted unchanged
- [x] 75 tests across all translators including resource routing

**Deliverable:** `tinker logs payments-api -q 'resource:ecs AND level:ERROR AND "timeout"'` works against every backend.

---

## Phase 2: Agent Core — Real RCA 🔄

**Goal:** Claude analyzes a real incident end-to-end and produces a structured `IncidentReport`.

### 2.1 Tool implementations
- [x] `query_logs` tool — complete, backend routing
- [x] `get_metrics` tool — complete
- [x] `detect_anomalies` tool — complete
- [ ] `get_recent_errors` — convenience wrapper
- [ ] `search_traces` — distributed trace lookup
- [ ] `get_file` + `search_code` + `get_recent_commits` + `blame` — codebase tools

### 2.2 Orchestrator
- [x] Agentic loop — Claude → tool calls → results → iterate until `end_turn`
- [x] `stream_analyze` — token-streaming for CLI `--verbose` and SSE
- [x] Model routing — `claude-sonnet-4-6` default, `claude-opus-4-6` + thinking for `--deep`
- [ ] `IncidentReport` structured extraction from final agent response
- [ ] `MAX_ITERATIONS` guard and graceful degradation

### 2.3 Prompt refinement
- [x] RCA system prompt skeleton
- [ ] Structured output prompt — reliable JSON for `IncidentReport` fields
- [ ] Monitoring triage prompt — fast severity classification

### 2.4 CLI integration
- [x] `tinker analyze <service>` — RCA with Rich-formatted output
- [x] `tinker logs <service>` — raw logs (no AI)
- [x] `tinker metrics <service> <metric>` — metric values
- [x] `--verbose` flag streams agent reasoning

**Deliverable:** `tinker analyze payments-api --since 1h` produces a structured incident report with root cause, severity, and evidence.

---

## Phase 3: Fix Suggestion & Guardrails 🔄

**Goal:** Agent proposes code fixes with safety validation. Human reviews before anything is applied.

### 3.1 Fix suggestion
- [ ] `suggest_fix` tool — stores diff in session, never applies automatically
- [ ] `IncidentReport.suggested_fix` and `fix_diff` populated
- [ ] Structured diff format validated (must be proper unified diff)

### 3.2 Fix validation
- [ ] `FixValidator.scan(diff)` — Semgrep on changed files
- [ ] Block HIGH/CRITICAL findings, report MEDIUM as warnings
- [ ] Diff sanity checks (no file deletions, no binary files, max line count)

### 3.3 Fix application
- [x] `FixApplier` skeleton — `git apply --check` before apply
- [ ] `FixApplier.create_pr(...)` — commit, push, open GitHub PR
- [ ] PR body template: incident ID, root cause, evidence, Semgrep results

### 3.4 Guardrails
- [x] `ApprovalRequired` — write tools gate on `approved_tools` context key
- [x] `RBACGuard` — role check from `actor_roles` context key
- [x] `AuditLogger` — structlog with session ID, actor, tool, approved_by, timestamp
- [x] `sanitize_log_content` — regex patterns for AWS keys, Anthropic keys, Slack tokens, GH tokens

### 3.5 CLI integration
- [x] `tinker fix <id>` — displays diff with syntax highlighting
- [ ] `tinker fix <id> --approve` — confirmation prompt → apply → print PR URL

**Deliverable:** `tinker fix INC-001 --approve` opens a PR. Semgrep blocks a deliberately insecure fix.

---

## Phase 4: Server + Remote Clients ✅

**Goal:** Tinker runs as a server. CLI and Claude Code are remote clients.

### 4.1 FastAPI server
- [x] `POST /api/v1/analyze` — SSE streaming, session created per request
- [x] `POST /api/v1/logs` — raw log query endpoint
- [x] `POST /api/v1/metrics` — metrics endpoint
- [x] `POST /api/v1/anomalies` — anomaly detection endpoint
- [ ] `POST /api/v1/fix` — return pending fix for a session
- [ ] `POST /api/v1/approve` — apply fix, requires `oncall` role
- [ ] `GET /api/v1/sessions/{id}` — session state
- [x] `GET /health` — liveness probe

### 4.2 Authentication
- [x] API key validation (SHA-256 hash comparison, constant-time)
- [ ] JWT validation via JWKS URL (SSO path)
- [x] Slack request signature verification (`X-Slack-Signature`)
- [x] Auth context → `actor` and `actor_roles` propagated to guardrails

### 4.3 MCP over SSE
- [x] `GET /mcp/sse` + `POST /mcp/messages` — MCP protocol over HTTP
- [x] All tools from the active backend exposed via single endpoint
- [ ] `apply_fix` API-level approval gate
- [ ] End-to-end test with Claude Code remote MCP connection

### 4.4 Session store
- [x] In-memory `SessionStore` with TTL eviction
- [ ] Redis-backed store (for multi-replica deployments)

### 4.5 Local/server dual-mode CLI ✅
- [x] `tinker.toml` — `[tinker] mode`, `[local]`, `[server]` sections
- [x] `src/tinker/client/` — `LocalClient` (wraps backend + orchestrator) and `RemoteClient` (HTTP to server)
- [x] `get_client()` factory — reads `tinker.toml`, respects `TINKER_MODE` env, auto-detects
- [x] `--mode` global CLI flag — overrides `tinker.toml` per command
- [x] `tinker init` — three-path wizard: local / server / deploy

**Deliverable:** `tinker analyze <service>` works in both local mode (direct to cloud) and server mode (via API).

---

## Phase 4.5: Live Log Streaming ✅

- [x] `tail_logs()` — `AsyncGenerator[LogEntry, None]` on `ObservabilityBackend` base class
- [x] Poll-based default implementation (deduplication by `(timestamp, message)`)
- [x] Grafana override — native Loki websocket, fallback to poll
- [x] `tinker tail <service>` CLI command — streams to terminal with Rich, Ctrl-C to stop
- [x] `-q` / `--query` flag — same unified query syntax as `tinker logs`
- [x] `--poll` flag — configurable poll interval

**Deliverable:** `tinker tail payments-api -q 'level:ERROR'` streams live filtered logs.

---

## Phase 5: Slack Bot 🔄

**Goal:** Full Slack workflow from proactive alert through `/tinker-approve`.

### 5.1 Bot setup
- [x] Slack Bolt skeleton mounted into FastAPI at `/slack`
- [ ] Socket Mode for development
- [x] Webhook mode for production

### 5.2 Slash commands
- [x] `/tinker-analyze <service>` skeleton
- [x] `/tinker-fix <incident-id>` skeleton
- [x] `/tinker-approve <incident-id>` skeleton (role check)
- [x] `/tinker-status`, `/tinker-help`
- [ ] Full streaming agent output into thread

### 5.3 Interactive components
- [ ] Block Kit incident report formatter
- [ ] "Get Fix" / "Approve" / "Dismiss" action buttons

### 5.4 RBAC
- [ ] Slack user group → role mapping

**Deliverable:** Full Slack flow: alert → `/tinker-analyze` → agent streams into thread → `/tinker-approve` opens PR.

---

## Phase 6: Monitoring Loop [ ]

**Goal:** Tinker proactively detects anomalies without being asked.

- [ ] `MonitoringLoop` — APScheduler polls all configured services on interval
- [ ] Per-service cooldown — no re-alert within 30 min for same metric
- [ ] Severity routing — critical → `#incidents`, low → `#tinker-noise`
- [ ] Slack alert handler — `post_anomaly_alert` with action buttons
- [ ] `tinker monitor` CLI command — foreground loop with Rich live display
- [ ] Configurable alert rules per service (error rate threshold, latency p99, etc.)
- [ ] Auto-triage — fast Claude severity classification before alerting

**Deliverable:** Loop detects a simulated error spike and posts to Slack within the configured interval. Cooldown prevents duplicate alerts.

---

## Phase 7: Hardening & Production Readiness [ ]

- [ ] OpenTelemetry instrumentation on Tinker itself (traces + metrics)
- [ ] Rate limiting on API endpoints (per-client, per-minute)
- [ ] Redis-backed session store for multi-replica deployments
- [ ] Secrets rotation — re-reads `TINKER_API_KEYS` on SIGHUP
- [ ] End-to-end integration tests: LocalStack (AWS) + docker-compose Grafana stack
- [ ] Load test: 10 concurrent `/analyze` requests, measure time to first token
- [ ] Runbook: deploying, rotating keys, adding a service, incident playbook

---

## Local development environment ✅

A self-contained stack for developing against real logs without a cloud account.

- [x] `local-dev/docker-compose.yml` — payments-api + Loki + Prometheus + Grafana (Tinker server not included — run from IDE)
- [x] `local-dev/dummy_server.py` — FastAPI dummy service, emits structured logs at all levels, Prometheus metrics
- [x] `local-dev/generate_traffic.sh` — steady / incident / burst / quiet traffic modes
- [x] `local-dev/run.sh` — start / stop with health checks
- [x] `local-dev/prometheus.yml` — scrapes payments-api

---

## Tech Stack

| Layer | Library | Version |
|---|---|---|
| Python | — | 3.11+ |
| Server | fastapi, uvicorn | ^0.111, ^0.30 |
| CLI | typer, rich | ^0.12, ^13 |
| Slack | slack-bolt | ^1.18 |
| LLM | anthropic, litellm | ^0.25 |
| MCP | mcp | ^1.0 |
| Auth | pyjwt[crypto] | ^2.8 |
| AWS | boto3 | ^1.34 |
| GCP | google-cloud-monitoring, google-cloud-logging | latest |
| Azure | azure-identity, azure-monitor-query | ^1.17, ^1.3 |
| Grafana / Prometheus | httpx, websockets | ^0.27 |
| Datadog | httpx | ^0.27 |
| Elastic | elasticsearch | ^8 |
| Config | pydantic-settings | ^2 |
| Logging | structlog | ^24 |
| Scheduling | apscheduler | ^3.10 |
| Code tools | gitpython, pygithub | ^3.1, ^2.3 |
| Testing | pytest, pytest-asyncio, moto, respx | latest |
| Packaging | uv | latest |

---

## Definition of Done (per phase)

1. All checklist items complete
2. `uv run pytest` passes with no skipped tests
3. `tinker` CLI smoke-test for the phase's features passes
4. `trufflehog filesystem .` reports no credential leaks
5. Structured audit log entries written for every agent write action

---

## Non-goals for v1

- Auto-merging PRs — human must merge
- `tinker deploy` CLI command — deployment is the platform team's job via Helm/Terraform
- Multi-tenant / SaaS mode
- Custom model fine-tuning
- Incident ticketing integration (Jira, PagerDuty) — Phase 8+
- Kubernetes operator
