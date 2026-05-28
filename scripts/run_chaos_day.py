"""DIX v42 — chaos day runner.

Runs the ChaosEngine over a simulated trading session to test
system resilience under injected faults.

Usage:
    python scripts/run_chaos_day.py [--seed 42] [--ticks 1000]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description="DIX chaos day simulation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=1_000)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    from execution.chaos_engine import ChaosEngine, FaultSpec

    specs = (
        FaultSpec(kind="LATENCY_SPIKE", probability=0.05, magnitude=10.0),
        FaultSpec(kind="PRICE_GAP", probability=0.02, magnitude=5.0),
        FaultSpec(kind="FILL_REJECTION", probability=0.03, magnitude=1.0),
        FaultSpec(kind="DATA_STALE", probability=0.01, magnitude=1.0),
    )

    engine = ChaosEngine(seed=args.seed, specs=specs)

    fault_counts: dict[str, int] = {}
    for tick in range(args.ticks):
        for spec in specs:
            result = engine.inject(spec.kind)
            if result.activated:
                fault_counts[spec.kind] = fault_counts.get(spec.kind, 0) + 1
                if args.verbose:
                    print(f"  tick={tick:>6} fault={spec.kind} mag={result.magnitude:.2f}")

    print(f"\nChaos day complete — seed={args.seed} ticks={args.ticks}")
    print("Fault injection summary:")
    for kind, count in sorted(fault_counts.items()):
        rate = count / args.ticks * 100
        print(f"  {kind:<25} {count:>5} faults  ({rate:.1f}%)")
    if not fault_counts:
        print("  (no faults injected)")


if __name__ == "__main__":
    main()
