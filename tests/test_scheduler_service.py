from app.config.settings import Settings
from app.scheduler.scheduler_service import build_scheduler


def test_build_scheduler_registers_morning_and_evening_jobs() -> None:
    settings = Settings(morning_report_time="07:30", evening_report_time="18:15", hourly_scan_enabled=False)

    scheduler = build_scheduler(settings)
    job_ids = {job.id for job in scheduler.get_jobs()}

    assert job_ids == {"morning_job", "evening_job"}


def test_build_scheduler_registers_hourly_job_when_enabled() -> None:
    settings = Settings(hourly_scan_enabled=True)

    scheduler = build_scheduler(settings)
    job_ids = {job.id for job in scheduler.get_jobs()}

    assert job_ids == {"morning_job", "evening_job", "hourly_scan_job"}


def test_build_scheduler_omits_hourly_job_when_disabled() -> None:
    settings = Settings(hourly_scan_enabled=False)

    scheduler = build_scheduler(settings)

    assert "hourly_scan_job" not in {job.id for job in scheduler.get_jobs()}


def test_build_scheduler_uses_configured_report_times() -> None:
    settings = Settings(morning_report_time="06:45", evening_report_time="19:05")

    scheduler = build_scheduler(settings)
    morning_trigger = scheduler.get_job("morning_job").trigger
    fields = {f.name: str(f) for f in morning_trigger.fields}

    assert fields["hour"] == "6"
    assert fields["minute"] == "45"
