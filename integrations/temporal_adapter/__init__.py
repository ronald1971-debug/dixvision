"""Temporal Durable Workflows Adapter.

Replaces fragile async coordination with Temporal — a production-grade
durable execution system for workflows that survive failures.

Maps DIXVISION workflow concepts:
- Strategy execution lifecycle → Temporal workflow
- Order management → Temporal activity
- Learning cycles → Temporal scheduled workflow
- Recovery/reconciliation → Temporal retry policies

Reference: github.com/temporalio/temporal
"""
