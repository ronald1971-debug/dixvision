"""execution_engine.adapters.external — Read-only external platform adapters (BUILD-DIRECTIVE §13).

These adapters fetch signals and backtest results from external trading
platforms. They are DATA SOURCES ONLY — B-FETCH lint rule enforces that
they expose only ``fetch_*`` methods. No ``submit``, ``execute``, ``place``,
``trade``, or ``swap`` methods are permitted.

External platforms serve as data inputs to the intelligence pipeline.
They never execute orders or modify positions.
"""
