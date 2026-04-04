"""Send the cinema digest by email."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")

PREVIEW_PATH = Path(__file__).resolve().parent.parent / "digest_preview.html"


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
) -> None:
    """Send the digest as a multipart email (plain text + branded HTML).

    In dry_run mode, prints plain text to stdout and writes the HTML
    version to digest_preview.html for browser viewing.
    """
    subject = f"Cinema Digest - {datetime.now(LONDON_TZ).strftime('%d %b %Y')}"

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

    logger.info("Sending digest to %s via %s:%d", to_addrs, smtp_host, smtp_port)

    # Try SSL on port 465 first (works on GitHub Actions and most CI)
    try:
        logger.info("Trying SMTP_SSL on port 465")
        server = smtplib.SMTP_SSL(smtp_host, 465, timeout=30)
        try:
            server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, to_addrs, msg.as_string())
            logger.info("Digest sent successfully via SSL port 465")
            return
        finally:
            server.quit()
    except Exception as e:
        logger.warning("SSL port 465 failed: %s", e)

    # Fallback: STARTTLS on configured port
    logger.info("Trying STARTTLS on port %d", smtp_port)
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    try:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        logger.info("Digest sent successfully via STARTTLS port %d", smtp_port)
    finally:
        server.quit()

    logger.info("Digest sent successfully")
