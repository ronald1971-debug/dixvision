"""OSS Integration Wiring Layer.

Connects OSS adapters (CCXT, Qdrant, Kafka, OPA) to existing
DIXVISION engines as optional backends. Each wire module:

1. Imports the OSS adapter
2. Imports the target engine interface
3. Creates a bridge class that translates between them
4. Respects existing governance/authority contracts

The wiring layer is the only place where OSS adapters touch core engines.
"""
