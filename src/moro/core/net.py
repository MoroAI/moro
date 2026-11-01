"""Network binding guards for local-first services.

Stdlib-only on purpose: the CLI and the legacy stdlib dashboard server must be
able to enforce loopback-only binding even when FastAPI/uvicorn are missing.
"""

from __future__ import annotations

import ipaddress

_LOOPBACK_NAMES = {"localhost", "ip6-localhost"}


class NonLoopbackBindError(ValueError):
    """Raised when a bind address is not loopback and no override was given."""


def is_loopback_host(host: str) -> bool:
    """Return True only for loopback literals and well-known loopback names."""
    name = (host or "").strip().lower()
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    name = name.rstrip(".")
    if name in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def check_bind_host(host: str, *, allow_non_loopback: bool = False) -> str | None:
    """Validate a bind address for a local-first service.

    Returns a warning message when a non-loopback bind is explicitly allowed,
    None when the bind is loopback. Raises NonLoopbackBindError when a
    non-loopback bind is requested without the explicit override.
    """
    if is_loopback_host(host):
        return None
    if not allow_non_loopback:
        raise NonLoopbackBindError(
            f"Refusing to bind {host!r}: MoroAI services are loopback-only by default. "
            "Re-run with --allow-non-loopback to expose the service beyond this machine, "
            "and only behind authentication you trust."
        )
    return (
        f"Binding to non-loopback address {host!r}. The service will be reachable "
        "from the network; ensure the installation token stays secret."
    )
