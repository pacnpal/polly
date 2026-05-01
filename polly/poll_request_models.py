"""
Pydantic v2 request models for poll create/update/vote.

Centralizes form-data parsing and validation so endpoint handlers can rely
on a typed, validated payload instead of scattered ``form_data.get(...)``
calls. Use :func:`parse_poll_form_request` as a FastAPI dependency
(``Depends(parse_poll_form_request)``) to obtain a validated
:class:`PollFormRequest` from any form-encoded request body.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple

import pytz
from fastapi import Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


_TIMEZONE_ALIASES = {
    "EDT": "US/Eastern",
    "EST": "US/Eastern",
    "CDT": "US/Central",
    "CST": "US/Central",
    "MDT": "US/Mountain",
    "MST": "US/Mountain",
    "PDT": "US/Pacific",
    "PST": "US/Pacific",
    "Eastern": "US/Eastern",
    "Central": "US/Central",
    "Mountain": "US/Mountain",
    "Pacific": "US/Pacific",
}

_TRUE_STRINGS = {"true", "1", "on", "yes"}


def _truthy(value: Any) -> bool:
    """Best-effort coercion of HTML form values to ``bool``."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUE_STRINGS


def _normalize_timezone(value: Optional[str]) -> str:
    """Normalize a user-supplied timezone identifier.

    Returns the default timezone for missing/blank input but raises
    ``ValueError`` for an explicitly malformed one, so tampered or typo'd
    values fail validation instead of silently being shifted to Eastern.
    """
    if not value:
        return "US/Eastern"
    value = value.strip()
    if not value:
        return "US/Eastern"
    value = _TIMEZONE_ALIASES.get(value, value)
    try:
        pytz.timezone(value)
    except pytz.UnknownTimeZoneError as exc:
        raise ValueError(f"Timezone: invalid timezone ({value})") from exc
    return value


