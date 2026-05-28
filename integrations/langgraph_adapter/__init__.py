"""LangGraph Orchestration Adapter.

Replaces custom planner/routing graphs with LangGraph — a production-grade
stateful agent orchestration framework.

Maps DIXVISION orchestration concepts:
- Intelligence Engine → LangGraph state machine
- Multi-agent consensus → LangGraph conditional routing
- Memory routing → LangGraph checkpointing
- Tool execution → LangGraph tool nodes
- Recovery loops → LangGraph error handling

Reference: github.com/langchain-ai/langgraph
"""
