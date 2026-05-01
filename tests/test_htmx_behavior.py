"""Tests for HTMX-specific behavior in the web app.

Two areas:
- The exception handler's HTMX content negotiation, exercised against a
  minimal FastAPI app so the auth middleware doesn't get in the way.
- The card-target dispatch logic in close_poll_htmx / delete_poll_htmx,
  exercised by patching templates.TemplateResponse and capturing the
  template chosen for each branch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

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
        # Make TypeSafeColumn.get_string return "scheduled" for status,
        # "" for image_path. Easiest: stub TypeSafeColumn.
        db = _FakeDB([[fake_poll]])

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
        db = _FakeDB([[fake_poll]])

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
