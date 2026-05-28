"""Qdrant Vector Memory Adapter.

Replaces custom vector memory indexing with Qdrant — a production-grade
vector database optimized for semantic search and similarity.

Maps DIXVISION memory concepts:
- trader embeddings → Qdrant collection
- strategy embeddings → Qdrant collection
- narrative embeddings → Qdrant collection
- regime embeddings → Qdrant collection

Reference: github.com/qdrant/qdrant
"""
