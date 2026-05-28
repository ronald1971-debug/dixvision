# C-78 — Flutter Mobile Operator Cockpit

**ADAPTED FROM:** https://github.com/flutter/flutter  
**License:** BSD-3-Clause  
**Classification:** PATTERN_ONLY (architecture brief — not Python adaptation)

## Overview

The Flutter mobile cockpit is a **separate Dart project** that communicates
with DIX exclusively via REST API and WebSocket. It NEVER imports Python
modules directly.

## Architecture

```
┌─────────────────────────────────────────┐
│         Flutter Mobile App              │
│                                          │
│  ┌──────────┐  ┌──────────────────┐    │
│  │ Riverpod │  │  REST API Client │    │
│  │  State   │──│  (api_client)    │    │
│  └──────────┘  └────────┬─────────┘    │
│                          │               │
│  ┌──────────────────────┐│               │
│  │  WebSocket Client    ││               │
│  │  (live feed)         ││               │
│  └──────────┬───────────┘│               │
└─────────────┼────────────┼───────────────┘
              │            │
              ▼            ▼
┌─────────────────────────────────────────┐
│         DIX ui/server.py                │
│  /api/operator/*   (REST)               │
│  /ws/live          (WebSocket)          │
└─────────────────────────────────────────┘
```

## Key Screens

| Screen               | API Endpoint                      | Description                           |
|---------------------|-----------------------------------|---------------------------------------|
| Positions           | `GET /api/operator/summary`       | Live portfolio positions              |
| Kill Switch         | `POST /api/operator/kill`         | Emergency halt (2-tap confirmation)   |
| Hazard Alerts       | `WS /ws/live` (hazard_event)      | Real-time hazard notifications        |
| Governance Approvals| `POST /api/operator/mode`         | Mode transition approvals             |
| PnL Chart           | `GET /api/operator/pnl`           | Performance over time                 |

## API Contract

All endpoints return JSON conforming to the Pydantic models in:
- `core/contracts/api/operator.py` — `OperatorSummaryResponse`, `OperatorActionResponse`

## Kill Switch

The kill switch requires **2-tap confirmation**:
1. First tap: shows confirmation dialog with current positions summary
2. Second tap: sends `POST /api/operator/kill` with HMAC-signed payload

## State Management

- **Riverpod** for reactive state (positions, mode, alerts)
- **WebSocket** for real-time push (hazard events, PnL updates)
- **REST polling** as fallback (30s interval)

## Security

- All API calls include `Authorization: Bearer <operator_token>`
- Kill switch payload signed with operator's HMAC key
- WebSocket authenticated via initial handshake token
- Certificate pinning for production builds
