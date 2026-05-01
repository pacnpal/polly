"""Unit tests for ``polly.poll_request_models``."""

from datetime import datetime, timedelta

import pytest
import pytz
from pydantic import ValidationError

from polly.poll_request_models import (
    PollFormRequest,
    VoteRequest,
    poll_form_to_dict,
    validation_error_to_messages,
)


class _FormShim(dict):
    """Mimic Starlette's ``FormData.get`` interface backed by a plain dict."""

    def get(self, key, default=None):  # type: ignore[override]
        return super().get(key, default)


def _future(hours: int, tz: str = "US/Pacific") -> str:
    """Return a fixed summer-noon datetime offset by ``hours`` in ``tz``.

    Using a fixed far-future summer date (rather than ``datetime.now() +
    timedelta``) keeps tests deterministic and avoids landing on DST
    gap/overlap wall-clock times that ``tz.localize(..., is_dst=None)``
    would reject as ambiguous or non-existent.
    """
    base = pytz.timezone(tz).localize(datetime(2099, 6, 15, 12, 0))
    return (base + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


def _base_form(**overrides) -> _FormShim:
    data = {
        "name": "Sample Poll",
        "question": "Which option do you prefer?",
        "server_id": "12345",
        "channel_id": "67890",
        "option1": "alpha",
        "option2": "beta",
        "timezone": "US/Pacific",
        "open_time": _future(2),
        "close_time": _future(4),
    }
    data.update(overrides)
    return _FormShim(data)


def _validate(form: _FormShim) -> PollFormRequest:
    return PollFormRequest.model_validate(poll_form_to_dict(form))


class TestPollFormRequestHappyPath:
    def test_minimal_valid_payload(self):
        m = _validate(_base_form())
        assert m.name == "Sample Poll"
        assert m.options == ["alpha", "beta"]
        assert m.timezone == "US/Pacific"
        assert m.open_time_utc is not None
        assert m.close_time_utc is not None
        assert m.close_time_utc > m.open_time_utc

    def test_open_immediately_skips_open_time(self):
        # When opening immediately, close_time must be relative to *now*,
        # not the fixed-future _future() helper, since the duration is
        # measured from the current moment.
        close_dt = datetime.now(pytz.timezone("US/Pacific")) + timedelta(hours=2)
        m = _validate(
            _base_form(
                open_immediately="true",
                open_time="",
                close_time=close_dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M"),
            )
        )
        assert m.open_immediately is True
        assert m.open_time_utc is not None
        assert m.close_time_utc > m.open_time_utc

    def test_max_choices_resolved_for_multiple_choice(self):
        m = _validate(_base_form(multiple_choice="true", max_choices="2"))
        assert m.max_choices == 2

    def test_max_choices_dropped_for_single_choice(self):
        m = _validate(
            _base_form(multiple_choice="false", max_choices="1")
        )
        assert m.max_choices is None

    def test_role_ping_fields_zeroed_when_disabled(self):
        m = _validate(
            _base_form(
                ping_role_enabled="false",
                ping_role_id="555",
                ping_role_on_close="true",
            )
        )
        assert m.ping_role_id is None
        assert m.ping_role_on_close is False

    def test_non_numeric_ping_role_id_ignored_when_disabled(self):
        # A stale or tampered non-numeric ping_role_id must not fail
        # validation when role ping is off — legacy behavior was to drop it.
        m = _validate(
            _base_form(ping_role_enabled="false", ping_role_id="not-a-number")
        )
        assert m.ping_role_id is None

    def test_quotes_stripped_from_options(self):
        m = _validate(_base_form(option1='foo"bar', option2="baz'qux"))
        assert m.options == ["foobar", "bazqux"]

    def test_html_stripped_from_name_and_question(self):
        m = _validate(
            _base_form(
                name='<script>"Sample"</script>',
                question="Which option<br/> do 'you' prefer?",
            )
        )
        assert m.name == "scriptSample/script"
        assert m.question == "Which optionbr/ do you prefer?"

    def test_image_message_text_preserves_discord_markup(self):
        # <@user>, <#channel>, <:emoji:id> must survive — they're Discord
        # markdown, not HTML.
        m = _validate(
            _base_form(image_message_text="ping <@123> in <#456> :: <:smile:789>")
        )
        assert m.image_message_text == "ping <@123> in <#456> :: <:smile:789>"

    def test_internal_utc_fields_excluded_from_dump(self):
        m = _validate(_base_form())
        dumped = m.model_dump()
        assert "open_time_utc" not in dumped
        assert "close_time_utc" not in dumped
        # but the parsed datetimes are still accessible on the instance.
        assert m.open_time_utc is not None

    def test_timezone_alias_normalized(self):
        m = _validate(
            _base_form(
                timezone="EDT",
                open_time=_future(6, "US/Eastern"),
                close_time=_future(8, "US/Eastern"),
            )
        )
        assert m.timezone == "US/Eastern"


class TestPollFormRequestFailures:
    def test_close_before_open(self):
        future_open = _future(4)
        future_close = _future(2)
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(open_time=future_open, close_time=future_close)
            )
        assert "after the open time" in str(exc.value)

    def test_open_time_in_past(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(open_time="2020-01-01T00:00"))
        assert "next full minute" in str(exc.value)

    def test_role_ping_enabled_without_role(self):
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(ping_role_enabled="true", ping_role_id="")
            )
        assert "select a role" in str(exc.value)

    def test_invalid_close_time_format(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(close_time="not-a-date"))
        assert "invalid date/time format" in str(exc.value).lower()

    def test_non_numeric_server_id(self):
        with pytest.raises(ValidationError):
            _validate(_base_form(server_id="abc"))

    def test_non_numeric_channel_id(self):
        with pytest.raises(ValidationError):
            _validate(_base_form(channel_id="xyz"))

    def test_non_numeric_ping_role_id(self):
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(ping_role_enabled="true", ping_role_id="foo")
            )
        assert "numeric Discord ID" in str(exc.value)

    def test_duplicate_options_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(option2="alpha"))
        assert "duplicate" in str(exc.value).lower()

    def test_overlong_option_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(option2="b" * 101))
        assert "100 characters" in str(exc.value)

    def test_too_few_options(self):
        with pytest.raises(ValidationError):
            _validate(_base_form(option2=""))

    def test_max_choices_exceeds_options(self):
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(multiple_choice="true", max_choices="5")
            )
        assert "cannot exceed" in str(exc.value)

    def test_max_choices_non_numeric(self):
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(multiple_choice="true", max_choices="abc")
            )
        assert "valid number" in str(exc.value)

    def test_short_name_rejected(self):
        with pytest.raises(ValidationError):
            _validate(_base_form(name="no"))

    def test_quote_only_option_dropped(self):
        # "''" collapses to "" after quote stripping; leaves only one
        # real option so the 2-minimum constraint should fire.
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(option2="''"))
        assert "at least 2" in str(exc.value)

    def test_invalid_timezone_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(timezone="Mars/Phobos"))
        assert "invalid timezone" in str(exc.value).lower()

    def test_duration_too_short(self):
        # Fixed summer noon -> safely outside any DST transition.
        base = pytz.timezone("US/Pacific").localize(datetime(2099, 6, 15, 12, 0))
        open_dt = base + timedelta(hours=2)
        close_dt = open_dt + timedelta(seconds=30)
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(
                    open_time=open_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    close_time=close_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                )
            )
        assert "at least 1 minute" in str(exc.value)

    def test_duration_too_long(self):
        base = pytz.timezone("US/Pacific").localize(datetime(2099, 6, 15, 12, 0))
        open_dt = base + timedelta(hours=2)
        close_dt = base + timedelta(days=31)
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(
                    open_time=open_dt.strftime("%Y-%m-%dT%H:%M"),
                    close_time=close_dt.strftime("%Y-%m-%dT%H:%M"),
                )
            )
        assert "30 days" in str(exc.value)


