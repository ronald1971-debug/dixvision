"""Open Policy Agent (OPA) Governance Adapter.

Replaces custom governance condition checks with OPA — a production-grade
policy engine that evaluates Rego policies at runtime.

Maps DIXVISION governance concepts:
- Execution gates → OPA allow/deny decisions
- Mode transitions → OPA policy evaluation
- Risk constraints → OPA data-driven rules
- Operator authority → OPA RBAC policies
- Kill switch → OPA explicit deny

Reference: github.com/open-policy-agent/opa
"""
