"""Kafka/Redpanda Event Streaming Adapter.

Replaces custom event bus and ad-hoc websocket routing with
Kafka/Redpanda — production-grade distributed event streaming.

Maps DIXVISION event concepts:
- Market data events → Kafka topic (dix.market.{symbol})
- Trading signals → Kafka topic (dix.signals)
- Governance decisions → Kafka topic (dix.governance)
- Execution events → Kafka topic (dix.execution)
- Telemetry → Kafka topic (dix.telemetry)

Reference:
- github.com/apache/kafka
- github.com/redpanda-data/redpanda
"""
