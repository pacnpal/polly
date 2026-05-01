"""Tests for HTMX-specific behavior in the web app.

Focused on the exception handler's HTMX content negotiation. Built against
a minimal FastAPI app so the auth middleware on the real app doesn't get
in the way.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from polly.web_app import add_exception_handlers


@pytest.fixture
def htmx_error_client():
    """Minimal app with the production exception handlers + a route that raises.

    Bypasses the authenticated app's middleware so the tests target the
    handler in isolation.
    """
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/htmx/boom")
    async def boom():
        raise HTTPException(status_code=400, detail="bad request")

    @app.get("/htmx/structured-boom")
    async def structured_boom():
        # Pydantic-style structured detail (list of dicts)
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "name"], "msg": "field required"}],
        )

    return TestClient(app)


class TestHtmxExceptionHandler:
    def test_htmx_request_gets_html_fragment_with_retarget(self, htmx_error_client):
        response = htmx_error_client.get(
            "/htmx/boom", headers={"HX-Request": "true"}
        )
        assert response.status_code == 400
        assert response.headers.get("HX-Retarget") == "#inline-messages"
        assert response.headers.get("HX-Reswap") == "innerHTML"
        # Inline error template renders an alert-danger div
        assert "alert-danger" in response.text
        assert "bad request" in response.text

    def test_non_htmx_request_gets_json(self, htmx_error_client):
        response = htmx_error_client.get("/htmx/boom")
        assert response.status_code == 400
        assert response.headers.get("HX-Retarget") is None
        assert response.json() == {"detail": "bad request"}

    def test_non_htmx_preserves_structured_detail(self, htmx_error_client):
        response = htmx_error_client.get("/htmx/structured-boom")
        assert response.status_code == 422
        body = response.json()
        assert body == {
            "detail": [{"loc": ["body", "name"], "msg": "field required"}]
        }
