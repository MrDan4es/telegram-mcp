"""Proxy configuration for ``TelegramClient`` from ``TELEGRAM_PROXY_*`` env vars.

Kept free of server imports so standalone scripts (the session string
generator) can route their connection through the same proxy as the server.
"""

import os
from typing import Any, Optional

_PROXY_TYPES_SOCKS_HTTP = {"socks5", "socks4", "http"}
_PROXY_TYPES_ALL = _PROXY_TYPES_SOCKS_HTTP | {"mtproxy"}


class ProxyConfigError(ValueError):
    """Malformed ``TELEGRAM_PROXY_*`` configuration."""


def get_proxy_env(name: str, label: str) -> Optional[str]:
    """Resolve a TELEGRAM_PROXY_* env var with optional ``_<LABEL>`` suffix.

    Per-account values override the unsuffixed defaults so a global proxy can
    coexist with per-label overrides.
    """
    suffixed = os.getenv(f"TELEGRAM_PROXY_{name}_{label.upper()}")
    if suffixed:
        return suffixed
    return os.getenv(f"TELEGRAM_PROXY_{name}") or None


def parse_bool_env(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_proxy_for_label(label: str) -> tuple[Optional[Any], Optional[Any]]:
    """Return ``(proxy, connection)`` kwargs for ``TelegramClient`` for a label.

    Reads ``TELEGRAM_PROXY_*`` env vars (with optional ``_<LABEL>`` suffix).
    Returns ``(None, None)`` when no proxy is configured. Raises
    :class:`ProxyConfigError` for malformed configuration so callers fail
    fast instead of silently bypassing the proxy.
    """
    proxy_type = get_proxy_env("TYPE", label)
    if not proxy_type:
        return None, None

    proxy_type = proxy_type.strip().lower()
    if proxy_type not in _PROXY_TYPES_ALL:
        raise ProxyConfigError(
            f"Invalid TELEGRAM_PROXY_TYPE '{proxy_type}'. "
            f"Expected one of: {', '.join(sorted(_PROXY_TYPES_ALL))}."
        )

    host = get_proxy_env("HOST", label)
    port_raw = get_proxy_env("PORT", label)
    if not host or not port_raw:
        raise ProxyConfigError(
            "TELEGRAM_PROXY_HOST and TELEGRAM_PROXY_PORT are required when "
            "TELEGRAM_PROXY_TYPE is set."
        )
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ProxyConfigError(
            f"TELEGRAM_PROXY_PORT must be an integer, got '{port_raw}'."
        ) from exc

    if proxy_type == "mtproxy":
        secret = get_proxy_env("SECRET", label)
        if not secret:
            raise ProxyConfigError("TELEGRAM_PROXY_SECRET is required for mtproxy.")
        try:
            from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
        except ImportError as exc:  # pragma: no cover - defensive guard
            raise ProxyConfigError(
                "Telethon MTProxy connection class is unavailable; upgrade telethon."
            ) from exc
        return (host, port, secret), ConnectionTcpMTProxyRandomizedIntermediate

    # SOCKS4/SOCKS5/HTTP via python-socks (Telethon's optional dependency).
    try:
        import python_socks  # noqa: F401
    except ImportError as exc:
        raise ProxyConfigError(
            f"Proxy type '{proxy_type}' requires the 'python-socks' package. "
            "Install it with `pip install python-socks` or `uv sync --extra proxy`."
        ) from exc

    proxy: dict[str, Any] = {
        "proxy_type": proxy_type,
        "addr": host,
        "port": port,
        "rdns": parse_bool_env(get_proxy_env("RDNS", label), default=True),
    }
    username = get_proxy_env("USERNAME", label)
    password = get_proxy_env("PASSWORD", label)
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy, None


def proxy_client_kwargs(label: str) -> dict[str, Any]:
    """``TelegramClient`` kwargs (``proxy``/``connection``) for a label; empty if none."""
    proxy, connection = build_proxy_for_label(label)
    kwargs: dict[str, Any] = {}
    if proxy is not None:
        kwargs["proxy"] = proxy
    if connection is not None:
        kwargs["connection"] = connection
    return kwargs
