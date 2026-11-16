"""Recipient addresses never reach the logs or stdout: GitHub masks only the
whole EMAIL_TO secret, so split addresses would print in the public run log."""

import logging
from unittest.mock import MagicMock, patch

from cinema_digest.emailer import send_digest

ADDRESSES = ["first@example.com", "second@example.org"]


def _send(dry_run):
    return send_digest(
        "body", "<p>body</p>",
        smtp_host="smtp.example.com", smtp_port=587, smtp_user="user", smtp_password="pw",
        from_addr="bot@example.com", to_addrs=ADDRESSES, dry_run=dry_run,
    )


def test_dry_run_does_not_print_addresses(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the dry run writes digest_preview.html here
    _send(dry_run=True)
    out = capsys.readouterr().out
    assert not any(a in out for a in ADDRESSES)
    assert "2 recipient(s)" in out


def test_real_send_does_not_log_addresses(caplog):
    with patch("cinema_digest.emailer.smtplib.SMTP") as smtp, caplog.at_level(logging.INFO):
        smtp.return_value.__enter__.return_value = MagicMock()
        _send(dry_run=False)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert not any(a in logged for a in ADDRESSES)
    assert "2 recipient(s)" in logged
