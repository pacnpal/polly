"""Tests for HTMX-specific behavior in the web app.

Three areas:
- The exception handler's HTMX content negotiation, exercised against a
  minimal FastAPI app so the auth middleware doesn't get in the way.
- The browser-navigation gating (Sec-Fetch-Mode/Sec-Fetch-Dest) used by
  /htmx/polls and /htmx/poll/{id}/details to redirect real top-level
  browser visits while still serving fragments to HTMX/TestClient/curl.
- The card-target dispatch logic in close_poll_htmx / delete_poll_htmx,
  exercised by patching templates.TemplateResponse and capturing the
  template chosen for each branch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.testclient import TestClient

from polly.htmx_utils import is_browser_navigation
from polly.web_app import add_exception_handlers


# ---------------------------------------------------------------------------
# Exception handler
# ---------------------------------------------------------------------------


@pytest.fixture
def htmx_error_client():
    """Minimal app with the production exception handlers + a route that raises."""
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/htmx/boom")
    async def boom():
        raise HTTPException(status_code=400, detail="bad request")

    @app.get("/htmx/structured-boom")
    async def structured_boom():
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "name"], "msg": "field required"}],
        )

    @app.get("/htmx/crash")
    async def crash():
        raise RuntimeError("boom")

    # raise_server_exceptions=False so the catch-all Exception handler runs
    # instead of the test client re-raising.
    return TestClient(app, raise_server_exceptions=False)


class TestHtmxExceptionHandler:
    def test_htmx_request_gets_html_fragment_with_retarget(self, htmx_error_client):
        response = htmx_error_client.get(
            "/htmx/boom", headers={"HX-Request": "true"}
        )
        assert response.status_code == 400
        assert response.headers.get("HX-Retarget") == "#inline-messages"
        assert response.headers.get("HX-Reswap") == "innerHTML"
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
        assert response.json() == {
            "detail": [{"loc": ["body", "name"], "msg": "field required"}]
        }

    def test_htmx_500_gets_html_fragment_with_retarget(self, htmx_error_client):
        response = htmx_error_client.get(
            "/htmx/crash", headers={"HX-Request": "true"}
        )
        assert response.status_code == 500
        assert response.headers.get("HX-Retarget") == "#inline-messages"
        assert response.headers.get("HX-Reswap") == "innerHTML"
        assert "Internal server error" in response.text

    def test_non_htmx_500_gets_json(self, htmx_error_client):
        response = htmx_error_client.get("/htmx/crash")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}

    def test_htmx_structured_detail_renders_as_json_not_repr(
        self, htmx_error_client
    ):
        # Structured detail (e.g. Pydantic validation lists) should be
        # JSON-encoded into the inline error template rather than coerced via
        # str(), which would produce Python repr (single quotes, braces).
        response = htmx_error_client.get(
            "/htmx/structured-boom", headers={"HX-Request": "true"}
        )
        assert response.status_code == 422
        body = response.text
        # JSON form has double-quoted keys and square-brackets; repr would have
        # single quotes around the keys.
        assert '"loc"' in body and '"msg"' in body
        assert "'loc'" not in body


# ---------------------------------------------------------------------------
# Browser-navigation gating (Sec-Fetch-Mode + Sec-Fetch-Dest)
# ---------------------------------------------------------------------------


@pytest.fixture
def browser_nav_client():
    """Minimal app whose route mirrors the gating used by /htmx/polls and
    /htmx/poll/{id}/details: redirect on top-level browser navigation,
    fragment otherwise. Bypasses the auth middleware so we test the
    gating contract in isolation."""
    app = FastAPI()

    @app.get("/htmx/polls")
    async def fake_polls(request: Request):
        if is_browser_navigation(request):
            return RedirectResponse(url="/dashboard", status_code=302)
        return PlainTextResponse("polls fragment")

    @app.get("/htmx/poll/{poll_id}/details")
    async def fake_poll_details(poll_id: int, request: Request):
        if is_browser_navigation(request):
            return RedirectResponse(url="/dashboard", status_code=302)
        return PlainTextResponse(f"details {poll_id}")

    return TestClient(app)


class TestBrowserNavigationGating:
    BROWSER_NAV_HEADERS = {
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document",
    }

    def test_polls_redirects_on_browser_navigation(self, browser_nav_client):
        response = browser_nav_client.get(
            "/htmx/polls",
            headers=self.BROWSER_NAV_HEADERS,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    def test_polls_serves_fragment_without_browser_nav_headers(
        self, browser_nav_client
    ):
        # No Sec-Fetch-* headers (TestClient/curl/scripts default) → fragment.
        response = browser_nav_client.get("/htmx/polls")
        assert response.status_code == 200
        assert response.text == "polls fragment"

    def test_polls_serves_fragment_for_htmx_request(self, browser_nav_client):
        # HTMX sends HX-Request but not Sec-Fetch-Mode: navigate.
        response = browser_nav_client.get(
            "/htmx/polls", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert response.text == "polls fragment"

    def test_polls_serves_fragment_when_only_one_sec_fetch_header_set(
        self, browser_nav_client
    ):
        # AND-of-both is required: navigate without dest=document is not a
        # top-level navigation (e.g. iframe or worker).
        response = browser_nav_client.get(
            "/htmx/polls", headers={"Sec-Fetch-Mode": "navigate"}
        )
        assert response.status_code == 200
        response = browser_nav_client.get(
            "/htmx/polls", headers={"Sec-Fetch-Dest": "document"}
        )
        assert response.status_code == 200

    def test_poll_details_redirects_on_browser_navigation(
        self, browser_nav_client
    ):
        response = browser_nav_client.get(
            "/htmx/poll/42/details",
            headers=self.BROWSER_NAV_HEADERS,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    def test_poll_details_serves_fragment_for_htmx(self, browser_nav_client):
        response = browser_nav_client.get(
            "/htmx/poll/42/details", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert response.text == "details 42"


# ---------------------------------------------------------------------------
# Card-target dispatch in close_poll_htmx / delete_poll_htmx
# ---------------------------------------------------------------------------


def _make_request(hx_target: str | None):
    headers = {"HX-Target": hx_target} if hx_target else {}
    request = MagicMock()
    request.headers = headers
    return request


def _make_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


class _FakeQuery:
    """Walks .filter().first() chains and returns queued results in order."""

    def __init__(self, results):
        self._results = list(results)

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        if not self._results:
            raise AssertionError("FakeQuery exhausted")
        return self._results.pop(0)

    def delete(self):
        return 0


class _FakeDB:
    def __init__(self, query_results):
        # query_results is a list (one entry per .query() call). Each entry
        # is a list of values returned by successive .first() calls.
        self._query_results = list(query_results)
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.deleted = []

    def query(self, *_args, **_kwargs):
        if not self._query_results:
            raise AssertionError("FakeDB query queue exhausted")
        return _FakeQuery(self._query_results.pop(0))

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def delete(self, instance):
        self.deleted.append(instance)


def _capture_template_response():
    """Patch templates.TemplateResponse to record (template_name, context).

    Returns (capture_dict, side_effect_callable). Inject the side_effect into a
    `patch.object(htmx_endpoints.templates, "TemplateResponse", side_effect=...)`.
    """
    captured = {}

    def side_effect(template_name, context, **_kwargs):
        captured["template"] = template_name
        captured["context"] = context
        response = MagicMock()
        response.headers = {}
        return response

    return captured, side_effect


@pytest.mark.asyncio
class TestCloseAndDeleteCardDispatch:
    async def test_close_with_card_target_uses_oob_template(self):
        from polly import htmx_endpoints

        captured, side_effect = _capture_template_response()

        # First .query() — ownership check, returns truthy (id tuple).
        # Second .query() — poll reload, returns a Mock poll.
        # Third .query() — UserPreference, returns None (default tz).
        fake_poll = MagicMock()
        fake_poll.id = 99
        fake_poll.name = "P"
        fake_poll.question = "Q"
        fake_poll.server_name = "s"
        fake_poll.channel_name = "c"
        fake_poll.anonymous = False
        fake_poll.close_time = None
        fake_poll.get_total_votes.return_value = 3

        ownership_db = _FakeDB([[(99,)]])
        oob_db = _FakeDB([[fake_poll], [None]])
        db_iter = iter([ownership_db, oob_db])

        closure_service = MagicMock()
        closure_service.close_poll_unified = AsyncMock(
            return_value={"success": True}
        )

        with (
            patch.object(htmx_endpoints, "get_db_session", lambda: next(db_iter)),
            patch.object(
                htmx_endpoints.templates, "TemplateResponse", side_effect=side_effect
            ),
            patch.object(
                htmx_endpoints,
                "invalidate_user_polls_cache",
                new=AsyncMock(),
            ),
            patch.object(
                htmx_endpoints,
                "format_datetime_for_user",
                return_value="some-time",
            ),
            patch(
                "polly.services.poll.poll_closure_service.get_poll_closure_service",
                return_value=closure_service,
            ),
        ):
            await htmx_endpoints.close_poll_htmx(
                poll_id=99,
                request=_make_request("poll-card-99"),
                bot=None,
                current_user=_make_user(),
            )

        assert captured["template"] == "htmx/components/poll_close_oob.html"
        assert captured["context"]["success_message"] == "Poll closed."

    async def test_close_without_card_target_uses_alert_template(self):
        from polly import htmx_endpoints

        captured, side_effect = _capture_template_response()

        ownership_db = _FakeDB([[(99,)]])
        closure_service = MagicMock()
        closure_service.close_poll_unified = AsyncMock(
            return_value={"success": True}
        )

        with (
            patch.object(
                htmx_endpoints, "get_db_session", lambda: ownership_db
            ),
            patch.object(
                htmx_endpoints.templates, "TemplateResponse", side_effect=side_effect
            ),
            patch.object(
                htmx_endpoints,
                "invalidate_user_polls_cache",
                new=AsyncMock(),
            ),
            patch(
                "polly.services.poll.poll_closure_service.get_poll_closure_service",
                return_value=closure_service,
            ),
        ):
            await htmx_endpoints.close_poll_htmx(
                poll_id=99,
                # Non-card caller: HX-Target is something else (e.g. main-content).
                request=_make_request("main-content"),
                bot=None,
                current_user=_make_user(),
            )

        assert captured["template"] == "htmx/components/alert_success.html"
        assert captured["context"]["redirect_url"] == "/htmx/polls"

    async def test_delete_with_card_target_uses_oob_template(self):
        from polly import htmx_endpoints

        captured, side_effect = _capture_template_response()

        fake_poll = MagicMock()
        # Two query() calls: ownership check, then Vote-deletion query.
        # The vote query uses .filter().delete() and ignores the queued
        # results, so [] is fine for the second slot.
        db = _FakeDB([[fake_poll], []])

        with (
            patch.object(htmx_endpoints, "get_db_session", lambda: db),
            patch.object(
                htmx_endpoints.templates, "TemplateResponse", side_effect=side_effect
            ),
            patch.object(
                htmx_endpoints,
                "invalidate_user_polls_cache",
                new=AsyncMock(),
            ),
            patch.object(
                htmx_endpoints.TypeSafeColumn,
                "get_string",
                side_effect=lambda obj, attr, default="": {
                    "status": "scheduled",
                    "image_path": "",
                }.get(attr, default),
            ),
        ):
            await htmx_endpoints.delete_poll_htmx(
                poll_id=99,
                request=_make_request("poll-card-99"),
                current_user=_make_user(),
            )

        assert captured["template"] == "htmx/components/poll_delete_oob.html"
        assert captured["context"]["success_message"] == "Poll deleted."

    async def test_delete_without_card_target_uses_alert_template(self):
        from polly import htmx_endpoints

        captured, side_effect = _capture_template_response()

        fake_poll = MagicMock()
        # Same two-query setup as the card-target case.
        db = _FakeDB([[fake_poll], []])

        with (
            patch.object(htmx_endpoints, "get_db_session", lambda: db),
            patch.object(
                htmx_endpoints.templates, "TemplateResponse", side_effect=side_effect
            ),
            patch.object(
                htmx_endpoints,
                "invalidate_user_polls_cache",
                new=AsyncMock(),
            ),
            patch.object(
                htmx_endpoints.TypeSafeColumn,
                "get_string",
                side_effect=lambda obj, attr, default="": {
                    "status": "scheduled",
                    "image_path": "",
                }.get(attr, default),
            ),
        ):
            await htmx_endpoints.delete_poll_htmx(
                poll_id=99,
                request=_make_request("main-content"),
                current_user=_make_user(),
            )

        assert captured["template"] == "htmx/components/alert_success.html"
        assert captured["context"]["redirect_url"] == "/htmx/polls"
