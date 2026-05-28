"""Execution Intelligence — smart order routing and market impact awareness.

Not just fast execution. SMART execution:
- Liquidity model: where is the liquidity?
- Slippage predictor: what will this order cost?
- Order splitting: how to minimize market impact?
- Smart routing: which venue/path is optimal?

Makes execution "smart-fast" instead of just "fast".
"""

from execution_engine.intelligence.liquidity_model import LiquidityModel, LiquiditySnapshot
from execution_engine.intelligence.order_splitter import OrderSplitter, SplitPlan
from execution_engine.intelligence.slippage_predictor import SlippageEstimate, SlippagePredictor
from execution_engine.intelligence.smart_router import RouteDecision, SmartRouter

__all__ = [
    "LiquidityModel",
    "LiquiditySnapshot",
    "SlippagePredictor",
    "SlippageEstimate",
    "OrderSplitter",
    "SplitPlan",
    "SmartRouter",
    "RouteDecision",
]
