from pathlib import Path

import run_dashboard
from app.config.settings import Settings


class _FakeFlaskApp:
    def __init__(self) -> None:
        self.run_calls: list[tuple[str, int, bool]] = []

    def run(self, host: str, port: int, debug: bool) -> None:
        self.run_calls.append((host, port, debug))


def test_main_creates_app_and_runs_it_on_the_requested_port(tmp_path: Path, monkeypatch, capsys) -> None:
    fake_app = _FakeFlaskApp()
    monkeypatch.setattr(run_dashboard, "create_app", lambda settings: fake_app)
    settings = Settings(logs_dir=tmp_path / "logs")

    exit_code = run_dashboard.main(["--port", "5050"], settings=settings)

    assert exit_code == 0
    assert fake_app.run_calls == [("127.0.0.1", 5050, False)]
    assert "5050" in capsys.readouterr().out


def test_main_passes_debug_flag_through(tmp_path: Path, monkeypatch) -> None:
    fake_app = _FakeFlaskApp()
    monkeypatch.setattr(run_dashboard, "create_app", lambda settings: fake_app)
    settings = Settings(logs_dir=tmp_path / "logs")

    run_dashboard.main(["--debug"], settings=settings)

    assert fake_app.run_calls == [("127.0.0.1", 5000, True)]
