from pathlib import Path

import run_scheduler
from app.config.settings import Settings


class _FakeScheduler:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True
        raise KeyboardInterrupt  # simulate Ctrl+C so main() returns instead of blocking


def test_main_builds_and_starts_the_scheduler(tmp_path: Path, monkeypatch, capsys) -> None:
    fake_scheduler = _FakeScheduler()
    monkeypatch.setattr(run_scheduler, "build_scheduler", lambda settings: fake_scheduler)
    settings = Settings(logs_dir=tmp_path / "logs")

    exit_code = run_scheduler.main(settings)

    assert exit_code == 0
    assert fake_scheduler.started is True
    assert "Scheduler running" in capsys.readouterr().out
