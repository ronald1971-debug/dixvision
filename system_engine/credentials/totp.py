# ADAPTED FROM: pyauth/pyotp
# (pyotp/totp.py — TOTP class, now(), verify(), provisioning_uri();
#  pyotp/utils.py — random_base32() for secret generation;
#  pyotp/otp.py — OTP base class, generate_otp())
"""C-75 — TOTP escalation codes for autonomy level changes.

This module adapts ``pyotp`` for time-based one-time passwords required
when escalating autonomy levels (A3 → A4 → A5).

What survives from upstream (pyauth/pyotp):
    * **TOTP** — ``totp.py``: ``TOTP(secret).now()`` generates current
      6-digit code, ``TOTP(secret).verify(code)`` validates.
    * **provisioning_uri()** — generates otpauth:// URI for QR codes.
    * **random_base32()** — ``utils.py``: generates a secure random
      TOTP secret for initial setup.

What we replaced:
    * Real ``pyotp`` import is lazy (Protocol seam).
    * Pure-Python HMAC-based TOTP for testing (RFC 6238).
    * TOTP secret stored via vault_backend (C-70) — never in registry.

RUNTIME tier: TOTP verification on escalation requests.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass

from system.time_source import wall_ns


@dataclass(frozen=True, slots=True)
class TOTPConfig:
    """Configuration for a TOTP instance."""

    secret: str  # base32-encoded secret
    issuer: str = "DIX"
    account: str = "operator"
    digits: int = 6
    interval: int = 30


class TOTPManager:
    """TOTP manager for autonomy escalation gates.

    Generates and verifies time-based one-time passwords required for
    autonomy level changes (A3 → A4 → A5).

    Usage::

        mgr = TOTPManager()
        config = mgr.generate_secret()
        code = mgr.now(config.secret)
        assert mgr.verify(config.secret, code)
    """

    def generate_secret(self, *, issuer: str = "DIX", account: str = "operator") -> TOTPConfig:
        """Generate a new TOTP secret (mirrors pyotp.random_base32())."""
        try:
            import pyotp

            secret = pyotp.random_base32()
        except ImportError:
            import base64
            import os

            secret = base64.b32encode(os.urandom(20)).decode("ascii")

        return TOTPConfig(secret=secret, issuer=issuer, account=account)

    def now(self, secret: str) -> str:
        """Generate current TOTP code (mirrors TOTP.now())."""
        try:
            import pyotp

            return pyotp.TOTP(secret).now()
        except ImportError:
            return self._generate_totp(secret, wall_ns() // 1_000_000_000)

    def verify(self, secret: str, code: str, *, window: int = 1) -> bool:
        """Verify a TOTP code (mirrors TOTP.verify()).

        Args:
            secret: Base32-encoded TOTP secret.
            code: 6-digit code to verify.
            window: Number of time steps to check (+/- window).
        """
        try:
            import pyotp

            return pyotp.TOTP(secret).verify(code, valid_window=window)
        except ImportError:
            return self._verify_totp(secret, code, window)

    def provisioning_uri(self, config: TOTPConfig) -> str:
        """Generate otpauth:// URI for QR code scanning."""
        try:
            import pyotp

            totp = pyotp.TOTP(config.secret)
            return totp.provisioning_uri(
                name=config.account,
                issuer_name=config.issuer,
            )
        except ImportError:
            return (
                f"otpauth://totp/{config.issuer}:{config.account}"
                f"?secret={config.secret}&issuer={config.issuer}"
                f"&digits={config.digits}&period={config.interval}"
            )

    # ---- pure-Python TOTP (RFC 6238) ------------------------------------

    def _generate_totp(self, secret: str, timestamp: int, interval: int = 30) -> str:
        """Pure-Python TOTP generation (RFC 6238)."""
        import base64

        key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
        counter = timestamp // interval
        counter_bytes = struct.pack(">Q", counter)
        mac = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        offset = mac[-1] & 0x0F
        truncated = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(truncated % 10**6).zfill(6)

    def _verify_totp(self, secret: str, code: str, window: int) -> bool:
        """Verify TOTP with window tolerance."""
        current_time = wall_ns() // 1_000_000_000
        for offset in range(-window, window + 1):
            check_time = current_time + (offset * 30)
            if self._generate_totp(secret, check_time) == code:
                return True
        return False


__all__ = ["TOTPConfig", "TOTPManager"]
