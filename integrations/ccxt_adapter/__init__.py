"""CCXT Exchange Adapter.

Wraps the CCXT unified API into DIXVISION execution contracts.
Replaces custom exchange adapters with battle-tested connectivity
to 100+ exchanges via a single interface.

Key design:
- All methods respect DIXVISION governance gates
- Kill switch integration at adapter level
- Rate limiting respects exchange-specific constraints
- Read-only mode enforced until operator enables execution
"""
