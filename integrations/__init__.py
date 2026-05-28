"""OSS Integration Layer.

Provides battle-tested open-source system adapters that back
DIXVISION's custom governance and orchestration philosophy.

Architecture:
- DIXVISION contracts remain the interface
- OSS systems provide the implementation
- Adapters bridge the two without leaking abstractions

Integrations:
- ccxt_adapter: Exchange connectivity (CCXT)
- qdrant_adapter: Vector memory (Qdrant)
- langgraph_adapter: Agent orchestration (LangGraph)
- opa_adapter: Policy enforcement (OPA)
"""
