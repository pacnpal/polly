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


def is_browser_navigation(request: Request) -> bool:
    """Return True if the request looks like a top-level browser navigation.

    Real browsers send Sec-Fetch-Mode: navigate (and Sec-Fetch-Dest: document)
    when the user types a URL or clicks a link directly. HTMX (fetch),
    TestClient, curl and most scripts do not send these headers, so this
    is a reliable way to distinguish "paste URL into address bar" from
    every other caller.
    """
    sec_mode = request.headers.get("sec-fetch-mode", "").lower()
    sec_dest = request.headers.get("sec-fetch-dest", "").lower()
    return sec_mode == "navigate" or sec_dest == "document"
