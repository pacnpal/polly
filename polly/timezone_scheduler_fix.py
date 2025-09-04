"""
Timezone-Aware Scheduler Fix for Poll Closing Tasks
Fixes the issue where poll closing tasks don't adhere to the timezone chosen during poll creation.
"""

import pytz
from datetime import datetime
from apscheduler.triggers.date import DateTrigger
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TimezoneAwareScheduler:
    """
    Wrapper for APScheduler to handle timezone-aware scheduling correctly.

    The core issue was that poll close_time is stored in UTC in the database,
    but when scheduling jobs, we need to ensure the scheduler interprets the
    time correctly based on the poll's original timezone.
    """

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def schedule_poll_opening(
        self, poll_id: int, open_time: datetime, poll_timezone: str, post_function, bot
    ) -> bool:
        """
        Schedule a poll to open at the correct time considering timezone.

        Args:
            poll_id: The poll ID
            open_time: UTC datetime when poll should open
            poll_timezone: Original timezone the poll was created in
            post_function: Function to call to post the poll
            bot: Discord bot instance

        Returns:
            bool: True if scheduled successfully, False otherwise
        """
        try:
            # Ensure open_time is timezone-aware (should be UTC from database)
            if open_time.tzinfo is None:
                open_time = pytz.UTC.localize(open_time)

            # Convert to UTC if not already
            if open_time.tzinfo != pytz.UTC:
                open_time = open_time.astimezone(pytz.UTC)

            # Schedule using UTC time (APScheduler handles this correctly)
            self.scheduler.add_job(
                post_function,
                DateTrigger(run_date=open_time),
                args=[bot, poll_id],
                id=f"open_poll_{poll_id}",
                replace_existing=True,
            )

            logger.info(
                f"✅ Scheduled poll {poll_id} to open at {open_time} UTC (original timezone: {poll_timezone})"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Failed to schedule poll {poll_id} opening: {e}")
            return False

    def schedule_poll_closing(
        self, poll_id: int, close_time: datetime, poll_timezone: str, close_function
    ) -> bool:
        """
        Schedule a poll to close at the correct time considering timezone.

        This is the CRITICAL FIX for the timezone issue.

        Args:
            poll_id: The poll ID
            close_time: UTC datetime when poll should close
            poll_timezone: Original timezone the poll was created in
            close_function: Function to call to close the poll

        Returns:
            bool: True if scheduled successfully, False otherwise
        """
        try:
            # Ensure close_time is timezone-aware (should be UTC from database)
            if close_time.tzinfo is None:
                close_time = pytz.UTC.localize(close_time)

            # Convert to UTC if not already
            if close_time.tzinfo != pytz.UTC:
                close_time = close_time.astimezone(pytz.UTC)

            # CRITICAL FIX: Use UTC time directly for scheduling
            # APScheduler's DateTrigger expects UTC when no timezone is specified
            # The issue was that we were sometimes passing timezone-naive datetimes
            # or not properly handling the timezone conversion

            self.scheduler.add_job(
                close_function,
                DateTrigger(run_date=close_time),  # Use UTC time directly
                args=[poll_id],
                id=f"close_poll_{poll_id}",
                replace_existing=True,
            )

            logger.info(
                f"✅ Scheduled poll {poll_id} to close at {close_time} UTC (original timezone: {poll_timezone})"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Failed to schedule poll {poll_id} closing: {e}")
            return False

    def remove_poll_jobs(self, poll_id: int) -> tuple[bool, bool]:
        """
        Remove both opening and closing jobs for a poll.

        Args:
            poll_id: The poll ID

        Returns:
            tuple[bool, bool]: (open_job_removed, close_job_removed)
        """
        open_removed = False
        close_removed = False

        # Remove opening job
        try:
            if self.scheduler.get_job(f"open_poll_{poll_id}"):
                self.scheduler.remove_job(f"open_poll_{poll_id}")
                open_removed = True
                logger.debug(f"Removed opening job for poll {poll_id}")
        except Exception as e:
            if "No job by the id" not in str(e):
                logger.warning(f"Error removing opening job for poll {poll_id}: {e}")

        # Remove closing job
        try:
            if self.scheduler.get_job(f"close_poll_{poll_id}"):
                self.scheduler.remove_job(f"close_poll_{poll_id}")
                close_removed = True
                logger.debug(f"Removed closing job for poll {poll_id}")
        except Exception as e:
            if "No job by the id" not in str(e):
                logger.warning(f"Error removing closing job for poll {poll_id}: {e}")

        return open_removed, close_removed


def validate_timezone_aware_datetime(dt: datetime, context: str = "") -> datetime:
    """
    Ensure a datetime is timezone-aware and in UTC.

    Args:
        dt: The datetime to validate
        context: Context string for logging

    Returns:
        datetime: UTC timezone-aware datetime

    Raises:
        ValueError: If datetime cannot be made timezone-aware
    """
    if dt is None:
        raise ValueError(f"Datetime is None {context}")

    try:
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            logger.warning(
                f"Timezone-naive datetime detected {context}, assuming UTC: {dt}"
            )
            return pytz.UTC.localize(dt)

        # Convert to UTC if not already
        if dt.tzinfo != pytz.UTC:
            logger.debug(
                f"Converting datetime to UTC {context}: {dt} -> {dt.astimezone(pytz.UTC)}"
            )
            return dt.astimezone(pytz.UTC)

        return dt

    except Exception as e:
        raise ValueError(f"Failed to validate timezone-aware datetime {context}: {e}")


def safe_parse_poll_times(
    open_time: datetime,
    close_time: datetime,
    poll_timezone: str,
    poll_id: Optional[int] = None,
) -> tuple[datetime, datetime]:
    """
    Safely parse and validate poll opening and closing times.

    Args:
        open_time: Poll opening time (should be UTC from database)
        close_time: Poll closing time (should be UTC from database)
        poll_timezone: Original timezone the poll was created in
        poll_id: Poll ID for logging context

    Returns:
        tuple[datetime, datetime]: (validated_open_time, validated_close_time) both in UTC

    Raises:
        ValueError: If times cannot be validated
    """
    context = f"for poll {poll_id}" if poll_id else ""

    try:
        # Validate both times are timezone-aware and in UTC
        validated_open = validate_timezone_aware_datetime(
            open_time, f"open_time {context}"
        )
        validated_close = validate_timezone_aware_datetime(
            close_time, f"close_time {context}"
        )

        # Validate time order
        if validated_close <= validated_open:
            raise ValueError(f"Close time must be after open time {context}")

        logger.debug(
            f"✅ Validated poll times {context}: open={validated_open}, close={validated_close}, timezone={poll_timezone}"
        )

        return validated_open, validated_close

    except Exception as e:
        logger.error(f"❌ Failed to validate poll times {context}: {e}")
        raise ValueError(f"Invalid poll times {context}: {e}")
