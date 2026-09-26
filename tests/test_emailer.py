"""Tests for sending the digest."""

import smtplib
import ssl
from unittest.mock import MagicMock, patch

import pytest

import cinema_digest.emailer as emailer
from cinema_digest.emailer import build_subject, send_digest

SEND_KWARGS = dict(
    smtp_host="smtp.example.com",
    smtp_user="user",
    smtp_password="pass",
    from_addr="from@example.com",
    to_addrs=["to@example.com"],
)


def _server(sent: list, label: str, **side_effects) -> MagicMock:
    server = MagicMock(name=label)
    server.sendmail.side_effect = lambda *a: sent.append(label)
    for method, effect in side_effects.items():
        getattr(server, method).side_effect = effect
    return server


class TestSendDigest:
    def test_quit_failure_after_send_does_not_resend(self):
        sent = []
        ssl_server = _server(sent, "ssl", quit=smtplib.SMTPServerDisconnected("bye"))
        plain_server = _server(sent, "starttls")
        with patch("smtplib.SMTP_SSL", return_value=ssl_server), patch("smtplib.SMTP", return_value=plain_server):
            send_digest("body", "<p>html</p>", smtp_port=465, **SEND_KWARGS)
        assert sent == ["ssl"]

    def test_configured_starttls_port_used_first(self):
        sent = []
        plain_server = _server(sent, "starttls")
        with patch("smtplib.SMTP", return_value=plain_server) as smtp, patch("smtplib.SMTP_SSL") as smtp_ssl:
            send_digest("body", "<p>html</p>", smtp_port=2525, **SEND_KWARGS)
        assert smtp.call_args.args[:2] == ("smtp.example.com", 2525)
        smtp_ssl.assert_not_called()
        assert sent == ["starttls"]

    def test_port_465_uses_implicit_tls(self):
        sent = []
        with patch("smtplib.SMTP_SSL", return_value=_server(sent, "ssl")) as smtp_ssl, patch("smtplib.SMTP") as smtp:
            send_digest("body", "<p>html</p>", smtp_port=465, **SEND_KWARGS)
        assert smtp_ssl.call_args.args[:2] == ("smtp.example.com", 465)
        smtp.assert_not_called()
        assert sent == ["ssl"]

    def test_falls_back_to_ssl_when_port_blocked(self):
        sent = []
        with patch("smtplib.SMTP", side_effect=OSError("blocked")), \
                patch("smtplib.SMTP_SSL", return_value=_server(sent, "ssl")) as smtp_ssl:
            send_digest("body", "<p>html</p>", smtp_port=587, **SEND_KWARGS)
        assert smtp_ssl.call_args.args[:2] == ("smtp.example.com", 465)
        assert sent == ["ssl"]

    def test_no_fallback_after_sendmail_error(self):
        """If sendmail itself fails the server may have the message; don't send again."""
        sent = []
        plain_server = _server(sent, "starttls")
        plain_server.sendmail.side_effect = smtplib.SMTPDataError(451, b"try later")
        with patch("smtplib.SMTP", return_value=plain_server), patch("smtplib.SMTP_SSL") as smtp_ssl:
            with pytest.raises(smtplib.SMTPDataError):
                send_digest("body", "<p>html</p>", smtp_port=587, **SEND_KWARGS)
        smtp_ssl.assert_not_called()

    def test_both_methods_failing_raises(self):
        with patch("smtplib.SMTP", side_effect=OSError("blocked")), \
                patch("smtplib.SMTP_SSL", side_effect=OSError("blocked")):
            with pytest.raises(RuntimeError, match="Could not send digest"):
                send_digest("body", "<p>html</p>", smtp_port=587, **SEND_KWARGS)

    def test_certificates_verified(self):
        sent = []
        plain_server = _server(sent, "starttls")
        ssl_server = _server(sent, "ssl")
        with patch("smtplib.SMTP", return_value=plain_server):
            send_digest("body", "<p>html</p>", smtp_port=587, **SEND_KWARGS)
        context = plain_server.starttls.call_args.kwargs["context"]
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname

        with patch("smtplib.SMTP_SSL", return_value=ssl_server) as smtp_ssl:
            send_digest("body", "<p>html</p>", smtp_port=465, **SEND_KWARGS)
        context = smtp_ssl.call_args.kwargs["context"]
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname

    def test_subject_flag_in_sent_message(self):
        sent_messages = []
        server = MagicMock()
        server.sendmail.side_effect = lambda frm, to, msg: sent_messages.append(msg)
        with patch("smtplib.SMTP", return_value=server):
            send_digest("body", "<p>html</p>", smtp_port=587, subject_flag="CHECK: listings", **SEND_KWARGS)
        assert "Subject: [CHECK: listings] Cinema Digest - " in sent_messages[0]

    def test_dry_run_prints_and_writes_preview(self, tmp_path, monkeypatch, capsys):
        preview = tmp_path / "preview.html"
        monkeypatch.setattr(emailer, "PREVIEW_PATH", preview)
        with patch("smtplib.SMTP") as smtp, patch("smtplib.SMTP_SSL") as smtp_ssl:
            send_digest("the body", "<p>html</p>", smtp_port=587, dry_run=True, subject_flag="X", **SEND_KWARGS)
        smtp.assert_not_called()
        smtp_ssl.assert_not_called()
        out = capsys.readouterr().out
        assert "DRY RUN - Subject: [X] Cinema Digest" in out
        assert "the body" in out
        assert preview.read_text() == "<p>html</p>"


class TestBuildSubject:
    def test_plain(self):
        assert build_subject().startswith("Cinema Digest - ")

    def test_flagged(self):
        assert build_subject("CHECK").startswith("[CHECK] Cinema Digest - ")
