"""OpenBB Financial Data Adapter.

Replaces scattered financial data sources with OpenBB — the leading
open-source financial data aggregator and analytics platform.

Maps DIXVISION data needs:
- Macro data (GDP, CPI, rates, employment) → OpenBB Economy
- Equity data (prices, fundamentals, earnings) → OpenBB Equity
- Crypto data (prices, on-chain, sentiment) → OpenBB Crypto
- Forex data (rates, crosses) → OpenBB Currency
- News and sentiment → OpenBB News
- Technical indicators → OpenBB Technical

Reference: github.com/OpenBB-finance/OpenBB
"""
