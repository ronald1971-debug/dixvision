# ADAPTED FROM: hashicorp/nomad
# (nomad/jobspec/parse.go — HCL job spec format;
#  rolling deploy, service discovery, health checks)
#
# I-39 — Nomad job specification for DIX VISION services.
# Lightweight container orchestration (simpler than Kubernetes).
#
# Services:
#   - dix-runtime: Core execution engine + event loop
#   - dix-learning: ML training + feature engineering (OFFLINE)
#   - dix-governance: Governance engine + kill switch
#   - dix-ui: Operator dashboard + REST API
#
# LICENSE: Nomad uses BSL 1.1 — review before production use.

job "dixvision" {
  datacenters = ["dc1"]
  type        = "service"

  # ─── DIX Runtime ──────────────────────────────────────────────────────
  group "runtime" {
    count = 1

    network {
      port "runtime" { static = 8100 }
    }

    update {
      max_parallel     = 1
      min_healthy_time = "30s"
      healthy_deadline = "5m"
      auto_revert      = true
    }

    task "dix-runtime" {
      driver = "docker"

      config {
        image = "dixvision/runtime:latest"
        ports = ["runtime"]
        volumes = [
          "/data/dix/ledger:/app/state/ledger",
          "/data/dix/registry:/app/registry",
        ]
      }

      env {
        DIX_MODE       = "RUNTIME"
        DIX_LOG_LEVEL  = "INFO"
        DIX_LOG_FORMAT = "json"
      }

      resources {
        cpu    = 2000  # MHz
        memory = 4096  # MB
      }

      service {
        name = "dix-runtime"
        port = "runtime"

        check {
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "2s"
        }
      }
    }
  }

  # ─── DIX Learning Engine ──────────────────────────────────────────────
  group "learning" {
    count = 1

    network {
      port "learning" { static = 8200 }
    }

    update {
      max_parallel     = 1
      min_healthy_time = "60s"
      healthy_deadline = "10m"
      auto_revert      = true
    }

    task "dix-learning" {
      driver = "docker"

      config {
        image = "dixvision/learning:latest"
        ports = ["learning"]
        volumes = [
          "/data/dix/models:/app/models",
          "/data/dix/features:/app/features",
        ]
      }

      env {
        DIX_MODE      = "OFFLINE"
        DIX_LOG_LEVEL = "INFO"
      }

      resources {
        cpu    = 4000  # MHz (ML workloads)
        memory = 8192  # MB
      }

      service {
        name = "dix-learning"
        port = "learning"

        check {
          type     = "http"
          path     = "/health"
          interval = "30s"
          timeout  = "5s"
        }
      }
    }
  }

  # ─── DIX Governance Engine ────────────────────────────────────────────
  group "governance" {
    count = 1

    network {
      port "governance" { static = 8300 }
    }

    update {
      # Governance requires checkpoint before deploy
      max_parallel     = 1
      min_healthy_time = "60s"
      healthy_deadline = "10m"
      auto_revert      = true
    }

    task "dix-governance" {
      driver = "docker"

      config {
        image = "dixvision/governance:latest"
        ports = ["governance"]
        volumes = [
          "/data/dix/governance:/app/governance_state",
          "/data/dix/credentials:/app/credentials:ro",
        ]
      }

      env {
        DIX_MODE      = "GOVERNANCE"
        DIX_LOG_LEVEL = "INFO"
        DIX_KILL_SWITCH_ENABLED = "true"
      }

      resources {
        cpu    = 1000
        memory = 2048
      }

      service {
        name = "dix-governance"
        port = "governance"

        check {
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "2s"
        }
      }
    }
  }

  # ─── DIX UI (Operator Dashboard) ─────────────────────────────────────
  group "ui" {
    count = 1

    network {
      port "http" { static = 8080 }
      port "ws"   { static = 8081 }
    }

    update {
      max_parallel     = 1
      min_healthy_time = "15s"
      healthy_deadline = "3m"
      auto_revert      = true
    }

    task "dix-ui" {
      driver = "docker"

      config {
        image = "dixvision/ui:latest"
        ports = ["http", "ws"]
      }

      env {
        DIX_MODE              = "UI"
        DIX_RUNTIME_URL       = "http://dix-runtime.service.consul:8100"
        DIX_GOVERNANCE_URL    = "http://dix-governance.service.consul:8300"
        DIX_LOG_LEVEL         = "INFO"
      }

      resources {
        cpu    = 500
        memory = 1024
      }

      service {
        name = "dix-ui"
        port = "http"

        check {
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "2s"
        }
      }
    }
  }
}
