#!/usr/bin/env python
"""Start the paper trading scheduler.

    python run_scheduler.py

Runs the morning scan+trade job, the evening wrap-up job, and (if
HOURLY_SCAN_ENABLED=true) an hourly scan, at the times configured in
`.env`. Runs until interrupted (Ctrl+C). This process places simulated
(paper) trades only -- it never connects to a brokerage.
"""

from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.scheduler.scheduler_service import build_scheduler
from app.utils.logging_config import configure_logging, get_logger


def main(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    configure_logging(settings.logs_dir)
    logger = get_logger("scheduler")

    scheduler = build_scheduler(settings)
    strategies = ", ".join(settings.strategies)
    logger.info(
        "Scheduler starting: morning=%s evening=%s hourly_scan=%s strategies=%s",
        settings.morning_report_time,
        settings.evening_report_time,
        settings.hourly_scan_enabled,
        strategies,
    )
    print(
        f"Scheduler running (morning {settings.morning_report_time}, "
        f"evening {settings.evening_report_time}, strategies={strategies}). "
        "Press Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
