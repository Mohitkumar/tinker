---
sidebar_position: 4
title: Docker / Self-hosted
---

# Docker and Self-hosted Deployment

The fastest way to get Tinker running locally or on any Linux host.

---

## Docker Compose (full stack)

The included `docker-compose.yml` spins up Tinker plus a complete local Grafana observability stack (Loki + Prometheus + Grafana UI):

```bash
git clone https://github.com/your-org/tinker
cd tinker

# Copy and fill in your secrets
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY at minimum

docker compose -f deploy/docker-compose.yml up -d
```

Services started:

| Service | Port | Purpose |
|---|---|---|
| `tinker` | 8000 | Tinker server |
| `loki` | 3100 | Log aggregation |
| `prometheus` | 9090 | Metrics |
| `grafana` | 3000 | Visualization UI |

```bash
# Generate test traffic
cd local-dev && ./generate_traffic.sh incident

# Query via CLI
tinker init cli   # URL: http://localhost:8000
tinker anomaly payments-api --since 5m
tinker investigate payments-api
```

---

## Docker (standalone)

```bash
docker run -d \
  --name tinker \
  -p 8000:8000 \
  --env-file ~/.tinker/.env \
  -v ~/.tinker:/root/.tinker \
  ghcr.io/your-org/tinker:latest
```

### Required `.env` values

```bash title="~/.tinker/.env"
# LLM — at least one required
ANTHROPIC_API_KEY=sk-ant-...

# Backend — set to your observability stack
TINKER_BACKEND=grafana
GRAFANA_LOKI_URL=http://loki:3100
GRAFANA_PROMETHEUS_URL=http://prometheus:9090
GRAFANA_TEMPO_URL=http://tempo:3200

# Auth — hashed API key for CLI users
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
# Hash:     python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" <raw>
TINKER_API_KEYS='[{"hash":"<sha256>","subject":"alice","roles":["oncall"]}]'

# Optional
GITHUB_TOKEN=ghp_...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
```

---

## Building the image locally

```bash
git clone https://github.com/your-org/tinker
cd tinker
docker build -t tinker:local .
docker run -p 8000:8000 --env-file ~/.tinker/.env -v ~/.tinker:/root/.tinker tinker:local
```

---

## Kubernetes (generic)

```yaml title="k8s/tinker.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tinker
  namespace: observability
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tinker
  template:
    metadata:
      labels:
        app: tinker
    spec:
      containers:
        - name: tinker
          image: ghcr.io/your-org/tinker:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: tinker-secrets
          env:
            - name: TINKER_BACKEND
              value: grafana
            - name: GRAFANA_LOKI_URL
              value: http://loki.observability.svc.cluster.local:3100
            - name: GRAFANA_PROMETHEUS_URL
              value: http://prometheus.observability.svc.cluster.local:9090
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 1Gi
---
apiVersion: v1
kind: Service
metadata:
  name: tinker
  namespace: observability
spec:
  selector:
    app: tinker
  ports:
    - port: 80
      targetPort: 8000
```

```bash
# Create secrets from .env file
kubectl create secret generic tinker-secrets \
  --from-env-file ~/.tinker/.env \
  -n observability

kubectl apply -f k8s/tinker.yaml
```

---

## Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0","active_profile":"local","profiles":{"local":"grafana"}}
```

## API docs

Tinker's interactive API docs are available at:

```
http://localhost:8000/docs
```
