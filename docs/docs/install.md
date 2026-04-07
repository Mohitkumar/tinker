---
sidebar_position: 2
title: Installation
---

# Installation

## Requirements

- Python **3.12** or higher
- Access to a cloud observability backend (CloudWatch, GCP, Azure, Grafana, Datadog, or Elastic)
- An Anthropic, OpenAI, OpenRouter, or Groq API key for LLM features

---

## Install options

### pip (recommended for production)

```bash
pip install tinker-agent
```

### uv (recommended for development)

```bash
uv tool install tinker-agent
```

`uv tool install` makes `tinker` available globally in your PATH without polluting any project virtualenv.

### Editable install from source

```bash
git clone https://github.com/your-org/tinker
cd tinker
uv sync                        # creates .venv and installs all deps
uv tool install --editable .   # installs tinker globally as editable
```

Changes to `src/` take effect immediately — no reinstall needed.

### Docker

```bash
docker pull ghcr.io/your-org/tinker:latest
docker run -p 8000:8000 \
  --env-file ~/.tinker/.env \
  -v ~/.tinker:/root/.tinker \
  ghcr.io/your-org/tinker:latest
```

---

## Verify the install

```bash
tinker --version
tinker --help
```

---

## File locations

All per-user state lives in `~/.tinker/`:

| File | Written by | Purpose |
|---|---|---|
| `~/.tinker/config.toml` | `tinker init server` | Server structure — profiles, LLM, Slack, GitHub, auth |
| `~/.tinker/.env` | `tinker init server` | Secrets — API keys, tokens. **Never commit this file** |
| `~/.tinker/config` | `tinker init cli` | CLI connection — server URL + API token |
| `~/.tinker/tinker.db` | auto-created | SQLite — REPL sessions, watch state, alert rules |
| `~/.tinker/repl_history` | auto-created | `tinker investigate` command history |

---

## Environment variables

All config can be driven purely via environment variables (useful for containers):

| Variable | Description | Default |
|---|---|---|
| `TINKER_BACKEND` | Active backend | `cloudwatch` |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `OPENROUTER_API_KEY` | OpenRouter API key | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `GROQ_API_KEY` | Groq API key | — |
| `TINKER_API_KEYS` | JSON array of hashed API keys | `[]` |
| `TINKER_SERVER_URL` | Server URL (CLI override) | `http://localhost:8000` |
| `TINKER_API_TOKEN` | API token (CLI override) | — |
| `TINKER_SERVER_PORT` | Bind port | `8000` |
| `TINKER_SERVER_HOST` | Bind host | `0.0.0.0` |
| `TINKER_DB_PATH` | SQLite path | `~/.tinker/tinker.db` |

Environment variables override `config.toml` values. See the [Configuration Reference](/configuration) for the full list.

---

## Generating and hashing API keys

```bash
# Generate a raw key (share this with CLI users)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Hash it (store the hash in config.toml [auth])
python -c "
import hashlib, sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest())
" <raw-key>
```

`tinker init server` does this automatically.
