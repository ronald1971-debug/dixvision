"""
security.wallet_policy — live-signing daily USD cap.

Phases (days since system birth):
    0 – 60   SUPERVISED    live ok per-wallet AFTER governance approval;
                           HARD daily cap = $100 USD / wallet / rolling 24h
                           AND $100 USD / system / rolling 24h
   60 +      OPERATOR_SET  cap configurable via cockpit (governance event);
                           defaults to $100 until raised

Lookups are bounded and read from sqlite. Budgets are deterministic:
all USD notionals come from the caller (estimated via the oracle layer).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from state.ledger.writer import get_writer
from system.time_source import utc_now

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "wallet_policy.sqlite"
_BIRTH_KEY = "wallet_policy_birth_utc"
_SYSTEM_DAILY_CAP_USD = 100.0
_PER_WALLET_DAILY_CAP_USD = 100.0
_SUPERVISED_DAYS = 60  # days 0-60 → SUPERVISED; 60+ → OPERATOR_SET

_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_key TEXT NOT NULL,             -- chain|address
    ts_utc TEXT NOT NULL,
    usd REAL NOT NULL,
    ref TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS spend_wallet ON policy_spend(wallet_key, ts_utc);
CREATE INDEX IF NOT EXISTS spend_ts ON policy_spend(ts_utc);
CREATE TABLE IF NOT EXISTS policy_caps (
    wallet_key TEXT PRIMARY KEY,
    daily_cap_usd REAL NOT NULL,
    updated_utc TEXT NOT NULL,
    approved_by TEXT NOT NULL DEFAULT ''
);
"""


class Phase(StrEnum):
    SUPERVISED = "SUPERVISED"
    OPERATOR_SET = "OPERATOR_SET"


@dataclass
class PolicySnapshot:
    phase: Phase
    birth_utc: str
    day_index: int
    supervised_days_remaining: int
    system_cap_usd: float
    per_wallet_cap_usd: float
    spent_system_24h_usd: float
    live_signing_allowed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "birth_utc": self.birth_utc,
            "day_index": self.day_index,
            "supervised_days_remaining": self.supervised_days_remaining,
            "system_cap_usd": self.system_cap_usd,
            "per_wallet_cap_usd": self.per_wallet_cap_usd,
            "spent_system_24h_usd": round(self.spent_system_24h_usd, 2),
            "live_signing_allowed": self.live_signing_allowed,
            "remaining_system_24h_usd": round(
                max(0.0, self.system_cap_usd - self.spent_system_24h_usd), 2
            ),
            "warmup_days_remaining": 0,
        }


_lock = threading.RLock()

_conn_cached: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    """Return the cached connection, opening it on first use.

    Callers MUST already hold ``_lock``.
    """
    global _conn_cached
    if _conn_cached is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        c.executescript(_SCHEMA)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL;")
        _conn_cached = c
    return _conn_cached


def _wkey(chain: str, address: str) -> str:
    return f"{chain}|{address}"


def _get_birth(c: sqlite3.Connection) -> datetime:
    row = c.execute("SELECT v FROM policy_meta WHERE k = ?", (_BIRTH_KEY,)).fetchone()
    if row and row["v"]:
        birth = datetime.fromisoformat(row["v"])
        if birth.tzinfo is None:
            birth = birth.replace(tzinfo=UTC)
        return birth
    b = utc_now()
    if b.tzinfo is None:
        b = b.replace(tzinfo=UTC)
    c.execute("INSERT OR REPLACE INTO policy_meta(k, v) VALUES (?, ?)", (_BIRTH_KEY, b.isoformat()))
    c.commit()
    return b


def _phase_for(birth: datetime, now: datetime) -> tuple[Phase, int]:
    day = max(0, (now - birth).days)
    if day < _SUPERVISED_DAYS:
        return Phase.SUPERVISED, day
    return Phase.OPERATOR_SET, day


def _now_utc() -> datetime:
    n = utc_now()
    return n.replace(tzinfo=UTC) if n.tzinfo is None else n


def _spent_24h(c: sqlite3.Connection, wallet_key: str | None = None) -> float:
    since = (_now_utc() - timedelta(hours=24)).isoformat()
    if wallet_key:
        row = c.execute(
            "SELECT COALESCE(SUM(usd), 0.0) AS s FROM policy_spend "
            "WHERE wallet_key = ? AND ts_utc >= ?",
            (wallet_key, since),
        ).fetchone()
    else:
        row = c.execute(
            "SELECT COALESCE(SUM(usd), 0.0) AS s FROM policy_spend WHERE ts_utc >= ?", (since,)
        ).fetchone()
    return float(row["s"] if row else 0.0)


def _effective_cap(c: sqlite3.Connection, wallet_key: str) -> float:
    row = c.execute(
        "SELECT daily_cap_usd FROM policy_caps WHERE wallet_key = ?", (wallet_key,)
    ).fetchone()
    if row:
        return float(row["daily_cap_usd"])
    return _PER_WALLET_DAILY_CAP_USD


