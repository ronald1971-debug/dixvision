"""DIX v42 — hot-path profiler.

Profiles the critical execution path (signal → impact → slices)
using cProfile and prints the top-N slowest calls.

Usage:
    python scripts/profile_hot_path.py [--n 20] [--iterations 10000]
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))


def _hot_path(iterations: int) -> None:
    from execution_engine.strategic_execution.market_impact.model import ImpactModel
    from execution_engine.strategic_execution.optimal_execution import OptimalExecutor
    from execution_engine.strategic_execution.adversarial_executor import AdversarialExecutor

    impact_model = ImpactModel()
    executor = OptimalExecutor(n_slices=10)
    adversarial = AdversarialExecutor()

    ts_ns = 1_700_000_000_000_000_000
    for i in range(iterations):
        ts = ts_ns + i
        impact_model.estimate(symbol="BTC", ts_ns=ts, qty=100.0, adv=10_000.0)
        executor.plan_twap(symbol="BTC", ts_ns=ts, total_qty=1000.0,
                           adv=10_000.0, mid_price=50_000.0)
        adversarial.plan(symbol="BTC", ts_ns=ts, side="BUY",
                         urgency=0.5, spread_bps=5.0, crowding_score=0.3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile DIX hot path")
    parser.add_argument("--n", type=int, default=20, help="Top N functions to show")
    parser.add_argument("--iterations", type=int, default=10_000)
    args = parser.parse_args()

    profiler = cProfile.Profile()
    profiler.enable()
    _hot_path(args.iterations)
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats(pstats.SortKey.CUMULATIVE)
    stats.print_stats(args.n)
    print(stream.getvalue())


if __name__ == "__main__":
    main()
