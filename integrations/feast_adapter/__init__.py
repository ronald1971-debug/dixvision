"""Feast Feature Store Adapter.

Replaces custom feature pipelines with Feast — a production-grade
feature store that ensures online/offline consistency.

Maps DIXVISION feature concepts:
- Trading features → Feast feature views
- Online serving → Feast online store
- Offline training → Feast offline store
- Point-in-time joins → Feast historical retrieval

Reference: github.com/feast-dev/feast
"""