class PollFormRequest(BaseModel):
    """Validated form payload for poll create/update endpoints.

    The same shape backs both endpoints because the edit form is a
    superset of the create form (existing fields must still validate).
    Aliases :class:`PollCreateRequest` and :class:`PollUpdateRequest` are
    exported below for call-site clarity.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore",
        populate_by_name=True,
    )

    name: str = Field(..., min_length=3, max_length=255)
    question: str = Field(..., min_length=5, max_length=2000)
    server_id: str = Field(..., min_length=1, pattern=r"^\d+$")
    channel_id: str = Field(..., min_length=1, pattern=r"^\d+$")
    options: List[str] = Field(..., min_length=2, max_length=10)

    timezone: str = Field(default="US/Eastern")
    open_time: Optional[str] = None
    close_time: Optional[str] = None

    open_immediately: bool = False
    anonymous: bool = False
    multiple_choice: bool = False
    # Carried as Optional[Any] so we can defer numeric coercion / range checks
    # to ``_resolve_dependent_fields``: a value of ``"1"`` on a single-choice
    # poll must be discarded, not rejected.
    max_choices: Optional[Any] = None

    ping_role_enabled: bool = False
    ping_role_id: Optional[str] = None
    ping_role_on_close: bool = False
    ping_role_on_update: bool = False

    image_message_text: str = ""

    # Internal scratch fields populated by ``_resolve_dependent_fields``;
    # excluded from schemas and ``model_dump()`` since they aren't part of
    # the request payload.
    open_time_utc: Optional[datetime] = Field(default=None, exclude=True)
    close_time_utc: Optional[datetime] = Field(default=None, exclude=True)

    @field_validator("timezone", mode="before")
    @classmethod
    def _coerce_timezone(cls, value: Any) -> str:
        return _normalize_timezone(value if isinstance(value, str) else None)

    @field_validator("options", mode="before")
    @classmethod
    def _strip_options(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, list):
            cleaned = []
            for item in value:
                # Match legacy PollValidator.validate_poll_options: drop
                # bare quotes while keeping Discord <:emoji:id> markers
                # intact, then re-strip so quote-only entries are dropped
                # rather than collapsing to "".
                text = re.sub(r'["\']', "", str(item).strip()).strip()
                if text:
                    cleaned.append(text)
            return cleaned
        return value

    @field_validator("options")
    @classmethod
    def _validate_option_items(cls, value: List[str]) -> List[str]:
        for index, option in enumerate(value, start=1):
            if len(option) > 100:
                raise ValueError(
                    f"Option {index}: must be 100 characters or fewer"
                )
        if len(set(value)) != len(value):
            raise ValueError("Options: duplicate options are not allowed")
        return value

    @field_validator("ping_role_id", mode="before")
    @classmethod
    def _empty_role_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("ping_role_id")
    @classmethod
    def _ping_role_id_must_be_numeric(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not value.isdigit():
            raise ValueError("Role Id: must be a numeric Discord ID")
        return value

    @model_validator(mode="after")
    def _resolve_dependent_fields(self) -> "PollFormRequest":
        self.max_choices = self._resolve_max_choices()

        if not self.ping_role_enabled:
            self.ping_role_id = None
            self.ping_role_on_close = False
            self.ping_role_on_update = False
        elif not self.ping_role_id:
            raise ValueError(
                "Role Selection: please select a role to ping when role ping is enabled"
            )

        open_dt, close_dt = self._parse_times()
        self._validate_time_window(open_dt, close_dt)
        self.open_time_utc = open_dt
        self.close_time_utc = close_dt
        return self

    def _resolve_max_choices(self) -> Optional[int]:
        if not self.multiple_choice:
            return None
        if self.max_choices is None or self.max_choices == "":
            return None
        try:
            parsed = int(self.max_choices)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Maximum Choices: must be a valid number"
            ) from exc
        if parsed < 2:
            raise ValueError("Maximum Choices: must be at least 2")
        if parsed > 10:
            raise ValueError("Maximum Choices: cannot exceed 10")
        if parsed > len(self.options):
            raise ValueError(
                f"Maximum Choices: cannot exceed the number of options ({len(self.options)})"
            )
        return parsed

    def _parse_times(self) -> Tuple[datetime, datetime]:
        if not self.close_time:
            raise ValueError(
                "Close Time: please select when the poll should end"
            )
        tz = pytz.timezone(self.timezone)

        if self.open_immediately:
            open_dt = datetime.now(pytz.UTC)
        else:
            if not self.open_time:
                raise ValueError(
                    "Open Time: please select when the poll should start"
                )
            open_dt = self._localize(self.open_time, tz)

        close_dt = self._localize(self.close_time, tz)
        return open_dt, close_dt

    @staticmethod
    def _localize(value: str, tz: Any) -> datetime:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"Poll Times: invalid date/time format ({value})"
            ) from exc
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt.astimezone(pytz.UTC)

    def _validate_time_window(
        self, open_dt: datetime, close_dt: datetime
    ) -> None:
        now = datetime.now(pytz.UTC)
        if self.open_immediately:
            if close_dt <= now:
                raise ValueError(
                    "Close Time: must be in the future for immediate polls"
                )
        else:
            user_tz = pytz.timezone(self.timezone)
            now_local = now.astimezone(user_tz)
            next_minute_local = now_local.replace(
                second=0, microsecond=0
            ) + timedelta(minutes=1)
            next_minute_utc = next_minute_local.astimezone(pytz.UTC)
            if open_dt < next_minute_utc:
                raise ValueError(
                    "Open Time: must be scheduled for at least the next full minute"
                )
            if close_dt <= open_dt:
                raise ValueError(
                    "Close Time: must be after the open time"
                )

        duration = close_dt - open_dt
        if duration < timedelta(minutes=1):
            raise ValueError(
                "Poll Duration: poll must run for at least 1 minute"
            )
        if duration > timedelta(days=30):
            raise ValueError(
                "Poll Duration: poll cannot run for more than 30 days"
            )


PollCreateRequest = PollFormRequest
PollUpdateRequest = PollFormRequest


class VoteRequest(BaseModel):
    """Validated payload for casting a vote.

    Used by both the bot's reaction handler and any future HTTP vote
    endpoint so option index + user id constraints live in one place.
    """

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., min_length=1)
    option_index: int = Field(..., ge=0)

    @field_validator("user_id", mode="before")
    @classmethod
    def _coerce_user_id(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip()


def _extract_options(form_data: Any) -> List[str]:
    options: List[str] = []
    for i in range(1, 11):
        value = form_data.get(f"option{i}")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            options.append(text)
    return options


def poll_form_to_dict(form_data: Any) -> dict:
    """Translate raw FastAPI ``FormData`` into a model_validate-ready dict."""
    return {
        "name": form_data.get("name"),
        "question": form_data.get("question"),
        "server_id": form_data.get("server_id"),
        "channel_id": form_data.get("channel_id"),
        "options": _extract_options(form_data),
        "timezone": form_data.get("timezone") or "US/Eastern",
        "open_time": form_data.get("open_time"),
        "close_time": form_data.get("close_time"),
        "open_immediately": _truthy(form_data.get("open_immediately")),
        "anonymous": _truthy(form_data.get("anonymous")),
        "multiple_choice": _truthy(form_data.get("multiple_choice")),
        "max_choices": form_data.get("max_choices") or None,
        "ping_role_enabled": _truthy(form_data.get("ping_role_enabled")),
        "ping_role_id": form_data.get("ping_role_id"),
        "ping_role_on_close": _truthy(form_data.get("ping_role_on_close")),
        "ping_role_on_update": _truthy(form_data.get("ping_role_on_update")),
        "image_message_text": form_data.get("image_message_text") or "",
    }


_FIELD_LABELS = {
    "name": "Poll Name",
    "question": "Question",
    "server_id": "Server",
    "channel_id": "Channel",
    "options": "Poll Options",
    "open_time": "Open Time",
    "close_time": "Close Time",
    "max_choices": "Maximum Choices",
    "ping_role_id": "Role Selection",
    "timezone": "Timezone",
}

_FIELD_SUGGESTIONS = {
    "name": (
        "Try something descriptive like 'Weekend Movie Night' or "
        "'Team Lunch Choice'"
    ),
    "question": (
        "Be specific! Instead of 'Pick one', try "
        "'Which movie should we watch this Friday?'"
    ),
    "server_id": "Choose the server where you want to post this poll",
    "channel_id": "Choose the channel where you want to post this poll",
    "options": (
        "Add more choices for people to vote on. Great polls usually have "
        "3-5 options!"
    ),
    "open_time": "Choose a time when your audience will be active",
    "close_time": (
        "Give people enough time to vote, but not too long that they forget"
    ),
    "max_choices": "Choose a reasonable number of choices users can select",
    "ping_role_id": "Choose a role from the dropdown or disable role ping",
}


def validation_error_to_messages(exc: ValidationError) -> List[dict]:
    """Convert a Pydantic ``ValidationError`` into the legacy error shape.

    Restores per-field labels and suggestion text so end-users see the same
    hints as the original hand-rolled validator.
    """
    messages: List[dict] = []
    for err in exc.errors():
        msg = err.get("msg", "Invalid value")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]

        loc = err.get("loc") or ()
        raw_field = str(loc[-1]) if loc else ""

        if ":" in msg:
            field_name, _, detail = msg.partition(":")
            field_name = field_name.strip()
            detail = detail.strip() or msg
        else:
            field_name = _FIELD_LABELS.get(
                raw_field,
                raw_field.replace("_", " ").title() if raw_field else "Field",
            )
            detail = msg

        messages.append(
            {
                "field_name": field_name,
                "message": detail,
                "suggestion": _FIELD_SUGGESTIONS.get(raw_field, ""),
            }
        )
    return messages


async def parse_poll_form_request(request: Request) -> PollFormRequest:
    """FastAPI dependency: read the request form and return a validated model.

    Raises ``pydantic.ValidationError`` when the payload is invalid; callers
    should catch it and translate to whatever response the endpoint needs.
    """
    form_data = await request.form()
    return PollFormRequest.model_validate(poll_form_to_dict(form_data))