def snapshot() -> PolicySnapshot:
    with _lock:
        c = _connect()
        birth = _get_birth(c)
        now = _now_utc()
        phase, day = _phase_for(birth, now)
        sup_rem = max(0, _SUPERVISED_DAYS - day) if phase is Phase.SUPERVISED else 0
        spent = _spent_24h(c)
        return PolicySnapshot(
            phase=phase,
            birth_utc=birth.isoformat(),
            day_index=day,
            supervised_days_remaining=sup_rem,
            system_cap_usd=_SYSTEM_DAILY_CAP_USD,
            per_wallet_cap_usd=_PER_WALLET_DAILY_CAP_USD,
            spent_system_24h_usd=spent,
            live_signing_allowed=(spent < _SYSTEM_DAILY_CAP_USD),
        )


def _check_locked(
    c: sqlite3.Connection, chain: str, address: str, usd_notional: float
) -> tuple[bool, str, str, float]:
    """Core gate logic. Caller MUST already hold ``_lock``.

    Returns ``(ok, reason, wallet_key, wallet_cap)``.
    """
    if usd_notional < 0:
        return False, "negative_notional", "", 0.0
    wk = _wkey(chain, address)
    cap_wallet = _effective_cap(c, wk)
    spent_wallet = _spent_24h(c, wk)
    if spent_wallet + usd_notional > cap_wallet:
        return (False, f"wallet_cap_exhausted:{spent_wallet:.2f}/{cap_wallet:.2f}", wk, cap_wallet)
    spent_sys = _spent_24h(c)
    if spent_sys + usd_notional > _SYSTEM_DAILY_CAP_USD:
        return (
            False,
            f"system_cap_exhausted:{spent_sys:.2f}/{_SYSTEM_DAILY_CAP_USD:.2f}",
            wk,
            cap_wallet,
        )
    return True, "ok", wk, cap_wallet


def can_sign(chain: str, address: str, *, usd_notional: float) -> tuple[bool, str]:
    """Read-only gate for callers that only want to preview intent."""
    with _lock:
        c = _connect()
        ok, reason, _, _ = _check_locked(c, chain, address, usd_notional)
        return ok, reason


def check_and_consume(
    chain: str, address: str, *, usd_notional: float, ref: str = ""
) -> tuple[bool, str]:
    """Atomic check + record in a single lock-held transaction."""
    with _lock:
        c = _connect()
        ok, reason, wk, cap_wallet = _check_locked(c, chain, address, usd_notional)
        if not ok:
            return ok, reason
        c.execute(
            "INSERT INTO policy_spend(wallet_key, ts_utc, usd, ref) VALUES (?, ?, ?, ?)",
            (wk, _now_utc().isoformat(), float(usd_notional), ref),
        )
        c.commit()
        spent_wallet = _spent_24h(c, wk)
        spent_sys = _spent_24h(c)
    if spent_wallet >= cap_wallet:
        get_writer().write(
            "GOVERNANCE",
            "DAILY_CAP_TRIPPED",
            "GOVERNANCE",
            {
                "scope": "wallet",
                "wallet_key": wk,
                "spent_usd": round(spent_wallet, 2),
                "cap_usd": cap_wallet,
            },
        )
    if spent_sys >= _SYSTEM_DAILY_CAP_USD:
        get_writer().write(
            "GOVERNANCE",
            "DAILY_CAP_TRIPPED",
            "GOVERNANCE",
            {
                "scope": "system",
                "spent_usd": round(spent_sys, 2),
                "cap_usd": _SYSTEM_DAILY_CAP_USD,
            },
        )
    return True, "ok"


def consume(chain: str, address: str, *, usd_notional: float, ref: str = "") -> None:
    """Legacy shim — prefer :func:`check_and_consume` on new code."""
    if usd_notional <= 0:
        return
    check_and_consume(chain, address, usd_notional=usd_notional, ref=ref)


def set_wallet_cap(chain: str, address: str, *, daily_cap_usd: float, approved_by: str) -> None:
    """Phase OPERATOR_SET only. Raises in SUPERVISED."""
    if daily_cap_usd < 0:
        raise ValueError(f"daily_cap_usd must be non-negative, got {daily_cap_usd}")
    s = snapshot()
    if s.phase is not Phase.OPERATOR_SET:
        raise PermissionError(f"cap change blocked in phase {s.phase.value}")
    with _lock:
        c = _connect()
        c.execute(
            "INSERT OR REPLACE INTO policy_caps"
            "(wallet_key, daily_cap_usd, updated_utc, approved_by) "
            "VALUES (?, ?, ?, ?)",
            (_wkey(chain, address), float(daily_cap_usd), _now_utc().isoformat(), approved_by),
        )
        c.commit()
    get_writer().write(
        "GOVERNANCE",
        "DAILY_CAP_CHANGED",
        "GOVERNANCE",
        {
            "wallet_key": _wkey(chain, address),
            "new_cap_usd": float(daily_cap_usd),
            "approved_by": approved_by,
        },
    )


def wallet_status(chain: str, address: str) -> dict[str, object]:
    wk = _wkey(chain, address)
    with _lock:
        c = _connect()
        cap = _effective_cap(c, wk)
        spent = _spent_24h(c, wk)
    return {
        "wallet_key": wk,
        "cap_usd": cap,
        "spent_24h_usd": round(spent, 2),
        "remaining_24h_usd": round(max(0.0, cap - spent), 2),
    }


__all__ = [
    "Phase",
    "PolicySnapshot",
    "snapshot",
    "can_sign",
    "check_and_consume",
    "consume",
    "set_wallet_cap",
    "wallet_status",
]
