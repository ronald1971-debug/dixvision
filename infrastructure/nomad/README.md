# I-39 — Nomad Container Orchestration for DIX VISION

**ADAPTED FROM:** https://github.com/hashicorp/nomad  
**License:** BSL 1.1 (review before production use)  
**Classification:** PATTERN_ONLY (infrastructure spec)

## Overview

Nomad provides lightweight container orchestration for DIX services —
simpler than Kubernetes, ideal for solo/small team operation.

## Services

| Service | Port | Mode | Resources |
|---------|------|------|-----------|
| dix-runtime | 8100 | RUNTIME | 2 CPU, 4GB RAM |
| dix-learning | 8200 | OFFLINE | 4 CPU, 8GB RAM |
| dix-governance | 8300 | GOVERNANCE | 1 CPU, 2GB RAM |
| dix-ui | 8080/8081 | UI | 0.5 CPU, 1GB RAM |

## Deployment

### Prerequisites

1. Install Nomad: `curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -`
2. Install Consul (service discovery): same HashiCorp repo
3. Docker runtime on all nodes

### Deploy

```bash
# Start Nomad agent (dev mode for single node)
nomad agent -dev

# Plan the job (dry run)
nomad job plan infrastructure/nomad/dixvision.nomad

# Run the job
nomad job run infrastructure/nomad/dixvision.nomad

# Check status
nomad job status dixvision
```

### Rolling Deploy

The job spec uses rolling deploy with:
- `max_parallel = 1` — one service at a time
- `auto_revert = true` — roll back on health check failure
- Governance requires checkpoint before deploy (longer `min_healthy_time`)

### Service Discovery

Services register with Consul for DNS-based discovery:
- `dix-runtime.service.consul:8100`
- `dix-governance.service.consul:8300`

### Health Checks

All services expose `/health` endpoint checked by Nomad:
- Runtime: every 10s (fast detection of hot-path issues)
- Learning: every 30s (long-running tasks tolerate brief hiccups)
- Governance: every 10s (kill switch must be responsive)
- UI: every 10s (operator needs immediate feedback)

## Why Nomad Over Kubernetes

| Factor | Nomad | Kubernetes |
|--------|-------|------------|
| Complexity | Single binary | Many components |
| Learning curve | Hours | Weeks |
| Resource overhead | ~50MB RAM | ~500MB+ RAM |
| Solo operator | Ideal | Overkill |
| Service mesh | Optional (Consul) | Required (often) |
| Job types | service, batch, system | Deployment, Job, CronJob, etc |

## Production Considerations

- [ ] Replace `latest` image tags with pinned SHA digests
- [ ] Add TLS between services (Consul Connect)
- [ ] Set up Vault integration for credentials
- [ ] Configure backup for `/data/dix/` volumes
- [ ] Add alerting on health check failures
