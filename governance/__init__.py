"""governance -- patch pipeline + approvals + policy gates.

LEGACY: This package is the pre-convergence governance layer. The
canonical governance engine lives in ``governance_engine/``. New code
should import from ``governance_engine`` instead. This package is
retained for backward compatibility and will be removed in a future
major version.

Every code change routes through `governance.patch_pipeline` (sandbox ->
authority-lint -> unit tests -> dep-scan -> shadow -> canary -> human
approval -> live) before being promoted. See patch_pipeline.py for details.
"""
