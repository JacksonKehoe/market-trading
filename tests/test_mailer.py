from app.config.settings import Settings
from app.email.mailer import send_email


class _FakeSmtp:
    """Stands in for `smtplib.SMTP` — no network access."""

    instances: list["_FakeSmtp"] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_calls: list[tuple[str, str]] = []
        self.sent: list[tuple[str, list[str], str]] = []
        _FakeSmtp.instances.append(self)

    def __enter__(self) -> "_FakeSmtp":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_calls.append((username, password))

    def sendmail(self, from_addr: str, to_addrs: list[str], message: str) -> None:
        self.sent.append((from_addr, to_addrs, message))


def _configured_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = dict(
        email_username="bot@example.com",
        email_password="secret",
        email_to="trader@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_send_email_skips_when_not_configured() -> None:
    settings = Settings()  # no email_username/password/to
    assert settings.email_enabled is False

    sent = send_email(settings, "Subject", "<p>Body</p>")

    assert sent is False


def test_send_email_sends_via_smtp_when_configured(monkeypatch) -> None:
    _FakeSmtp.instances.clear()
    monkeypatch.setattr("app.email.mailer.smtplib.SMTP", _FakeSmtp)
    settings = _configured_settings()

    sent = send_email(settings, "Morning Report", "<p>Hello</p>")

    assert sent is True
    assert len(_FakeSmtp.instances) == 1
    fake = _FakeSmtp.instances[0]
    assert fake.host == "smtp.example.com"
    assert fake.port == 587
    assert fake.started_tls is True
    assert fake.login_calls == [("bot@example.com", "secret")]
    assert len(fake.sent) == 1
    from_addr, to_addrs, message = fake.sent[0]
    assert from_addr == "bot@example.com"
    assert to_addrs == ["trader@example.com"]
    assert "Morning Report" in message
