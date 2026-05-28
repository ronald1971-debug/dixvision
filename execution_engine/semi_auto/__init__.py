"""execution_engine.semi_auto — Semi-automatic execution subsystem (BUILD-DIRECTIVE §8).

When a domain is in SEMI_AUTO trading mode:
- Entries below threshold go to approval queue
- Exits auto-fire (Indira protects on the way out)
- Risk reductions auto-fire
"""
