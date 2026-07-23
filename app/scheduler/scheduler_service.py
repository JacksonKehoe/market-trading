"""APScheduler wiring: registers the trading jobs at their configured times.

Kept separate from `jobs.py` so the jobs themselves stay plain, testable
functions with no APScheduler import -- this module's only job is
translating `Settings` (report times, whether the hourly scan is on)
into cron triggers.
"""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config.settings import Settings, get_settings
from app.scheduler.jobs import evening_job, hourly_scan_job, morning_job

_WEEKDAYS = "mon-fri"


def _parse_hh_mm(value: str) -> tuple[int, int]:
    hour_str, minute_str = value.split(":")
    return int(hour_str), int(minute_str)


def build_scheduler(settings: Settings | None = None) -> BlockingScheduler:
    """Construct a `BlockingScheduler` with jobs registered but not started."""
    settings = settings or get_settings()
    scheduler = BlockingScheduler()

    morning_hour, morning_minute = _parse_hh_mm(settings.morning_report_time)
    scheduler.add_job(
        morning_job,
        CronTrigger(day_of_week=_WEEKDAYS, hour=morning_hour, minute=morning_minute),
        id="morning_job",
        name="Morning scan + trade + report",
    )

    evening_hour, evening_minute = _parse_hh_mm(settings.evening_report_time)
    scheduler.add_job(
        evening_job,
        CronTrigger(day_of_week=_WEEKDAYS, hour=evening_hour, minute=evening_minute),
        id="evening_job",
        name="Evening wrap-up + report",
    )

    if settings.hourly_scan_enabled:
        scheduler.add_job(
            hourly_scan_job,
            CronTrigger(day_of_week=_WEEKDAYS, hour="9-16", minute=0),
            id="hourly_scan_job",
            name="Hourly scan",
        )

    return scheduler