class TestValidationErrorToMessages:
    def test_translates_value_error_with_field_prefix(self):
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(ping_role_enabled="true", ping_role_id="")
            )
        msgs = validation_error_to_messages(exc.value)
        assert msgs and msgs[0]["field_name"] == "Role Selection"
        assert "select a role" in msgs[0]["message"]

    def test_translates_pattern_failure_with_field_loc(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(server_id="abc"))
        msgs = validation_error_to_messages(exc.value)
        assert msgs and msgs[0]["field_name"] == "Server"
        assert msgs[0]["message"] == "Please select a Discord server"
        assert "post this poll" in msgs[0]["suggestion"]

    def test_channel_pattern_failure_uses_friendly_copy(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(channel_id="bad"))
        msgs = validation_error_to_messages(exc.value)
        assert msgs[0]["field_name"] == "Channel"
        assert msgs[0]["message"] == "Please select a Discord channel"

    def test_missing_server_id_uses_friendly_copy(self):
        # Empty string mimics an unselected dropdown -> string_too_short
        # under the digits-only pattern; should still surface friendly copy.
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(server_id=""))
        msgs = validation_error_to_messages(exc.value)
        assert msgs[0]["field_name"] == "Server"
        assert msgs[0]["message"] == "Please select a Discord server"

    def test_model_level_value_error_keeps_suggestion(self):
        # Role-Selection error originates from a model_validator and has
        # an empty ``loc``; the wrapper should still attach the role-ping
        # suggestion based on the parsed label.
        with pytest.raises(ValidationError) as exc:
            _validate(
                _base_form(ping_role_enabled="true", ping_role_id="")
            )
        msgs = validation_error_to_messages(exc.value)
        assert msgs[0]["field_name"] == "Role Selection"
        assert "disable role ping" in msgs[0]["suggestion"]

    def test_min_length_failure_uses_friendly_label(self):
        with pytest.raises(ValidationError) as exc:
            _validate(_base_form(name="no"))
        msgs = validation_error_to_messages(exc.value)
        assert msgs[0]["field_name"] == "Poll Name"
        assert "descriptive" in msgs[0]["suggestion"]


class TestVoteRequest:
    def test_valid_vote(self):
        v = VoteRequest.model_validate({"user_id": " 123 ", "option_index": 1})
        assert v.user_id == "123"
        assert v.option_index == 1

    def test_negative_option_index_rejected(self):
        with pytest.raises(ValidationError):
            VoteRequest.model_validate({"user_id": "1", "option_index": -1})

    def test_empty_user_id_rejected(self):
        with pytest.raises(ValidationError):
            VoteRequest.model_validate({"user_id": "", "option_index": 0})
