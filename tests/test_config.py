"""Tests for configuration loading."""

from cinema_digest.config import Config


class TestConfigFromEnv:
    def test_empty_smtp_values_use_defaults(self, monkeypatch):
        # GitHub Actions passes undefined secrets as empty strings
        monkeypatch.setenv("SMTP_PORT", "")
        monkeypatch.setenv("SMTP_HOST", "")
        config = Config.from_env()
        assert config.smtp_port == 587
        assert config.smtp_host == "smtp.gmail.com"

    def test_explicit_values_used(self, monkeypatch):
        monkeypatch.setenv("SMTP_PORT", " 465 ")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("EMAIL_TO", "a@example.com, b@example.com,")
        config = Config.from_env()
        assert config.smtp_port == 465
        assert config.smtp_host == "smtp.example.com"
        assert config.email_to == ["a@example.com", "b@example.com"]
