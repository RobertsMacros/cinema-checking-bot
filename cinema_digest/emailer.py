"""Send the cinema digest by email."""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")

PREVIEW_PATH = Path(__file__).resolve().parent.parent / "digest_preview.html"

SMTP_SSL_PORT = 465
SMTP_STARTTLS_PORT = 587
SMTP_TIMEOUT = 30


class _NotSent(Exception):
    """A failure before the message was handed to the server (safe to retry)."""


def build_subject(subject_flag: str | None = None, now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(LONDON_TZ)
    subject = f"Cinema Digest - {now.strftime('%d %b %Y')}"
    if subject_flag:
        subject = f"[{subject_flag}] {subject}"
    return subject


def _send_via(
    host: str,
    port: int,
    implicit_tls: bool,
    user: str,
    password: str,
    from_addr: str,
    to_addrs: list[str],
    message: str,
) -> None:
    """Send one message over one connection, with certificate verification.

    Raises _NotSent for failures before sendmail (connect, TLS, login), so
    the caller may try another method. Errors from sendmail itself propagate
    unchanged: the server may already have accepted the message, and
    retrying could deliver it twice. A failed QUIT after a successful send
    is ignored.
    """
    context = ssl.create_default_context()
    try:
        if implicit_tls:
            server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
    except (OSError, smtplib.SMTPException) as e:
        raise _NotSent(f"connect to {host}:{port} failed: {e}") from e

    try:
        try:
            if not implicit_tls:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
            server.login(user, password)
        except (OSError, smtplib.SMTPException) as e:
            raise _NotSent(f"TLS/login on {host}:{port} failed: {e}") from e

        server.sendmail(from_addr, to_addrs, message)
    finally:
        try:
            server.quit()
        except (OSError, smtplib.SMTPException):
            pass


def send_digest(
    body: str,
    html_body: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_addr: str,
    to_addrs: list[str],
    dry_run: bool = False,
    subject_flag: str | None = None,
) -> None:
    """Send the digest as a multipart email (plain text + branded HTML).

    In dry_run mode, prints plain text to stdout and writes the HTML
    version to digest_preview.html for browser viewing.

    Uses the configured port first: 465 means implicit TLS (SMTP_SSL), any
    other port means STARTTLS. If that fails before the message is sent
    (e.g. the port is blocked), the other method is tried once on its
    standard port. The message is never sent twice.
    """
    subject = build_subject(subject_flag)

    if dry_run:
        print("=" * 60)
        print(f"DRY RUN - Subject: {subject}")
        print(f"DRY RUN - To: {', '.join(to_addrs)}")
        print("=" * 60)
        print(body)
        print("=" * 60)

        PREVIEW_PATH.write_text(html_body, encoding="utf-8")
        print(f"\nHTML preview written to: {PREVIEW_PATH}")
        return

    if not to_addrs or not to_addrs[0]:
        raise ValueError("No recipient email addresses configured")
    if not smtp_user or not smtp_password:
        raise ValueError("SMTP credentials not configured")
    if not smtp_host:
        raise ValueError("SMTP host not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    message = msg.as_string()

    primary_tls = smtp_port == SMTP_SSL_PORT
    attempts = [(smtp_port, primary_tls)]
    if primary_tls:
        attempts.append((SMTP_STARTTLS_PORT, False))
    else:
        attempts.append((SMTP_SSL_PORT, True))

    logger.info("Sending digest to %s via %s", to_addrs, smtp_host)
    last_error: _NotSent | None = None
    for port, implicit_tls in attempts:
        method = "SMTP_SSL" if implicit_tls else "STARTTLS"
        logger.info("Trying %s on port %d", method, port)
        try:
            _send_via(
                smtp_host, port, implicit_tls, smtp_user, smtp_password, from_addr, to_addrs, message
            )
        except _NotSent as e:
            logger.warning("%s on port %d failed: %s", method, port, e)
            last_error = e
            continue
        logger.info("Digest sent successfully via %s on port %d", method, port)
        return

    raise RuntimeError(f"Could not send digest: {last_error}")
