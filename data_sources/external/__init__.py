"""data_sources.external — Read-only external data source adapters (BUILD-DIRECTIVE §14).

These adapters provide market data, news, social sentiment, and economic
data. They are feeder streams only — they provide data to the intelligence
pipeline but never directly influence execution decisions.

B-FETCH lint rule applies: only fetch_* public methods permitted.
"""
