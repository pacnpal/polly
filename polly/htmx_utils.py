"""HTMX request helpers.

Small utilities for HTMX-aware request handling. Intentionally tiny — anything
larger belongs in a dedicated module.
"""

from fastapi import Request


def is_htmx(request: Request) -> bool:
    """Return True if the request was issued by HTMX (HX-Request: true)."""
    return request.headers.get("HX-Request") == "true"


def htmx_target(request: Request) -> str:
    """Return the id of the element that triggered an HTMX swap (HX-Target).

    Empty string if the header is absent — the caller is responsible for
    treating that as 'no specific target'.
    """
    return request.headers.get("HX-Target") or ""
