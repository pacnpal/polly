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
from fastapi import HTTPException, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


TIMEZONE_ALIASES = {
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
DEFAULT_TIMEZONE = "US/Eastern"
# Backwards-compatible private alias for code that already imports the old name.
_TIMEZONE_ALIASES = TIMEZONE_ALIASES

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

    Returns :data:`DEFAULT_TIMEZONE` for missing/blank input but raises
    ``ValueError`` for an explicitly malformed one, so tampered or typo'd
    values fail validation instead of silently being shifted to the default.
    """
    if not value:
        return DEFAULT_TIMEZONE
    value = value.strip()
    if not value:
        return DEFAULT_TIMEZONE
    value = TIMEZONE_ALIASES.get(value, value)
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

    # ``image_message_text`` is intentionally NOT stripped of ``<>``: Discord
    # interprets ``<@id>`` (mentions), ``<#id>`` (channels), and
    # ``<:name:id>`` (custom emojis) — stripping them would break those
    # legitimate user inputs. Templates that render this string must rely on
    # Jinja's autoescaping, not validator-side sanitization.

    timezone: str = Field(default=DEFAULT_TIMEZONE)
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

    # Discord caps message content at 2000 characters; validate up front
    # so users see a friendly form error instead of an HTTPException at
    # post time.
    image_message_text: str = Field(default="", max_length=2000)

    # Internal scratch fields populated by ``_resolve_dependent_fields``;
    # excluded from schemas and ``model_dump()`` since they aren't part of
    # the request payload.
    open_time_utc: Optional[datetime] = Field(default=None, exclude=True)
    close_time_utc: Optional[datetime] = Field(default=None, exclude=True)

    @field_validator("name", "question", mode="before")
    @classmethod
    def _sanitize_user_text(cls, value: Any) -> Any:
        # Strip only raw angle brackets so payloads can't smuggle HTML/JS
        # markup into templates, logs, or Discord embeds. Apostrophes and
        # quotes are legitimate punctuation ("don't", "Friday's vote") and
        # are safely handled by Jinja autoescaping on the way out — we
        # deliberately diverge from legacy validate_poll_name's broader
        # quote scrub so user prose isn't mangled.
        if isinstance(value, str):
            return re.sub(r'[<>]', "", value)
        return value

    @field_validator("timezone", mode="before")
    @classmethod
    def _coerce_timezone(cls, value: Any) -> str:
        # ``None``/empty defaults to DEFAULT_TIMEZONE; anything provided but
        # not a string (list, int, …) is treated as tampered input and
        # rejected, matching ``_normalize_timezone``'s posture for invalid
        # explicit values.
        if value is None:
            return _normalize_timezone(None)
        if not isinstance(value, str):
            raise ValueError(f"Timezone: invalid timezone ({value!r})")
        return _normalize_timezone(value)

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

    @model_validator(mode="after")
    def _resolve_dependent_fields(self) -> "PollFormRequest":
        self.max_choices = self._resolve_max_choices()

        if not self.ping_role_enabled:
            # Role ping disabled: ignore any stale/tampered ping_role_id
            # rather than rejecting the form, matching legacy behavior.
            self.ping_role_id = None
            self.ping_role_on_close = False
            self.ping_role_on_update = False
        elif not self.ping_role_id:
            raise ValueError(
                "Role Selection: please select a role to ping when role ping is enabled"
            )
        elif not self.ping_role_id.isdigit():
            raise ValueError("Role Selection: must be a numeric Discord ID")

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
            open_dt = self._localize(self.open_time, tz, "Open Time")

        close_dt = self._localize(self.close_time, tz, "Close Time")
        return open_dt, close_dt

    @staticmethod
    def _localize(value: str, tz: Any, field_label: str = "Poll Times") -> datetime:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"{field_label}: invalid date/time format ({value})"
            ) from exc
        if dt.tzinfo is None:
            try:
                dt = tz.localize(dt, is_dst=None)
            except pytz.AmbiguousTimeError as exc:
                raise ValueError(
                    f"{field_label}: {value} is ambiguous in {tz} (DST overlap); "
                    "pick a time outside the transition"
                ) from exc
            except pytz.NonExistentTimeError as exc:
                raise ValueError(
                    f"{field_label}: {value} does not exist in {tz} (DST gap); "
                    "pick a time outside the transition"
                ) from exc
        else:
            # Mirror legacy ``safe_parse_datetime_with_timezone``: if an
            # aware datetime ever reaches us (e.g. via a non-form caller),
            # re-anchor it into the user-selected zone first. Mathematically
            # equivalent to going straight to UTC, but keeps the chosen tz
            # as the visible source of truth.
            dt = dt.astimezone(tz)
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
            # Compute the floor of the next minute directly in UTC to avoid
            # naive timedelta arithmetic on a pytz-aware local datetime,
            # which can produce wrong offsets across DST boundaries.
            next_minute_utc = now.replace(
                second=0, microsecond=0
            ) + timedelta(minutes=1)
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

    def to_validated_data_dict(self, creator_id: str) -> dict:
        """Return the legacy ``(field -> value)`` dict shape used by the
        HTMX endpoints. Centralizing it here keeps the model the single
        source of truth: any new field added to the model only needs to
        be added once for downstream callers to pick it up.
        ``open_time`` / ``close_time`` use the computed UTC datetimes so
        callers can drop straight into APScheduler.
        """
        return {
            "name": self.name,
            "question": self.question,
            "server_id": self.server_id,
            "channel_id": self.channel_id,
            "options": self.options,
            "open_time": self.open_time_utc,
            "close_time": self.close_time_utc,
            "timezone": self.timezone,
            "anonymous": self.anonymous,
            "multiple_choice": self.multiple_choice,
            "max_choices": self.max_choices,
            "open_immediately": self.open_immediately,
            "ping_role_enabled": self.ping_role_enabled,
            "ping_role_id": self.ping_role_id,
            "ping_role_on_close": self.ping_role_on_close,
            "ping_role_on_update": self.ping_role_on_update,
            "image_message_text": self.image_message_text,
            "creator_id": creator_id,
        }


PollCreateRequest = PollFormRequest
PollUpdateRequest = PollFormRequest


class VoteRequest(BaseModel):
    """Validated payload for casting a vote.

    Used by both the bot's reaction handler and any future HTTP vote
    endpoint so option index + user id constraints live in one place.
    """

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., min_length=1, pattern=r"^\d+$")
    option_index: int = Field(..., ge=0)

    @field_validator("user_id", mode="before")
    @classmethod
    def _coerce_user_id(cls, value: Any) -> Any:
        # Restrict the coercion path to types Discord actually emits for
        # user IDs (snowflake int or stringified int). Other shapes (dict,
        # list, None) fall straight to Pydantic's type/missing checks
        # rather than being silently turned into nonsense via str(...).
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return value.strip()
        return value


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
    """Translate raw FastAPI ``FormData`` into a model_validate-ready dict.

    Raw form values are passed through as-is wherever the model has its own
    ``mode="before"`` validator that distinguishes "absent" from "explicit
    falsy". That keeps tampered inputs (e.g. ``timezone=0``, ``max_choices=0``)
    visible to the validator instead of silently collapsing to defaults.
    """
    raw_max_choices = form_data.get("max_choices")
    return {
        "name": form_data.get("name"),
        "question": form_data.get("question"),
        "server_id": form_data.get("server_id"),
        "channel_id": form_data.get("channel_id"),
        "options": _extract_options(form_data),
        # Pass timezone through verbatim; _coerce_timezone defaults None and
        # rejects non-strings instead of silently collapsing falsy garbage.
        "timezone": form_data.get("timezone"),
        "open_time": form_data.get("open_time"),
        "close_time": form_data.get("close_time"),
        "open_immediately": _truthy(form_data.get("open_immediately")),
        "anonymous": _truthy(form_data.get("anonymous")),
        "multiple_choice": _truthy(form_data.get("multiple_choice")),
        # Only collapse the empty-string case; preserve other falsy values
        # (e.g. ``"0"``) so _resolve_max_choices can range-check them.
        "max_choices": None if raw_max_choices == "" else raw_max_choices,
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

# Reverse map of friendly labels → field key, used to rehydrate suggestion
# lookup for model-level ValueErrors where Pydantic's ``loc`` is empty/root
# but the message itself starts with the friendly label (e.g. "Role Selection: ...").
_LABEL_TO_FIELD = {label: field for field, label in _FIELD_LABELS.items()}

# Synthetic prefixes used by model-level validators that don't correspond to
# a single field. ``_LABEL_TO_FIELD`` maps them to a real key in
# ``_FIELD_SUGGESTIONS`` so the wrapper still attaches a useful hint.
_LABEL_TO_FIELD["Poll Duration"] = "close_time"
_LABEL_TO_FIELD["Poll Times"] = "open_time"

# Discord ID fields whose Pydantic pattern error should be translated to
# the legacy user-friendly copy instead of "String should match pattern …".
_DISCORD_ID_PATTERN_MESSAGES = {
    "server_id": "Please select a Discord server",
    "channel_id": "Please select a Discord channel",
    "ping_role_id": "Must be a numeric Discord ID",
}

# When a required Discord ID is missing or blank (most often an unselected
# dropdown), surface the same friendly copy used for pattern mismatches
# instead of leaking Pydantic's "Field required" / "String should have at
# least 1 character" wording.
_DISCORD_ID_PRESENCE_MESSAGES = {
    "server_id": "Please select a Discord server",
    "channel_id": "Please select a Discord channel",
}
_DISCORD_ID_PRESENCE_TYPES = {"missing", "string_too_short", "string_type"}


def validation_error_to_messages(exc: ValidationError) -> List[dict]:
    """Convert a Pydantic ``ValidationError`` into the legacy error shape.

    Restores per-field labels and suggestion text so end-users see the same
    hints as the original hand-rolled validator. When Pydantic provides a
    concrete ``loc``, that field's canonical label always wins over any
    ``"Label: ..."`` prefix in the raw message; a colon prefix is only used
    as the source of truth when ``loc`` is empty (model-level validators).
    """
    messages: List[dict] = []
    for err in exc.errors():
        msg = err.get("msg", "Invalid value")
        err_type = err.get("type", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]

        loc = err.get("loc") or ()
        raw_field = str(loc[-1]) if loc else ""

        # Split off any "Label: detail" prefix up front so we can use the
        # detail body regardless of which source wins for ``field_name``.
        prefix_label = ""
        detail_after_prefix = msg
        if ":" in msg:
            head, _, tail = msg.partition(":")
            prefix_label = head.strip()
            detail_after_prefix = tail.strip() or msg

        if raw_field in _FIELD_LABELS:
            # Concrete loc: trust the canonical label and drop only the
            # redundant "Field: ..." prefix from the body so output reads
            # cleanly (e.g. avoid "Poll Options: Options: duplicates ...").
            # We MUST keep informative prefixes like "Option 2: ..." that
            # carry data the field label can't express.
            field_name = _FIELD_LABELS[raw_field]
            redundant_prefixes = {
                field_name,
                raw_field.replace("_", " ").title(),
            }
            if prefix_label and prefix_label in redundant_prefixes:
                detail = detail_after_prefix
            else:
                detail = msg
        elif prefix_label:
            # No useful loc; fall back to the message-level prefix and
            # rehydrate raw_field via _LABEL_TO_FIELD for suggestion lookup.
            field_name = prefix_label
            detail = detail_after_prefix
            if not raw_field:
                raw_field = _LABEL_TO_FIELD.get(prefix_label, raw_field)
        else:
            field_name = (
                raw_field.replace("_", " ").title() if raw_field else "Field"
            )
            detail = msg

        if (
            err_type == "string_pattern_mismatch"
            and raw_field in _DISCORD_ID_PATTERN_MESSAGES
        ):
            detail = _DISCORD_ID_PATTERN_MESSAGES[raw_field]
        elif (
            err_type in _DISCORD_ID_PRESENCE_TYPES
            and raw_field in _DISCORD_ID_PRESENCE_MESSAGES
        ):
            detail = _DISCORD_ID_PRESENCE_MESSAGES[raw_field]

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

    Raises ``HTTPException`` with status 422 (carrying the legacy-shaped
    error messages in ``detail``) on invalid payloads, so failures surface
    as proper client errors instead of bubbling to FastAPI's generic 500
    handler.
    """
    form_data = await request.form()
    try:
        return PollFormRequest.model_validate(poll_form_to_dict(form_data))
    except ValidationError as exc:
        # Some Starlette versions renamed the constant; fall back gracefully.
        unprocessable = getattr(
            status,
            "HTTP_422_UNPROCESSABLE_CONTENT",
            getattr(status, "HTTP_422_UNPROCESSABLE_ENTITY", 422),
        )
        raise HTTPException(
            status_code=unprocessable,
            detail=validation_error_to_messages(exc),
        ) from exc
